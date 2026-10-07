import json
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parent / "data" / "participants.json"


@dataclass(frozen=True, slots=True)
class AuthorizationCode:
    """Код авторизации: одноразовый, короткоживущий, привязан к клиенту и PKCE."""

    participant_id: str
    client_id: str
    redirect_uri: str
    code_challenge: str
    nonce: str | None
    scope: str
    expires_at: float


class Registry:
    """Участники ФСП и их достижения из сид-файла эмулятора."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        """Строит индексы по идентификатору и логину."""
        self.participants = records
        self._by_id = {item["id"]: item for item in records}
        self._by_login = {item["login"]: item for item in records}

    def by_id(self, participant_id: str) -> dict[str, Any] | None:
        """Участник по идентификатору ФСП ID."""
        return self._by_id.get(participant_id)

    def by_login(self, login: str) -> dict[str, Any] | None:
        """Участник по логину на странице входа."""
        return self._by_login.get(login.strip().lower())


class CodeStore:
    """Выданные коды авторизации в памяти процесса.

    Для эмулятора этого достаточно: код живёт две минуты и используется один раз.
    Повторное использование кода — признак перехвата, поэтому код удаляется при
    первом же обмене, даже неудачном.
    """

    def __init__(self) -> None:
        """Создаёт пустое хранилище."""
        self._codes: dict[str, AuthorizationCode] = {}

    def issue(self, code: AuthorizationCode) -> str:
        """Сохраняет код и возвращает его значение."""
        self._purge()
        value = secrets.token_urlsafe(32)
        self._codes[value] = code
        return value

    def consume(self, value: str) -> AuthorizationCode | None:
        """Забирает код; просроченный или уже использованный даёт None."""
        code = self._codes.pop(value, None)
        if code is None or code.expires_at < time.time():
            return None
        return code

    def _purge(self) -> None:
        """Удаляет просроченные коды."""
        now = time.time()
        for value in [key for key, item in self._codes.items() if item.expires_at < now]:
            del self._codes[value]


@lru_cache
def get_registry() -> Registry:
    """Реестр участников, загруженный один раз."""
    return Registry(json.loads(DATA_FILE.read_text(encoding="utf-8")))


@lru_cache
def get_code_store() -> CodeStore:
    """Хранилище кодов на весь процесс."""
    return CodeStore()
