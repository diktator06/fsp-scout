import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.microtask import MicroTaskAssignment
from app.models.user import UserRole
from tests.api.test_employer_matching import UserFactory, employer_headers
from tests.factories import make_bank_candidate
from tests.helpers import auth_headers

TASKS = "/api/v1/candidates/me/tasks"


async def backend_id(client: AsyncClient, headers: dict[str, str]) -> int:
    """Идентификатор специализации Backend."""
    specs = (await client.get("/api/v1/dictionaries/specializations", headers=headers)).json()
    return next(item["id"] for item in specs if item["code"] == "backend")


async def create_tasks(client: AsyncClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    """Задача «решить» с числовым эталоном и задача «предложить подход»."""
    spec = await backend_id(client, headers)
    solve = await client.post(
        "/api/v1/employer/tasks",
        json={
            "kind": "solve",
            "title": "Задержка чтения с кешем",
            "statement": "Redis отвечает за 3 мс, PostgreSQL за 40 мс, попаданий в кеш 80 %. "
            "Средняя задержка чтения в миллисекундах?",
            "specialization_id": spec,
            "answer_value": 11,
            "answer_tolerance": 0.1,
        },
        headers=headers,
    )
    assert solve.status_code == 201, solve.text
    approach = await client.post(
        "/api/v1/employer/tasks",
        json={
            "kind": "approach",
            "title": "Идемпотентность платежей",
            "statement": "Как гарантировать, что повторный запрос на списание не спишет деньги "
            "дважды? Опишите подход и где хранить ключ.",
            "specialization_id": spec,
            "rubric": "Ключ идемпотентности, хранение результата, гонки, срок жизни ключа.",
        },
        headers=headers,
    )
    assert approach.status_code == 201, approach.text
    return [solve.json(), approach.json()]


async def test_task_validation_and_isolation(client: AsyncClient, make_user: UserFactory) -> None:
    """У «решить» нужен эталон, у «подхода» — рубрика; чужие ответы не видны."""
    headers = await employer_headers(client, make_user)
    spec = await backend_id(client, headers)
    base = {
        "title": "Задача",
        "statement": "Описание задачи достаточно длинное, чтобы пройти проверку.",
        "specialization_id": spec,
    }
    no_key = await client.post(
        "/api/v1/employer/tasks", json={**base, "kind": "solve"}, headers=headers
    )
    assert no_key.status_code == 422
    no_rubric = await client.post(
        "/api/v1/employer/tasks", json={**base, "kind": "approach"}, headers=headers
    )
    assert no_rubric.status_code == 422
    solve, _ = await create_tasks(client, headers)
    assert solve["answer_value"] == 11
    stranger = await employer_headers(client, make_user)
    assert (
        await client.get(f"/api/v1/employer/tasks/{solve['id']}/submissions", headers=stranger)
    ).status_code == 404


async def test_offer_auto_grade_and_profile_index(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user: UserFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Система предлагает задачу; «решить» проверяется сразу; фактор M растит индекс."""
    employer = await employer_headers(client, make_user)
    solve, approach = await create_tasks(client, employer)
    candidate = await make_bank_candidate(db_session)
    me = auth_headers(candidate.user)
    card_before = (
        await client.get(f"/api/v1/employer/candidates/{candidate.profile_id}", headers=employer)
    ).json()["card"]
    assert card_before["micro_tasks"]["count"] == 0

    monkeypatch.setattr("random.Random.choice", lambda self, items: items[0])
    overview = (await client.get(TASKS, headers=me)).json()
    assert overview["available"] is True
    current = overview["current"]
    assert current["task"]["id"] == solve["id"]
    assert current["task"]["answer_format"] == "number"
    assert "answer_value" not in current["task"] and "answer_key" not in current["task"]

    graded = await client.post(
        f"{TASKS}/{current['id']}/submit", json={"answer": "11,0"}, headers=me
    )
    assert graded.status_code == 200, graded.text
    assert graded.json()["status"] == "graded" and graded.json()["score"] == 1
    again = await client.post(f"{TASKS}/{current['id']}/submit", json={"answer": "11"}, headers=me)
    assert again.status_code == 409

    overview = (await client.get(TASKS, headers=me)).json()
    assert overview["current"] is None
    assert overview["freshness"]["value"] == pytest.approx(2 / 3, abs=1e-3)
    assert overview["next_offer_at"] is not None

    card = (
        await client.get(f"/api/v1/employer/candidates/{candidate.profile_id}", headers=employer)
    ).json()["card"]
    micro = next(c for c in card["verified_score"]["components"] if c["key"] == "micro_tasks")
    assert micro["contribution"] == pytest.approx(13.3, abs=0.1)
    assert card["verified_score"]["total"] > card_before["verified_score"]["total"]
    assert card["micro_tasks"]["recent"][0]["title"] == solve["title"]
    assert approach["stats"]["assigned"] == 0


async def test_approach_review_limits_and_expiry(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user: UserFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Подход оценивает работодатель; лимит задач в неделю; просроченная задача закрывается."""
    employer = await employer_headers(client, make_user)
    _, approach = await create_tasks(client, employer)
    candidate = await make_bank_candidate(db_session)
    me = auth_headers(candidate.user)
    monkeypatch.setattr("random.Random.choice", lambda self, items: items[-1])

    first = (await client.get(TASKS, headers=me)).json()["current"]
    assert first["task"]["id"] == approach["id"] and first["task"]["answer_format"] == "text"
    assert first["task"]["rubric"]
    submitted = await client.post(
        f"{TASKS}/{first['id']}/submit",
        json={"answer": "Ключ идемпотентности в заголовке, результат храним 24 часа."},
        headers=me,
    )
    assert submitted.json()["status"] == "submitted"
    submissions = (
        await client.get(f"/api/v1/employer/tasks/{approach['id']}/submissions", headers=employer)
    ).json()
    assert submissions[0]["candidate"]["alias"] and "full_name" not in submissions[0]["candidate"]
    graded = await client.post(
        f"/api/v1/employer/task-submissions/{submissions[0]['id']}/grade",
        json={"rating": 4, "feedback": "Хорошо, не хватает гонок"},
        headers=employer,
    )
    assert graded.json()["score"] == 0.75
    assert (
        await client.post(
            f"/api/v1/employer/task-submissions/{submissions[0]['id']}/grade",
            json={"rating": 5},
            headers=employer,
        )
    ).status_code == 409

    monkeypatch.setattr(get_settings(), "microtask_weekly_limit", 2)
    second = await client.post(f"{TASKS}/request", headers=me)
    assert second.status_code == 200, second.text
    current = second.json()["current"]
    await db_session.execute(
        update(MicroTaskAssignment)
        .where(MicroTaskAssignment.id == uuid.UUID(current["id"]))
        .values(due_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    overview = (await client.get(TASKS, headers=me)).json()
    assert overview["current"] is None
    assert any(item["status"] == "expired" for item in overview["history"])
    assert overview["can_request"] is False and overview["requests_left"] == 0
    limited = await client.post(f"{TASKS}/request", headers=me)
    assert limited.status_code == 409


async def test_no_tasks_without_survey(client: AsyncClient, make_user: UserFactory) -> None:
    """Без опроса специализация неизвестна — задач не подобрать, и это сказано прямо."""
    me = auth_headers(await make_user(UserRole.CANDIDATE))
    overview = (await client.get(TASKS, headers=me)).json()
    assert overview["available"] is False and overview["current"] is None
    assert (await client.post(f"{TASKS}/request", headers=me)).status_code == 409
