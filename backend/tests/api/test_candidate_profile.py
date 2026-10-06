from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consent import Consent, ConsentType
from app.models.user import User, UserRole
from tests.helpers import auth_headers

PROFILE_URL = "/api/v1/candidates/me/profile"
UserFactory = Callable[..., Awaitable[User]]


async def _skill_ids(client: AsyncClient, *queries: str) -> list[int]:
    """Идентификаторы навыков по поисковым запросам к справочнику."""
    ids = []
    for query in queries:
        page = (await client.get("/api/v1/dictionaries/skills", params={"query": query})).json()
        ids.append(page["items"][0]["id"])
    return ids


def _profile_payload(**overrides: object) -> dict[str, object]:
    """Корректная анкета с возможностью переопределить поля."""
    payload: dict[str, object] = {
        "full_name": "  Иван Петров ",
        "phone": "+7 999 123-45-67",
        "telegram": "ivan_petrov",
        "city": "Казань",
        "about": "Пишу бэкенд на Python, люблю PostgreSQL и понятные API. " * 2,
        "experience_years": 3.5,
        "team_roles": ["developer", "mentor"],
        "soft_skills": ["Коммуникация", "коммуникация", " "],
        "work_formats": ["remote", "hybrid"],
        "relocation_ready": False,
        "salary_expectation_from": 250000,
        "salary_expectation_gross": True,
        "search_status": "active",
        "skills": [],
        "experiences": [
            {
                "company_name": "Кедр Технологии",
                "position": "Python-разработчик",
                "started_on": "2023-02-01",
                "ended_on": None,
                "description": "Платёжный шлюз",
            }
        ],
        "educations": [{"institution": "КФУ", "degree": "Бакалавр", "graduated_year": 2022}],
    }
    payload.update(overrides)
    return payload


