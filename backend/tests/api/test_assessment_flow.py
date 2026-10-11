import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import AssessmentItem, AssessmentSession, GradeHistory
from app.models.dictionary import Grade
from app.models.user import User
from tests.helpers import auth_headers

UserFactory = Callable[..., Awaitable[User]]
BASE = "/api/v1/assessment"


async def _ids(client: AsyncClient) -> tuple[dict[str, int], dict[str, int]]:
    """Идентификаторы специализаций и грейдов по кодам."""
    specializations = (await client.get("/api/v1/dictionaries/specializations")).json()
    grades = (await client.get("/api/v1/dictionaries/grades")).json()
    return {s["code"]: s["id"] for s in specializations}, {g["code"]: g["id"] for g in grades}


async def _skill(client: AsyncClient, query: str) -> int:
    """Идентификатор навыка по запросу."""
    return (await client.get("/api/v1/dictionaries/skills", params={"query": query})).json()[
        "items"
    ][0]["id"]


async def _candidate(
    client: AsyncClient,
    make_user: UserFactory,
    specialization: str = "backend",
    grade: str = "middle",
) -> dict[str, str]:
    """Кандидат, прошедший опрос: заголовки авторизации готовы к тестированию."""
    headers = auth_headers(await make_user())
    specs, grades = await _ids(client)
    skills = [await _skill(client, "питон"), await _skill(client, "SQL")]
    response = await client.post(
        f"{BASE}/surveys",
        json={
            "specialization_id": specs[specialization],
            "claimed_grade_id": grades[grade],
            "primary_skill_ids": skills,
            "experience_years": 3,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return headers


async def _answer(db_session: AsyncSession, item_id: str, *, correct: bool) -> str:
    """Ответ на экземпляр: правильный берётся из ключа в БД, неправильный строится от него."""
    item = await db_session.get(AssessmentItem, uuid.UUID(item_id))
    assert item is not None
    key = item.answer_key
    if key["kind"] == "choice":
        if correct:
            return str(key["correct"])
        return next(option for option in "abcd" if option != key["correct"])
    return str(key["value"]) if correct else "987654321"


async def _run(
    client: AsyncClient,
    headers: dict[str, str],
    db_session: AsyncSession,
    session: dict[str, Any],
    *,
    correct: bool,
) -> dict[str, Any]:
    """Отвечает на задания, пока тест не закончится."""
    for _ in range(40):
        if session["status"] != "in_progress":
            return session
        item = session["current_item"]
        response = await client.post(
            f"{BASE}/sessions/{session['id']}/answers",
            json={
                "item_id": item["id"],
                "answer": await _answer(db_session, item["id"], correct=correct),
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        session = response.json()
    raise AssertionError("Тест не завершился за 40 заданий")


async def _start(
    client: AsyncClient, headers: dict[str, str], grade: str, mode: str = "full"
) -> dict[str, Any]:
    """Начинает тест на грейд."""
    _, grades = await _ids(client)
    response = await client.post(
        f"{BASE}/sessions", json={"target_grade_id": grades[grade], "mode": mode}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_passing_test_assigns_category_and_verifies_skills(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Верные ответы подтверждают грейд, присваивают категорию и отмечают навыки подтверждёнными."""
    headers = await _candidate(client, make_user)
    session = await _start(client, headers, "junior")
    assert session["current_item"]["position"] == 1
    assert session["min_items"] == 12

    finished = await _run(client, headers, db_session, session, correct=True)
    result = finished["result"]
    assert finished["status"] == "completed"
    assert result["outcome"] in {"passed", "passed_confident"}
    assert result["resulting_category"]["code"] == "backend-junior"
    assert 12 <= result["items_scored"] <= 20
    assert sum(entry["answered"] for entry in result["competencies"]) == result["items_scored"]
    assert [point["grade"]["code"] for point in result["scale"]] == [
        "intern",
        "junior",
        "middle",
        "senior",
    ]

    status = (await client.get("/api/v1/candidates/me/status", headers=headers)).json()
    assert status["grade_status"] == "confirmed"
    assert status["category"]["code"] == "backend-junior"
    assert status["category"]["specialization"]["direction_name"] == "Разработка"
    profile = (await client.get("/api/v1/candidates/me/profile", headers=headers)).json()
    assert any(skill["is_verified"] for skill in profile["skills"])

    history = (await client.get(f"{BASE}/history", headers=headers)).json()
    assert [survey["specialization"]["code"] for survey in history["surveys"]] == ["backend"]
    assert history["grade_changes"][0]["reason"] == "initial"
    assert history["sessions"][0]["outcome"] == result["outcome"]

    if result["outcome"] == "passed_confident":
        options = (await client.get(f"{BASE}/eligibility", headers=headers)).json()["options"]
        allowed = {option["grade"]["code"]: option["allowed"] for option in options}
        assert allowed == {"intern": False, "junior": False, "middle": True, "senior": False}


async def test_failing_test_keeps_lower_grades_open(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Провал не присваивает категорию и не сжигает попытку на уровнях ниже."""
    headers = await _candidate(client, make_user)
    finished = await _run(
        client, headers, db_session, await _start(client, headers, "senior"), correct=False
    )
    assert finished["result"]["outcome"] == "failed"
    assert finished["result"]["resulting_category"] is None

    options = (await client.get(f"{BASE}/eligibility", headers=headers)).json()["options"]
    allowed = {option["grade"]["code"]: option["allowed"] for option in options}
    assert allowed == {"intern": True, "junior": True, "middle": True, "senior": False}
    status = (await client.get("/api/v1/candidates/me/status", headers=headers)).json()
    assert status["grade_status"] == "unconfirmed"

    retry = await client.post(
        f"{BASE}/sessions",
        json={"target_grade_id": (await _ids(client))[1]["senior"]},
        headers=headers,
    )
    assert retry.status_code == 409
    assert retry.json()["error"]["details"]["available_at"] is not None


async def test_suggested_lower_grade_can_be_accepted(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Если тест уверенно подтвердил уровень ниже, его можно принять без пересдачи."""
    headers = await _candidate(client, make_user)
    finished = await _run(
        client, headers, db_session, await _start(client, headers, "senior"), correct=False
    )
    junior_id = await db_session.scalar(select(Grade.id).where(Grade.code == "junior"))
    await db_session.execute(
        update(AssessmentSession)
        .where(AssessmentSession.id == uuid.UUID(finished["id"]))
        .values(suggested_grade_id=junior_id)
    )
    await db_session.commit()

    view = (await client.get(f"{BASE}/sessions/{finished['id']}", headers=headers)).json()
    assert view["result"]["can_accept_suggested"] is True
    accepted = await client.post(
        f"{BASE}/sessions/{finished['id']}/accept-suggested-grade", headers=headers
    )
    assert accepted.status_code == 200
    assert accepted.json()["result"]["resulting_category"]["code"] == "backend-junior"
    reasons = (await db_session.scalars(select(GradeHistory.reason))).all()
    assert "accepted_lower" in [reason.value for reason in reasons]
    again = await client.post(
        f"{BASE}/sessions/{finished['id']}/accept-suggested-grade", headers=headers
    )
    assert again.status_code == 409


async def test_items_never_reveal_answers_and_answers_are_strict(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Ответ API не содержит ключа; ответить можно только на текущее задание своей сессии."""
    headers = await _candidate(client, make_user)
    session = await _start(client, headers, "middle")
    serialized = json.dumps(session, ensure_ascii=False)
    assert "answer_key" not in serialized and '"correct"' not in serialized
    assert "explanation" not in serialized

    wrong_item = await client.post(
        f"{BASE}/sessions/{session['id']}/answers",
        json={"item_id": str(uuid.uuid4()), "answer": "a"},
        headers=headers,
    )
    assert wrong_item.status_code == 409

    stranger = await _candidate(client, make_user)
    assert (
        await client.get(f"{BASE}/sessions/{session['id']}", headers=stranger)
    ).status_code == 404

    second = await client.post(
        f"{BASE}/sessions",
        json={"target_grade_id": (await _ids(client))[1]["junior"]},
        headers=headers,
    )
    assert second.status_code == 409


async def test_overdue_item_is_scored_as_unanswered(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Если время задания вышло, при следующем обращении оно закрывается с нулём."""
    headers = await _candidate(client, make_user)
    session = await _start(client, headers, "middle")
    first_id = uuid.UUID(session["current_item"]["id"])
    await db_session.execute(
        update(AssessmentItem)
        .where(AssessmentItem.id == first_id)
        .values(deadline_at=datetime.now(UTC) - timedelta(minutes=5))
    )
    await db_session.commit()

    view = (await client.get(f"{BASE}/sessions/{session['id']}", headers=headers)).json()
    assert view["current_item"]["position"] == 2
    expired = await db_session.get(AssessmentItem, first_id)
    assert expired is not None
    await db_session.refresh(expired)
    assert expired.timed_out is True and expired.score == 0.0


async def test_abandon_counts_as_failed_attempt(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Прерванный тест закрывает повтор того же уровня на сутки."""
    headers = await _candidate(client, make_user)
    session = await _start(client, headers, "middle")
    abandoned = await client.post(f"{BASE}/sessions/{session['id']}/abandon", headers=headers)
    assert abandoned.json()["status"] == "abandoned"
    options = (await client.get(f"{BASE}/eligibility", headers=headers)).json()["options"]
    allowed = {option["grade"]["code"]: option["allowed"] for option in options}
    assert allowed["middle"] is False and allowed["junior"] is True


async def test_express_mode_is_short(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Экспресс-тест укладывается в 8 заданий и помечается режимом."""
    headers = await _candidate(client, make_user)
    eligibility = (await client.get(f"{BASE}/eligibility", headers=headers)).json()
    assert eligibility["express_available"] is True
    session = await _start(client, headers, "junior", mode="express")
    assert session["mode"] == "express" and session["max_items"] == 8
    finished = await _run(client, headers, db_session, session, correct=True)
    assert finished["result"]["items_scored"] <= 8


async def test_integrity_events_are_counted(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Уход со вкладки фиксируется и виден в итоге, но тест не прерывает."""
    headers = await _candidate(client, make_user)
    session = await _start(client, headers, "junior", mode="express")
    for _ in range(2):
        response = await client.post(
            f"{BASE}/sessions/{session['id']}/integrity-events",
            json={"event": "focus_lost"},
            headers=headers,
        )
        assert response.status_code == 204
    finished = await _run(client, headers, db_session, session, correct=True)
    assert finished["result"]["integrity_flags"]["focus_lost"] == 2


async def test_start_requires_survey_and_blueprint_gates_languages(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Без опроса тест не начать; без Python в стеке задания по Python не включаются."""
    headers = auth_headers(await make_user())
    _, grades = await _ids(client)
    response = await client.post(
        f"{BASE}/sessions", json={"target_grade_id": grades["junior"]}, headers=headers
    )
    assert response.status_code == 422

    specs, _ = await _ids(client)
    java = await _skill(client, "java")
    preview = (
        await client.get(
            f"{BASE}/blueprint",
            params={"specialization_id": specs["backend"], "skill_ids": [java]},
            headers=headers,
        )
    ).json()
    python = next(item for item in preview["competencies"] if item["code"] == "python_core")
    assert python["included"] is False and python["weight"] == 0
    assert preview["available"] is True
    assert sum(item["weight"] for item in preview["competencies"]) == pytest.approx(1.0, abs=0.01)
