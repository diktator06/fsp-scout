from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_session import EmailVerificationToken
from app.models.consent import Consent, ConsentType
from app.models.user import User
from tests.helpers import DEFAULT_PASSWORD, RecordingMailer, unique_email

REGISTER_URL = "/api/v1/auth/register"
VERIFY_URL = "/api/v1/auth/verify-email"
LOGIN_URL = "/api/v1/auth/login"
RESEND_URL = "/api/v1/auth/resend-verification"


async def _register(client: AsyncClient, email: str, role: str = "candidate") -> dict[str, object]:
    """Регистрирует пользователя через API и возвращает тело ответа."""
    response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "password": DEFAULT_PASSWORD,
            "role": role,
            "accept_personal_data_processing": True,
        },
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


async def test_registration_creates_unverified_user_consent_and_sends_email(
    client: AsyncClient, mailer: RecordingMailer, db_session: AsyncSession
) -> None:
    """Регистрация создаёт неподтверждённый аккаунт, пишет согласие и отправляет письмо.

    В письме есть ссылка подтверждения на адрес фронтенда.
    """
    email = unique_email("candidate")
    body = await _register(client, email.upper())

    assert body["email"] == email
    assert body["verification_email_sent"] is True
    user = await db_session.scalar(select(User).where(User.email == email))
    assert user is not None and not user.is_email_verified
    consent = await db_session.scalar(select(Consent).where(Consent.user_id == user.id))
    assert consent is not None
    assert consent.consent_type == ConsentType.PERSONAL_DATA_PROCESSING

    assert len(mailer.outbox) == 1
    letter = mailer.outbox[0]
    assert letter.to == email
    assert "http://scout.test/auth/verify?token=" in letter.text_body
    assert letter.html_body and "Подтвердить email" in letter.html_body


async def test_duplicate_email_is_rejected_with_conflict(client: AsyncClient) -> None:
    """Повторная регистрация того же адреса (в любом регистре) даёт 409."""
    email = unique_email()
    await _register(client, email)

    response = await client.post(
        REGISTER_URL,
        json={
            "email": email.upper(),
            "password": DEFAULT_PASSWORD,
            "role": "employer",
            "accept_personal_data_processing": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_registered"


async def test_registration_validation_errors_are_field_level(client: AsyncClient) -> None:
    """Ошибки валидации приходят списком полей с понятными сообщениями."""
    response = await client.post(
        REGISTER_URL,
        json={
            "email": "not-an-email",
            "password": "onlyletters",
            "role": "methodist",
            "accept_personal_data_processing": False,
        },
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "request_validation_error"
    fields = {item["field"] for item in error["details"]}
    assert {"email", "password", "role", "accept_personal_data_processing"} <= fields
    password_error = next(item for item in error["details"] if item["field"] == "password")
    assert password_error["message"].startswith("Пароль должен")


async def test_login_is_forbidden_until_email_is_verified(client: AsyncClient) -> None:
    """До подтверждения email вход запрещён с отдельным кодом ошибки."""
    email = unique_email()
    await _register(client, email)

    response = await client.post(LOGIN_URL, json={"email": email, "password": DEFAULT_PASSWORD})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "email_not_verified"


async def test_verification_link_confirms_email_and_opens_session(
    client: AsyncClient, mailer: RecordingMailer
) -> None:
    """Переход по ссылке подтверждает email, выдаёт токены и ставит refresh-cookie."""
    email = unique_email()
    await _register(client, email, role="employer")

    response = await client.post(VERIFY_URL, json={"token": mailer.last_verification_token()})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == email
    assert body["user"]["role"] == "employer"
    assert body["user"]["is_email_verified"] is True
    set_cookie = response.headers["set-cookie"]
    assert "fsp_scout_refresh=" in set_cookie
    assert "HttpOnly" in set_cookie and "SameSite=strict" in set_cookie
    assert "Path=/api/v1/auth" in set_cookie

    login = await client.post(LOGIN_URL, json={"email": email, "password": DEFAULT_PASSWORD})
    assert login.status_code == 200


async def test_verification_link_works_only_once(
    client: AsyncClient, mailer: RecordingMailer
) -> None:
    """Повторный переход по той же ссылке отклоняется с причиной `used`."""
    await _register(client, unique_email())
    token = mailer.last_verification_token()
    assert (await client.post(VERIFY_URL, json={"token": token})).status_code == 200

    again = await client.post(VERIFY_URL, json={"token": token})
    assert again.status_code == 400
    assert again.json()["error"]["details"] == {"reason": "used"}


async def test_expired_verification_link_is_rejected(
    client: AsyncClient, mailer: RecordingMailer, db_session: AsyncSession
) -> None:
    """Просроченная ссылка не подтверждает email."""
    await _register(client, unique_email())
    await db_session.execute(
        update(EmailVerificationToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.commit()

    response = await client.post(VERIFY_URL, json={"token": mailer.last_verification_token()})
    assert response.status_code == 400
    assert response.json()["error"]["details"] == {"reason": "expired"}


async def test_unknown_verification_token_is_rejected(client: AsyncClient) -> None:
    """Выдуманный токен не принимается."""
    response = await client.post(VERIFY_URL, json={"token": "x" * 43})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_verification_token"


async def test_resend_invalidates_previous_link(
    client: AsyncClient, mailer: RecordingMailer
) -> None:
    """Повторное письмо гасит старую ссылку: действует только последняя."""
    email = unique_email()
    await _register(client, email)
    first_token = mailer.last_verification_token()

    response = await client.post(RESEND_URL, json={"email": email})
    assert response.status_code == 202
    assert len(mailer.outbox) == 2
    second_token = mailer.last_verification_token()
    assert second_token != first_token

    assert (await client.post(VERIFY_URL, json={"token": first_token})).status_code == 400
    assert (await client.post(VERIFY_URL, json={"token": second_token})).status_code == 200


async def test_resend_does_not_reveal_unknown_accounts(
    client: AsyncClient, mailer: RecordingMailer
) -> None:
    """Для несуществующего адреса ответ тот же, что и для существующего, письмо не уходит."""
    response = await client.post(RESEND_URL, json={"email": unique_email("ghost")})
    assert response.status_code == 202
    assert mailer.outbox == []
