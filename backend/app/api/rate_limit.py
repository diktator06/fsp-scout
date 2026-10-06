import math
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import get_settings
from app.core.exceptions import RateLimitExceededError


def client_ip(request: Request) -> str | None:
    """IP клиента. За nginx uvicorn запускается с `--proxy-headers`, поэтому адрес уже реальный."""
    return request.client.host if request.client else None


class RateLimiter:
    """Ограничитель частоты запросов «скользящее окно» в памяти процесса.

    Ключ — маршрут плюс IP клиента. Этого достаточно для одного процесса uvicorn
    (так и запускаем MVP). При горизонтальном масштабировании хранилище переедет
    в Redis, а интерфейс зависимости останется прежним.
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        """Задаёт лимит: не больше `limit` запросов за `window_seconds` секунд."""
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, request: Request) -> None:
        """Пропускает запрос или бросает 429 с подсказкой, через сколько повторить."""
        if not get_settings().rate_limit_enabled:
            return
        key = f"{request.url.path}:{client_ip(request) or 'unknown'}"
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            retry_after = math.ceil(self.window_seconds - (now - hits[0]))
            raise RateLimitExceededError(details={"retry_after_seconds": retry_after})
        hits.append(now)

    def reset(self) -> None:
        """Сбрасывает накопленные счётчики (нужно тестам)."""
        self._hits.clear()
