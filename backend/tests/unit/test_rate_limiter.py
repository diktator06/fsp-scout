from collections.abc import Iterator

import pytest
from starlette.requests import Request

from app.api.rate_limit import RateLimiter
from app.core.config import get_settings
from app.core.exceptions import RateLimitExceededError


def _request(path: str = "/api/v1/auth/login", host: str = "10.0.0.1") -> Request:
    """Минимальный ASGI-запрос с заданным путём и адресом клиента."""
    return Request(
        {"type": "http", "method": "POST", "path": path, "client": (host, 50000), "headers": []}
    )


@pytest.fixture
def rate_limit_enabled() -> Iterator[None]:
    """Временно включает ограничение частоты: в остальных тестах оно выключено."""
    settings = get_settings()
    previous = settings.rate_limit_enabled
    settings.rate_limit_enabled = True
    yield
    settings.rate_limit_enabled = previous


@pytest.mark.usefixtures("rate_limit_enabled")
async def test_limiter_blocks_after_limit_and_reports_retry_after() -> None:
    """После исчерпания лимита запрос отклоняется с подсказкой, через сколько повторить."""
    limiter = RateLimiter(limit=2, window_seconds=60)
    await limiter(_request())
    await limiter(_request())

    with pytest.raises(RateLimitExceededError) as error:
        await limiter(_request())
    assert 0 < error.value.details["retry_after_seconds"] <= 60


@pytest.mark.usefixtures("rate_limit_enabled")
async def test_limiter_counts_clients_separately() -> None:
    """Лимит считается отдельно для каждого IP: чужие запросы не блокируют клиента."""
    limiter = RateLimiter(limit=1, window_seconds=60)
    await limiter(_request(host="10.0.0.1"))
    await limiter(_request(host="10.0.0.2"))

    with pytest.raises(RateLimitExceededError):
        await limiter(_request(host="10.0.0.1"))


async def test_limiter_is_noop_when_disabled() -> None:
    """При выключенной настройке ограничитель ничего не блокирует."""
    limiter = RateLimiter(limit=1, window_seconds=60)
    for _ in range(5):
        await limiter(_request())
