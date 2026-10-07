from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserRole
from tests.api.test_employer_matching import COMPANY, employer_headers
from tests.api.test_invitations import INVITATIONS, UserFactory, offer
from tests.api.test_vacancies import publish_vacancy, vacancy_payload
from tests.factories import make_bank_candidate
from tests.helpers import auth_headers

MODERATION = "/api/v1/moderation"


async def test_inn_must_pass_checksum(client: AsyncClient, make_user: UserFactory) -> None:
    """Выдуманный ИНН не проходит: это первый фильтр против фиктивного работодателя."""
    headers = auth_headers(await make_user(UserRole.EMPLOYER))
    bad = await client.put(
        "/api/v1/employer/company", json={**COMPANY, "inn": "7701234567"}, headers=headers
    )
    assert bad.status_code == 422
    good = await client.put("/api/v1/employer/company", json=COMPANY, headers=headers)
    assert good.status_code == 200


async def test_complaints_restrict_company_until_moderation(
    client: AsyncClient, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """Три жалобы разных кандидатов ставят компанию на проверку; модератор снимает ограничение."""
    employer = await employer_headers(client, make_user)
    vacancy = await publish_vacancy(client, employer)
    complaint = {
        "target_type": "vacancy",
        "target_id": vacancy["id"],
        "reason": "fake_offer",
        "comment": "Просили оплатить обучение",
    }
    candidates = [auth_headers(await make_user(UserRole.CANDIDATE)) for _ in range(3)]
    first = await client.post("/api/v1/complaints", json=complaint, headers=candidates[0])
    assert first.status_code == 201, first.text
    again = await client.post("/api/v1/complaints", json=complaint, headers=candidates[0])
    assert again.status_code == 409
    for headers in candidates[1:]:
        assert (
            await client.post("/api/v1/complaints", json=complaint, headers=headers)
        ).status_code == 201

    company = (await client.get("/api/v1/employer/company", headers=employer)).json()
    assert company["company"]["restricted_at"] is not None
    blocked = await client.post(
        "/api/v1/employer/vacancies", json=await vacancy_payload(client, employer), headers=employer
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "company_restricted"
    candidate = await make_bank_candidate(db_session)
    invite = await client.post(INVITATIONS, json=offer(candidate), headers=employer)
    assert invite.status_code == 403

    assert (await client.get(f"{MODERATION}/complaints", headers=employer)).status_code == 403
    methodist = auth_headers(await make_user(UserRole.METHODIST))
    queue = (await client.get(f"{MODERATION}/complaints", headers=methodist)).json()
    assert len(queue) == 3 and queue[0]["target_title"].startswith("Вакансия")
    companies = (await client.get(f"{MODERATION}/companies", headers=methodist)).json()
    assert companies[0]["id"] == company["company"]["id"]
    assert companies[0]["complaints_open"] == 3

    confirmed = await client.post(
        f"{MODERATION}/complaints/{queue[0]['id']}/resolve",
        json={"status": "confirmed", "note": "Проверили переписку"},
        headers=methodist,
    )
    assert confirmed.json()["status"] == "confirmed"
    lifted = await client.post(
        f"{MODERATION}/companies/{company['company']['id']}/lift", headers=methodist
    )
    assert lifted.json()["restricted_at"] is None
    assert lifted.json()["reputation"]["complaints_confirmed"] == 1
    assert (
        await client.post(
            "/api/v1/employer/vacancies",
            json=await vacancy_payload(client, employer),
            headers=employer,
        )
    ).status_code == 201

    board = (await client.get("/api/v1/vacancies", headers=candidates[0])).json()
    brief = board["items"][0]["company"]
    assert brief["under_review"] is False
    assert "жалоб: 1" in brief["reputation"]["summary"]


async def test_complaint_only_on_own_invitation(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """На чужое приглашение пожаловаться нельзя — его для кандидата нет."""
    headers = auth_headers(await make_user(UserRole.CANDIDATE))
    response = await client.post(
        "/api/v1/complaints",
        json={
            "target_type": "invitation",
            "target_id": "00000000-0000-0000-0000-000000000001",
            "reason": "spam",
        },
        headers=headers,
    )
    assert response.status_code == 404


async def test_market_check_flags_dream_salary(
    client: AsyncClient, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """Вилка в разы выше рынка подсвечивается работодателю и модератору."""
    for _ in range(3):
        await make_bank_candidate(db_session, salary=250_000)
    employer = await employer_headers(client, make_user)
    payload = await vacancy_payload(client, employer)
    normal = await client.post("/api/v1/employer/vacancies", json=payload, headers=employer)
    assert normal.json()["market_check"]["status"] == "ok"
    dream = await client.post(
        "/api/v1/employer/vacancies",
        json={**payload, "title": "Мечта", "salary_from": 600_000, "salary_to": 900_000},
        headers=employer,
    )
    check = dream.json()["market_check"]
    assert check["status"] == "suspicious" and check["median"] == 250_000
    methodist = auth_headers(await make_user(UserRole.METHODIST))
    companies = (await client.get(f"{MODERATION}/companies", headers=methodist)).json()
    flagged = next(item for item in companies if item["suspicious_vacancies"])
    assert flagged["suspicious_vacancies"] == ["Мечта"]
