import asyncio
import hashlib
import secrets
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings
from app.core.exceptions import InvalidTokenError

_password_hasher = PasswordHasher()
_DUMMY_PASSWORD_HASH = _password_hasher.hash("timing-equalizer-not-a-real-password")
PASSWORD_HASH_CONCURRENCY = 2
_password_slots = threading.BoundedSemaphore(PASSWORD_HASH_CONCURRENCY)


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """Проверенное содержимое access-токена."""

    user_id: uuid.UUID
    role: str
    email: str
    email_verified: bool
    expires_at: datetime


def hash_password(password: str) -> str:
    """Хеширует пароль алгоритмом argon2id (параметры по умолчанию argon2-cffi)."""
    return _password_hasher.hash(password)


def _bounded[Result](func: Callable[..., Result], *args: Any) -> Result:
    """Выполняет функцию argon2, заняв один из слотов процесса."""
    with _password_slots:
        return func(*args)


async def hash_password_async(password: str) -> str:
    """Хеш argon2id в отдельном потоке, не больше двух одновременно на процесс.

    argon2id нарочно дорогой: десятки миллисекунд CPU и 64 МБ памяти на хеш. В цикле
    событий он остановил бы все остальные запросы процесса, а без ограничения всплеск
    входов занял бы все ядра и память контейнера. argon2-cffi отпускает GIL, поэтому
    поток считает хеш параллельно с обработкой других запросов; лишние ждут слота.
    """
    return await asyncio.to_thread(_bounded, hash_password, password)


async def verify_password_async(password: str, password_hash: str | None) -> bool:
    """Проверка пароля в отдельном потоке с тем же ограничением, что и хеширование."""
    return await asyncio.to_thread(_bounded, verify_password, password, password_hash)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Проверяет пароль против сохранённого хеша.

    Если хеша нет (пользователь не найден или вошёл через внешний IdP), всё равно
    выполняем проверку против фиктивного хеша. Время ответа тогда не выдаёт,
    существует ли аккаунт с таким email.
    """
    try:
        _password_hasher.verify(password_hash or _DUMMY_PASSWORD_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return password_hash is not None


def password_needs_rehash(password_hash: str) -> bool:
    """Сообщает, что хеш создан со старыми параметрами и его стоит пересчитать при входе."""
    return _password_hasher.check_needs_rehash(password_hash)


def generate_opaque_token() -> str:
    """Генерирует случайный токен для ссылок подтверждения и refresh-сессий (256 бит)."""
    return secrets.token_urlsafe(32)


def hash_opaque_token(token: str) -> str:
    """Возвращает SHA-256 от токена.

    В базе храним только хеш: утечка дампа не даёт ни войти в чужую сессию,
    ни подтвердить чужой email. Соль не нужна, потому что сам токен случайный и длинный.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    *,
    user_id: uuid.UUID,
    role: str,
    email: str,
    email_verified: bool,
    settings: Settings,
    now: datetime | None = None,
) -> tuple[str, int]:
    """Выпускает access-JWT и возвращает его вместе со сроком жизни в секундах.

    Набор claims повторяет Keycloak (`sub`, `email_verified`, `preferred_username`,
    `realm_access.roles`). Когда авторизация переедет на ФСП ID, фронтенду и проверкам
    ролей не придётся меняться.
    """
    issued_at = now or datetime.now(UTC)
    lifetime = timedelta(minutes=settings.access_token_ttl_minutes)
    payload: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + lifetime,
        "jti": uuid.uuid4().hex,
        "typ": "Bearer",
        "email": email,
        "email_verified": email_verified,
        "preferred_username": email,
        "realm_access": {"roles": [role]},
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str, settings: Settings) -> AccessTokenClaims:
    """Проверяет подпись, срок, издателя и аудиторию access-токена.

    Подробности о причине отказа наружу не отдаём, только различаем «истёк» и
    «недействителен»: по первому фронтенд пробует обновить сессию.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError(
            "Срок действия токена истёк", details={"reason": "expired"}
        ) from exc
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(details={"reason": "malformed"}) from exc

    roles = payload.get("realm_access", {}).get("roles") or []
    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError as exc:
        raise InvalidTokenError(details={"reason": "malformed"}) from exc
    if not roles:
        raise InvalidTokenError(details={"reason": "malformed"})

    return AccessTokenClaims(
        user_id=user_id,
        role=str(roles[0]),
        email=str(payload.get("email", "")),
        email_verified=bool(payload.get("email_verified", False)),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
    )
