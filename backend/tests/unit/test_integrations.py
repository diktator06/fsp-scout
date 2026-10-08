from datetime import UTC, datetime

import pytest

from app.core.exceptions import UnsafeWebhookUrlError
from app.models.invitation import DisclosureReason
from app.schemas.integration import AtsCandidate
from app.services.integrations import signing
from app.services.integrations.export import render
from app.services.integrations.url_guard import ensure_public_destination

NOW = 1_791_400_000


def test_signature_roundtrip_and_tampering() -> None:
    """Подпись сходится только для того же тела, секрета и свежей метки времени."""
    secret = signing.new_secret()
    body = signing.encode_payload({"type": "ping", "data": {"text": "Привет"}})
    signature = signing.sign(secret, NOW, body)
    assert signature.startswith("sha256=")
    assert signing.verify(secret, str(NOW), body, signature, NOW + 10)
    assert not signing.verify(secret, str(NOW), body + b" ", signature, NOW)
    assert not signing.verify(signing.new_secret(), str(NOW), body, signature, NOW)
    assert not signing.verify(secret, str(NOW), body, signature, NOW + 301)
    assert not signing.verify(secret, "вчера", body, signature, NOW)
    hint = signing.secret_hint(secret)
    assert hint.startswith("whsec_") and secret not in hint


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/api",
        "http://10.0.0.5/hook",
        "http://169.254.169.254/latest/meta-data",
        "http://localhost/hook",
        "http://db.internal/hook",
        "http://[::1]/hook",
        "ftp://93.184.215.14/hook",
    ],
)
async def test_private_destinations_are_blocked(url: str) -> None:
    """SSRF: внутренние адреса и чужие схемы отвергаются."""
    with pytest.raises(UnsafeWebhookUrlError):
        await ensure_public_destination(url, allow_private=False, require_https=False)


async def test_public_destination_and_https_policy() -> None:
    """Публичный адрес проходит; в production без HTTPS — нет; на стенде можно разрешить всё."""
    await ensure_public_destination(
        "https://93.184.215.14/hook", allow_private=False, require_https=True
    )
    with pytest.raises(UnsafeWebhookUrlError):
        await ensure_public_destination(
            "http://93.184.215.14/hook", allow_private=False, require_https=True
        )
    await ensure_public_destination(
        "http://localhost:9000/hook", allow_private=True, require_https=False
    )


def _candidate() -> AtsCandidate:
    """Кандидат для выгрузки."""
    return AtsCandidate(
        candidate_id="0b6b1f9e-6a43-4c1e-9d55-2d6d2c1e0a11",
        alias="Кандидат К-17",
        full_name="Иван Петров",
        email="ivan@example.com",
        phone=None,
        telegram="ivan_bank_test",
        city="Москва",
        specialization="Backend-разработка",
        grade="Middle",
        category="Backend-разработчик · Middle",
        grade_confirmed=True,
        verified_score=71.5,
        experience_years=3.5,
        skills=["Python", "FastAPI"],
        profile_url="http://scout.test/e/candidates/0b6b1f9e",
        source=DisclosureReason.APPLICATION,
        source_id=None,
        disclosed_at=datetime(2026, 10, 7, tzinfo=UTC),
    )


def test_export_formats() -> None:
    """CSV открывается в Excel (BOM), навыки в одной ячейке; JSON — со счётчиком."""
    now = datetime(2026, 10, 8, tzinfo=UTC)
    csv_file = render([_candidate()], "csv", now)
    assert csv_file.filename == "scout-candidates-2026-10-08.csv"
    text = csv_file.content.decode("utf-8-sig")
    header, row = text.strip().splitlines()
    assert header.startswith("candidate_id,full_name,email,phone,telegram")
    assert "Иван Петров" in row and "Python; FastAPI" in row and ",true," in row
    json_file = render([_candidate()], "json", now)
    assert json_file.media_type == "application/json"
    assert b'"count": 1' in json_file.content
