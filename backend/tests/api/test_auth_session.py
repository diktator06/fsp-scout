from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_session import RefreshSession, SessionRevokeReason
from app.models.user import User, UserRole
from tests.helpers import DEFAULT_PASSWORD, auth_headers

LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/auth/me"
COOKIE_NAME = "fsp_scout_refresh"

UserFactory = Callable[..., Awaitable[User]]


async def _login(client: AsyncClient, user: User) -> dict[str, object]:
    """Входит пользователем и возвращает тело ответа."""
    response = await client.post(
        LOGIN_URL, json={"email": user.email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


async def test_login_returns_access_token_usable_for_me(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """После входа access-токен открывает `/auth/me`."""
    user = await make_user(UserRole.EMPLOYER)
    body = await _login(client, user)

    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["id"] == str(user.id)
    assert me.json()["role"] == "employer"


async def test_wrong_password_and_unknown_email_give_same_error(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Неверный пароль и несуществующий email неотличимы для клиента."""
    user = await make_user()
    wrong_password = await client.post(
        LOGIN_URL, json={"email": user.email, "password": "Wrong-123"}
    )
    unknown_email = await client.post(
        LOGIN_URL, json={"email": "nobody@example.com", "password": "Wrong-123"}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


async def test_disabled_account_cannot_log_in(client: AsyncClient, make_user: UserFactory) -> None:
    """Заблокированный аккаунт не может войти даже с верным паролем."""
    user = await make_user(active=False)
    response = await client.post(
        LOGIN_URL, json={"email": user.email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_disabled"


async def test_me_requires_valid_bearer_token(client: AsyncClient) -> None:
    """Без токена или с испорченным токеном `/auth/me` отвечает 401."""
    assert (await client.get(ME_URL)).status_code == 401
    broken = await client.get(ME_URL, headers={"Authorization": "Bearer broken.token.value"})
    assert broken.status_code == 401
    assert broken.json()["error"]["code"] == "invalid_token"


async def test_refresh_rotates_token_and_detects_reuse(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Обновление выдаёт новый refresh-токен, а повтор старого отзывает всё семейство.

    После обнаруженного повтора не работает и самый свежий токен этой цепочки.
    """
    user = await make_user()
    await _login(client, user)
    first_cookie = client.cookies.get(COOKIE_NAME, path="/api/v1/auth")
    assert first_cookie

    refreshed = await client.post(REFRESH_URL)
    assert refreshed.status_code == 200, refreshed.text
    second_cookie = client.cookies.get(COOKIE_NAME, path="/api/v1/auth")
    assert second_cookie and second_cookie != first_cookie

    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, first_cookie, path="/api/v1/auth")
    reuse = await client.post(REFRESH_URL)
    assert reuse.status_code == 401

    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, second_cookie, path="/api/v1/auth")
    after_reuse = await client.post(REFRESH_URL)
    assert after_reuse.status_code == 401

    sessions = (
        await db_session.scalars(select(RefreshSession).where(RefreshSession.user_id == user.id))
    ).all()
    assert {item.revoke_reason for item in sessions} == {
        SessionRevokeReason.ROTATED,
        SessionRevokeReason.REUSE_DETECTED,
    }


async def test_refresh_without_cookie_is_unauthorized(client: AsyncClient) -> None:
    """Обновление без cookie невозможно."""
    response = await client.post(REFRESH_URL)
    assert response.status_code == 401


async def test_logout_revokes_session_and_clears_cookie(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Выход отзывает refresh-сессию: обновить её больше нельзя."""
    user = await make_user()
    await _login(client, user)
    cookie = client.cookies.get(COOKIE_NAME, path="/api/v1/auth")

    response = await client.post(LOGOUT_URL)
    assert response.status_code == 204
    assert 'fsp_scout_refresh=""' in response.headers["set-cookie"]

    client.cookies.set(COOKIE_NAME, cookie or "", path="/api/v1/auth")
    assert (await client.post(REFRESH_URL)).status_code == 401
    assert (await client.post(LOGOUT_URL)).status_code == 204


async def test_role_comes_from_database_not_from_token(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Если аккаунт заблокировали, уже выданный access-токен перестаёт работать сразу."""
    user = await make_user()
    headers = auth_headers(user)
    assert (await client.get(ME_URL, headers=headers)).status_code == 200

    user.is_active = False
    await db_session.commit()
    response = await client.get(ME_URL, headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_disabled"
