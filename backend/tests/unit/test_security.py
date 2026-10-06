import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import InvalidTokenError
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_opaque_token,
    hash_opaque_token,
    hash_password,
    verify_password,
)


def test_password_hash_uses_argon2id_and_verifies() -> None:
    """Пароль хешируется argon2id и проверяется, неверный пароль не проходит."""
    password_hash = hash_password("Correct-Horse-42")

    assert password_hash.startswith("$argon2id$")
    assert verify_password("Correct-Horse-42", password_hash)
    assert not verify_password("correct-horse-42", password_hash)


def test_verify_password_without_hash_is_always_false() -> None:
    """Без хеша (пользователь не найден) проверка не проходит, но и не падает."""
    assert not verify_password("anything", None)
    assert not verify_password("anything", "not-a-hash")


def test_opaque_token_is_random_and_hash_is_stable() -> None:
    """Токены не повторяются, а хеш одного токена детерминирован."""
    first, second = generate_opaque_token(), generate_opaque_token()

    assert first != second
    assert len(first) >= 40
    assert hash_opaque_token(first) == hash_opaque_token(first)
    assert hash_opaque_token(first) != hash_opaque_token(second)


def test_access_token_roundtrip_has_keycloak_compatible_claims() -> None:
    """Access-токен содержит роль в `realm_access.roles`, как в Keycloak, и успешно разбирается."""
    settings = get_settings()
    user_id = uuid.uuid4()
    token, expires_in = create_access_token(
        user_id=user_id,
        role="employer",
        email="hr@example.com",
        email_verified=True,
        settings=settings,
    )

    raw = jwt.decode(token, options={"verify_signature": False})
    claims = decode_access_token(token, settings)

    assert raw["realm_access"] == {"roles": ["employer"]}
    assert raw["preferred_username"] == "hr@example.com"
    assert expires_in == settings.access_token_ttl_minutes * 60
    assert claims.user_id == user_id
    assert claims.role == "employer"
    assert claims.email_verified is True


def test_expired_access_token_is_rejected_with_reason() -> None:
    """Истёкший токен отклоняется с причиной `expired`: по ней фронтенд обновляет сессию."""
    settings = get_settings()
    token, _ = create_access_token(
        user_id=uuid.uuid4(),
        role="candidate",
        email="c@example.com",
        email_verified=True,
        settings=settings,
        now=datetime.now(UTC) - timedelta(hours=2),
    )

    with pytest.raises(InvalidTokenError) as error:
        decode_access_token(token, settings)
    assert error.value.details == {"reason": "expired"}


def test_tampered_or_foreign_token_is_rejected() -> None:
    """Токен с чужой подписью или чужой аудиторией не принимается."""
    settings = get_settings()
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "iss": settings.jwt_issuer, "aud": settings.jwt_audience},
        "another-secret-that-is-long-enough-123",
        algorithm="HS256",
    )
    foreign_audience = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "iss": settings.jwt_issuer,
            "aud": "someone-else",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "realm_access": {"roles": ["candidate"]},
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    for token in (forged, foreign_audience, "not.a.jwt"):
        with pytest.raises(InvalidTokenError):
            decode_access_token(token, settings)
