import hashlib
import hmac
import json
import secrets
from typing import Any

EVENT_HEADER = "X-Scout-Event"
EVENT_ID_HEADER = "X-Scout-Event-Id"
DELIVERY_HEADER = "X-Scout-Delivery"
TIMESTAMP_HEADER = "X-Scout-Timestamp"
SIGNATURE_HEADER = "X-Scout-Signature"
SIGNATURE_PREFIX = "sha256="
SECRET_PREFIX = "whsec_"
REPLAY_TOLERANCE_SECONDS = 300


def new_secret() -> str:
    """Секрет подписи: 256 бит случайности с узнаваемым префиксом."""
    return SECRET_PREFIX + secrets.token_urlsafe(32)


def secret_hint(secret: str) -> str:
    """Подсказка, по которой секрет узнаётся, но не восстанавливается."""
    return f"{secret[: len(SECRET_PREFIX) + 4]}…{secret[-4:]}"


def encode_payload(payload: dict[str, Any]) -> bytes:
    """Тело запроса. Подпись считается именно от этих байтов, поэтому кодируем один раз."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def sign(secret: str, timestamp: int, body: bytes) -> str:
    """Подпись HMAC-SHA256 от «метка времени.тело».

    Метка времени входит в подпись, поэтому перехваченный запрос нельзя повторить
    позже: получатель отвергает подписи старше пяти минут.
    """
    message = str(timestamp).encode() + b"." + body
    digest = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return SIGNATURE_PREFIX + digest


def verify(secret: str, timestamp: str, body: bytes, signature: str, now: int) -> bool:
    """Проверка подписи на стороне получателя — так её проверяет и песочница ATS."""
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs(now - sent_at) > REPLAY_TOLERANCE_SECONDS:
        return False
    return hmac.compare_digest(sign(secret, sent_at, body), signature)