async def test_profile_is_created_on_first_access(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Первое обращение создаёт пустой профиль с псевдонимом, не раскрывающим ПДн."""
    headers = auth_headers(await make_user())
    response = await client.get(PROFILE_URL, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["public_alias"]) == 4
    assert body["full_name"] is None
    assert body["category"] is None
    assert body["completeness"] == 0
    assert (await client.get(PROFILE_URL, headers=headers)).json()["public_alias"] == body[
        "public_alias"
    ]


async def test_only_candidates_have_candidate_profile(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Работодатель и методист не могут открыть кабинет кандидата."""
    for role in (UserRole.EMPLOYER, UserRole.METHODIST):
        response = await client.get(PROFILE_URL, headers=auth_headers(await make_user(role)))
        assert response.status_code == 403


async def test_profile_update_normalizes_and_replaces_lists(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Анкета сохраняется целиком: текст очищается, Telegram получает «@», списки заменяются."""
    headers = auth_headers(await make_user())
    python, sql = await _skill_ids(client, "питон", "постгрес")
    payload = _profile_payload(
        skills=[{"skill_id": python, "self_level": 4}, {"skill_id": sql, "self_level": 3}]
    )
    body = (await client.put(PROFILE_URL, json=payload, headers=headers)).json()
    assert body["full_name"] == "Иван Петров"
    assert body["telegram"] == "@ivan_petrov"
    assert body["soft_skills"] == ["Коммуникация"]
    assert {item["skill"]["slug"] for item in body["skills"]} == {"python", "postgresql"}
    assert body["experiences"][0]["company_name"] == "Кедр Технологии"
    assert body["salary_expectation_gross"] is True
    assert body["completeness"] < 100

    shorter = (
        await client.put(
            PROFILE_URL,
            json=_profile_payload(skills=[{"skill_id": sql, "self_level": 5}], experiences=[]),
            headers=headers,
        )
    ).json()
    assert [item["skill"]["slug"] for item in shorter["skills"]] == ["postgresql"]
    assert shorter["skills"][0]["self_level"] == 5
    assert shorter["experiences"] == []


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"phone": "звоните мне"}, "phone"),
        ({"telegram": "@ab"}, "telegram"),
        ({"experience_years": -1}, "experience_years"),
        ({"salary_expectation_from": 0}, "salary_expectation_from"),
        (
            {
                "experiences": [
                    {
                        "company_name": "X",
                        "position": "Y",
                        "started_on": "2024-05-01",
                        "ended_on": "2023-01-01",
                    }
                ]
            },
            "experiences.0",
        ),
    ],
)
async def test_profile_validation(
    client: AsyncClient, make_user: UserFactory, override: dict[str, object], field: str
) -> None:
    """Ошибки анкеты приходят с указанием поля."""
    headers = auth_headers(await make_user())
    response = await client.put(PROFILE_URL, json=_profile_payload(**override), headers=headers)
    assert response.status_code == 422
    assert any(item["field"].startswith(field) for item in response.json()["error"]["details"])


async def test_unknown_skill_is_rejected(client: AsyncClient, make_user: UserFactory) -> None:
    """Несуществующий навык отклоняется со списком неизвестных идентификаторов."""
    headers = auth_headers(await make_user())
    response = await client.put(
        PROFILE_URL, json=_profile_payload(skills=[{"skill_id": 999999}]), headers=headers
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"skill_ids": [999999]}


async def test_privacy_settings(client: AsyncClient, make_user: UserFactory) -> None:
    """По умолчанию раскрываются email и Telegram; хотя бы один канал обязателен."""
    headers = auth_headers(await make_user())
    defaults = (await client.get("/api/v1/candidates/me/privacy", headers=headers)).json()
    assert defaults["revealed_channels"] == ["email", "telegram"]
    assert defaults["show_company_names"] is False

    update = {
        "show_salary_expectation": False,
        "show_city": True,
        "show_company_names": True,
        "show_fsp_achievements": True,
        "revealed_channels": ["phone", "phone"],
    }
    saved = (await client.put("/api/v1/candidates/me/privacy", json=update, headers=headers)).json()
    assert saved["revealed_channels"] == ["phone"]
    assert saved["show_salary_expectation"] is False

    empty = await client.put(
        "/api/v1/candidates/me/privacy", json={**update, "revealed_channels": []}, headers=headers
    )
    assert empty.status_code == 422


async def test_bank_publication_consent_is_logged(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Согласие на публикацию даётся и отзывается; журнал сохраняет обе записи."""
    user = await make_user()
    headers = auth_headers(user)
    url = "/api/v1/candidates/me/consents/bank-publication"
    granted = (await client.put(url, json={"granted": True}, headers=headers)).json()
    assert granted["bank_publication"] is True
    assert granted["bank_publication_granted_at"] is not None
    assert (await client.put(url, json={"granted": True}, headers=headers)).status_code == 200

    revoked = (await client.put(url, json={"granted": False}, headers=headers)).json()
    assert revoked["bank_publication"] is False
    rows = (
        await db_session.scalars(
            select(Consent).where(
                Consent.user_id == user.id, Consent.consent_type == ConsentType.BANK_PUBLICATION
            )
        )
    ).all()
    assert len(rows) == 1 and rows[0].revoked_at is not None


async def test_onboarding_status_progresses(client: AsyncClient, make_user: UserFactory) -> None:
    """Шаги онбординга: профиль → опрос → выбор грейда; заявленный грейд не подтверждён."""
    headers = auth_headers(await make_user())
    status = (await client.get("/api/v1/candidates/me/status", headers=headers)).json()
    assert status["onboarding_step"] == "profile"
    assert status["grade_status"] == "not_declared"

    await client.put(PROFILE_URL, json=_profile_payload(), headers=headers)
    assert (await client.get("/api/v1/candidates/me/status", headers=headers)).json()[
        "onboarding_step"
    ] == "survey"

    specializations = (await client.get("/api/v1/dictionaries/specializations")).json()
    grades = (await client.get("/api/v1/dictionaries/grades")).json()
    backend = next(item for item in specializations if item["code"] == "backend")
    middle = next(item for item in grades if item["code"] == "middle")
    survey = await client.post(
        "/api/v1/assessment/surveys",
        json={
            "specialization_id": backend["id"],
            "claimed_grade_id": middle["id"],
            "primary_skill_ids": await _skill_ids(client, "питон"),
            "experience_years": 3,
        },
        headers=headers,
    )
    assert survey.status_code == 201
    status = (await client.get("/api/v1/candidates/me/status", headers=headers)).json()
    assert status["onboarding_step"] == "grade"
    assert status["grade_status"] == "unconfirmed"
    assert status["claimed_category"]["code"] == "backend-middle"
    assert status["category"] is None


async def test_profile_pdf(client: AsyncClient, make_user: UserFactory) -> None:
    """PDF-профиль скачивается файлом с понятным именем."""
    pytest.importorskip("weasyprint")
    headers = auth_headers(await make_user())
    await client.put(PROFILE_URL, json=_profile_payload(), headers=headers)
    response = await client.get("/api/v1/candidates/me/profile.pdf", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "scout-profile-" in response.headers["content-disposition"]
