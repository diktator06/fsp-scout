import json

from httpx import AsyncClient
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import AssessmentSession
from app.models.audit import AuditLog
from app.models.candidate import CandidateProfile
from app.models.employer import Company
from app.models.integration import WebhookDelivery
from app.models.invitation import ContactDisclosure, Invitation
from app.models.user import User, UserRole
from tests.api.test_employer_matching import employer_headers
from tests.api.test_integrations import BASE
from tests.api.test_invitations import INBOX, INVITATIONS, UserFactory, offer
from tests.factories import make_bank_candidate
from tests.helpers import RecordingMailer, auth_headers

ACCOUNT = "/api/v1/account"


async def _count(session: AsyncSession, statement: Select[tuple[int]]) -> int:
    """Число строк по запросу count."""
    return int(await session.scalar(statement) or 0)


async def test_export_contains_everything_but_secrets(
    client: AsyncClient, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """Выгрузка: профиль, тест, приглашение, раскрытие контактов — без хешей и ключей ответов."""
    candidate = await make_bank_candidate(db_session)
    employer = await employer_headers(client, make_user)
    invitation = (await client.post(INVITATIONS, json=offer(candidate), headers=employer)).json()
    headers = auth_headers(candidate.user)
    await client.post(f"{INBOX}/{invitation['id']}/accept", headers=headers)

    response = await client.get(f"{ACCOUNT}/personal-data", headers=headers)
    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    body = response.json()
    sections = body["sections"]
    assert body["role"] == "candidate" and body["user_id"] == str(candidate.user.id)
    assert sections["account"][0]["email"] == candidate.user.email
    assert sections["profile"][0]["full_name"] == candidate.full_name
    assert sections["assessment_sessions"] and sections["assessment_items"]
    assert sections["grade_history"] and sections["consents"]
    assert sections["invitations"][0]["id"] == invitation["id"]
    assert sections["contact_disclosures"], "кандидат видит, кому открыты его контакты"
    assert body["counters"]["shortlist_appearances"] >= 0
    raw = json.dumps(body, ensure_ascii=False)
    for secret in ("password_hash", "token_hash", "answer_key", "instance_seed", "seed_salt"):
        assert secret not in raw

    employer_export = (await client.get(f"{ACCOUNT}/personal-data", headers=employer)).json()
    assert employer_export["sections"]["recruiter"] and employer_export["sections"]["company"]
    assert "profile" not in employer_export["sections"]


async def test_candidate_deletion_destroys_data_and_leaves_only_audit(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user: UserFactory,
    mailer: RecordingMailer,
) -> None:
    """Удаление: подтверждение email, каскад по всем данным, копии событий ATS, письмо, аудит."""
    candidate = await make_bank_candidate(db_session)
    employer = await employer_headers(client, make_user)
    await client.post(f"{BASE}/sandbox", headers=employer)
    invitation = (await client.post(INVITATIONS, json=offer(candidate), headers=employer)).json()
    headers = auth_headers(candidate.user)
    await client.post(f"{INBOX}/{invitation['id']}/accept", headers=headers)
    copies = select(func.count()).select_from(WebhookDelivery)
    assert await _count(db_session, copies) == 1

    wrong = await client.request(
        "DELETE", ACCOUNT, json={"confirm_email": "other@example.com"}, headers=headers
    )
    assert wrong.status_code == 422
    deleted = await client.request(
        "DELETE", ACCOUNT, json={"confirm_email": candidate.user.email.upper()}, headers=headers
    )
    assert deleted.status_code == 204, deleted.text

    user_id = candidate.user.id
    assert await db_session.get(User, user_id) is None
    profile = select(func.count()).select_from(CandidateProfile)
    assert await _count(db_session, profile.where(CandidateProfile.user_id == user_id)) == 0
    for model in (AssessmentSession, Invitation, ContactDisclosure):
        statement = select(func.count()).select_from(model)
        assert (
            await _count(db_session, statement.where(model.candidate_id == candidate.profile_id))
            == 0
        )
    assert await _count(db_session, copies) == 0

    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "account_deleted"))
    assert audit is not None and audit.actor_user_id is None
    assert audit.meta["removed"]["assessment_sessions"] >= 1
    assert audit.meta["removed"]["ats_event_copies"] == 1
    assert candidate.user.email not in json.dumps(audit.meta, ensure_ascii=False)
    assert mailer.outbox[-1].to == candidate.user.email
    assert "удалён" in mailer.outbox[-1].subject

    gone = await client.get("/api/v1/auth/me", headers=headers)
    assert gone.status_code == 401


async def test_last_recruiter_takes_company_with_them(
    client: AsyncClient, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """Единственный рекрутер удаляет аккаунт — компания и её приглашения удаляются тоже."""
    candidate = await make_bank_candidate(db_session)
    recruiter = await make_user(UserRole.EMPLOYER)
    employer = auth_headers(recruiter)
    company = await client.put(
        "/api/v1/employer/company",
        json={
            "name": "Кедр Технологии",
            "inn": "7701234560",
            "website": "kedr.example",
            "description": "Платёжный шлюз для малого бизнеса",
            "size": "medium",
            "city": "Москва",
            "contact_email": "hr@kedr.example",
            "contact_telegram": "kedr_hr",
            "recruiter_full_name": "Мария Соколова",
            "recruiter_position": "HR-партнёр",
        },
        headers=employer,
    )
    assert company.status_code == 200, company.text
    await client.post(INVITATIONS, json=offer(candidate), headers=employer)

    deleted = await client.request(
        "DELETE", ACCOUNT, json={"confirm_email": recruiter.email}, headers=employer
    )
    assert deleted.status_code == 204, deleted.text
    assert await _count(db_session, select(func.count()).select_from(Company)) == 0
    inbox = await client.get(INBOX, headers=auth_headers(candidate.user))
    assert inbox.status_code == 200 and inbox.json() == []
