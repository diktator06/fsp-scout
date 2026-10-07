import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employer import TrustLevel
from app.models.invitation import ContactDisclosure, DisclosureReason
from app.models.notification import Notification, NotificationKind
from app.models.user import UserRole
from app.services.vacancies import limits
from tests.api.test_employer_matching import UserFactory, employer_headers
from tests.factories import make_bank_candidate
from tests.helpers import auth_headers

EMPLOYER = "/api/v1/employer"


async def vacancy_payload(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    """Вакансия Backend Middle с обязательным Python и FastAPI."""
    specs = (await client.get("/api/v1/dictionaries/specializations", headers=headers)).json()
    grades = (await client.get("/api/v1/dictionaries/grades", headers=headers)).json()
    skills = {}
    for slug in ("python", "fastapi", "kafka"):
        found = (
            await client.get("/api/v1/dictionaries/skills", params={"query": slug}, headers=headers)
        ).json()
        items = found["items"] if isinstance(found, dict) else found
        skills[slug] = next(item["id"] for item in items if item["slug"] == slug)
    return {
        "title": "Python-разработчик (Middle)",
        "description": "Платёжный шлюз: эквайринг, биллинг и сверки с банками. Команда 8 человек.",
        "specialization_id": next(s["id"] for s in specs if s["code"] == "backend"),
        "grade_ids": [next(g["id"] for g in grades if g["code"] == "middle")],
        "skills": [
            {"skill_id": skills["python"], "importance": "must"},
            {"skill_id": skills["fastapi"], "importance": "must"},
            {"skill_id": skills["kafka"], "importance": "nice"},
        ],
        "work_formats": ["remote"],
        "salary_from": 220_000,
        "salary_to": 300_000,
        "salary_gross": True,
    }


async def publish_vacancy(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    """Публикует вакансию и возвращает её."""
    response = await client.post(
        f"{EMPLOYER}/vacancies", json=await vacancy_payload(client, headers), headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_vacancy_lifecycle_rules_and_isolation(
    client: AsyncClient, make_user: UserFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Черновик, публикация, правка, закрытие; вилка обязательна; лимит; чужая вакансия — 404."""
    headers = await employer_headers(client, make_user)
    payload = await vacancy_payload(client, headers)
    wide = await client.post(
        f"{EMPLOYER}/vacancies", json={**payload, "salary_to": 500_000}, headers=headers
    )
    assert wide.status_code == 422
    draft = await client.post(
        f"{EMPLOYER}/vacancies", params={"publish": False}, json=payload, headers=headers
    )
    assert draft.status_code == 201
    assert draft.json()["status"] == "draft" and draft.json()["published_at"] is None
    vacancy_id = draft.json()["id"]

    edited = await client.put(
        f"{EMPLOYER}/vacancies/{vacancy_id}",
        json={**payload, "title": "Python-разработчик в платежи"},
        headers=headers,
    )
    assert edited.json()["title"] == "Python-разработчик в платежи"
    published = await client.post(f"{EMPLOYER}/vacancies/{vacancy_id}/publish", headers=headers)
    assert published.json()["status"] == "published"
    closed = await client.post(f"{EMPLOYER}/vacancies/{vacancy_id}/close", headers=headers)
    assert closed.json()["status"] == "closed"
    assert (
        await client.put(f"{EMPLOYER}/vacancies/{vacancy_id}", json=payload, headers=headers)
    ).status_code == 409

    stranger = await employer_headers(client, make_user)
    assert (
        await client.get(f"{EMPLOYER}/vacancies/{vacancy_id}", headers=stranger)
    ).status_code == 404

    monkeypatch.setitem(limits.PUBLISHED_VACANCY_LIMITS, TrustLevel.NEW, 1)
    assert (
        await client.post(f"{EMPLOYER}/vacancies", json=payload, headers=headers)
    ).status_code == 201
    over = await client.post(f"{EMPLOYER}/vacancies", json=payload, headers=headers)
    assert over.status_code == 429
    assert over.json()["error"]["code"] == "vacancy_limit_exceeded"


async def test_apply_discloses_contacts_and_shows_match(
    client: AsyncClient, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """Отклик с согласием открывает контакты компании; кандидат видит балл соответствия."""
    headers = await employer_headers(client, make_user)
    vacancy = await publish_vacancy(client, headers)
    candidate = await make_bank_candidate(db_session, skills=("python", "fastapi", "sql"))
    me = auth_headers(candidate.user)

    board = (await client.get("/api/v1/vacancies", headers=me)).json()
    assert board["can_apply"] is True
    item = next(entry for entry in board["items"] if entry["id"] == vacancy["id"])
    assert item["company"]["name"] == "Кедр Технологии"
    assert item["match"]["score"] > 0
    texts = [reason["text"] for reason in item["match"]["explanation"]]
    assert any(text.startswith("Закрывает 2 из 2") for text in texts)
    assert not any("вашу вилку" in text for text in texts)

    no_consent = await client.post(
        f"/api/v1/vacancies/{vacancy['id']}/applications",
        json={"cover_letter": "Хочу", "share_contacts": False},
        headers=me,
    )
    assert no_consent.status_code == 422
    applied = await client.post(
        f"/api/v1/vacancies/{vacancy['id']}/applications",
        json={"cover_letter": "Строил биллинг на FastAPI", "share_contacts": True},
        headers=me,
    )
    assert applied.status_code == 201, applied.text
    assert applied.json()["status"] == "submitted"
    again = await client.post(
        f"/api/v1/vacancies/{vacancy['id']}/applications",
        json={"share_contacts": True},
        headers=me,
    )
    assert again.status_code == 409

    disclosure = await db_session.scalar(
        select(ContactDisclosure).where(
            ContactDisclosure.candidate_id == uuid.UUID(candidate.profile_id)
        )
    )
    assert disclosure is not None and disclosure.reason is DisclosureReason.APPLICATION
    notifications = await db_session.scalars(
        select(Notification).where(Notification.kind == NotificationKind.APPLICATION_RECEIVED)
    )
    assert len(notifications.all()) == 1

    applications = (
        await client.get(f"{EMPLOYER}/vacancies/{vacancy['id']}/applications", headers=headers)
    ).json()
    assert len(applications) == 1
    assert applications[0]["contacts"]["full_name"] == candidate.full_name
    assert applications[0]["card"]["alias"]
    assert applications[0]["match_score"] == item["match"]["score"]
    listed = (await client.get(f"{EMPLOYER}/vacancies", headers=headers)).json()
    assert listed[0]["applications_new"] == 1


async def test_application_status_flow(
    client: AsyncClient, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """Просмотр, приглашение на собеседование с контактами, отказ с причиной, отзыв."""
    headers = await employer_headers(client, make_user)
    vacancy = await publish_vacancy(client, headers)
    first = await make_bank_candidate(db_session)
    second = await make_bank_candidate(db_session, telegram="second_candidate")
    for candidate in (first, second):
        response = await client.post(
            f"/api/v1/vacancies/{vacancy['id']}/applications",
            json={"share_contacts": True},
            headers=auth_headers(candidate.user),
        )
        assert response.status_code == 201
    applications = (
        await client.get(f"{EMPLOYER}/vacancies/{vacancy['id']}/applications", headers=headers)
    ).json()
    by_alias = {item["card"]["alias"]: item for item in applications}

    first_id = next(
        item["id"] for item in applications if item["contacts"]["full_name"] == first.full_name
    )
    opened = await client.get(f"{EMPLOYER}/applications/{first_id}", headers=headers)
    assert opened.json()["status"] == "viewed"
    mine = (
        await client.get("/api/v1/candidates/me/applications", headers=auth_headers(first.user))
    ).json()
    assert mine[0]["status"] == "viewed" and mine[0]["employer_contacts"] is None

    no_reason = await client.post(
        f"{EMPLOYER}/applications/{first_id}/decision",
        json={"status": "rejected"},
        headers=headers,
    )
    assert no_reason.status_code == 422
    interview = await client.post(
        f"{EMPLOYER}/applications/{first_id}/decision",
        json={"status": "interview", "message": "Созвонимся в четверг"},
        headers=headers,
    )
    assert interview.json()["status"] == "interview"
    mine = (
        await client.get("/api/v1/candidates/me/applications", headers=auth_headers(first.user))
    ).json()
    assert mine[0]["status"] == "interview"
    assert mine[0]["employer_contacts"]["telegram"] == "@kedr_hr"
    assert [event["status"] for event in mine[0]["events"]] == ["submitted", "viewed", "interview"]
    late = await client.post(
        f"/api/v1/candidates/me/applications/{first_id}/withdraw", headers=auth_headers(first.user)
    )
    assert late.status_code == 409

    second_id = next(item["id"] for item in by_alias.values() if item["id"] != first_id)
    assert (
        await client.post(
            f"/api/v1/candidates/me/applications/{second_id}/withdraw",
            headers=auth_headers(first.user),
        )
    ).status_code == 404
    withdrawn = await client.post(
        f"/api/v1/candidates/me/applications/{second_id}/withdraw",
        headers=auth_headers(second.user),
    )
    assert withdrawn.json()["status"] == "withdrawn"
    stranger = await employer_headers(client, make_user)
    assert (
        await client.get(f"{EMPLOYER}/applications/{first_id}", headers=stranger)
    ).status_code == 404


async def test_board_without_survey_and_closed_vacancy(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Без опроса откликаться рано; закрытая вакансия пропадает из ленты."""
    headers = await employer_headers(client, make_user)
    vacancy = await publish_vacancy(client, headers)
    newcomer = auth_headers(await make_user(UserRole.CANDIDATE))
    board = (await client.get("/api/v1/vacancies", headers=newcomer)).json()
    assert board["can_apply"] is False
    assert board["items"][0]["match"] is None
    early = await client.post(
        f"/api/v1/vacancies/{vacancy['id']}/applications",
        json={"share_contacts": True},
        headers=newcomer,
    )
    assert early.status_code == 409

    await client.post(f"{EMPLOYER}/vacancies/{vacancy['id']}/close", headers=headers)
    board = (await client.get("/api/v1/vacancies", headers=newcomer)).json()
    assert all(item["id"] != vacancy["id"] for item in board["items"])
    assert (
        await client.get(f"/api/v1/vacancies/{vacancy['id']}", headers=newcomer)
    ).status_code == 404
    assert (await client.get("/api/v1/vacancies", headers=headers)).status_code == 403
