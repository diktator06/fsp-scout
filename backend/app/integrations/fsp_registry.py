from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.core.exceptions import FspUnavailableError
from app.integrations.fsp_id import FspIdClient, read_json
from app.models.fsp import FspEventLevel, FspParticipationFormat, FspResultStatus


class RegistryAchievement(BaseModel):
    """Участие в соревновании так, как его отдаёт реестр ФСП."""

    event_id: str = Field(min_length=1, max_length=64)
    event_name: str = Field(min_length=1, max_length=300)
    event_level: FspEventLevel
    discipline: str = Field(min_length=1, max_length=160)
    event_date: date
    participation_format: FspParticipationFormat
    team_name: str | None = Field(default=None, max_length=200)
    team_role: str | None = Field(default=None, max_length=64)
    place: int | None = Field(default=None, gt=0)
    participants_total: int | None = Field(default=None, gt=0)
    result_status: FspResultStatus
    is_online: bool = False
    rating_points: float | None = None
    protocol_url: str | None = Field(default=None, max_length=500)

    @field_validator("protocol_url")
    @classmethod
    def only_web_links(cls, value: str | None) -> str | None:
        """Ссылка на протокол показывается работодателю, поэтому допускается только http(s).

        Иначе запись реестра со ссылкой `javascript:` превратилась бы в XSS в карточке.
        """
        if value is None or value.startswith(("https://", "http://")):
            return value
        return None


class RegistryRecord(BaseModel):
    """Участник ФСП с историей соревнований."""

    participant_id: str
    region: str | None = Field(default=None, max_length=120)
    sport_rank: str | None = Field(default=None, max_length=64)
    achievements: list[RegistryAchievement]


class RegistryParticipant(BaseModel):
    """Краткая сводка участника из сервисного списка реестра."""

    id: str
    region: str | None = None
    sport_rank: str | None = None
    events: int = 0
    results: int = 0
    finals: int = 0
    demo_persona: bool = False


class FspRegistryClient:
    """Клиент API реестра достижений ФСП.

    Реестр читается либо токеном самого участника сразу после входа, либо сервисным
    токеном платформы (client credentials) при повторной синхронизации.
    """

    def __init__(self, base_url: str, identity: FspIdClient) -> None:
        """Запоминает адрес API реестра и клиента ФСП ID, который выдаёт токены."""
        self._base_url = base_url.rstrip("/")
        self._identity = identity

    async def _get(self, path: str, params: dict[str, Any], token: str | None) -> dict[str, Any]:
        """Авторизованный GET. Отказ по сервисному токену один раз повторяется с новым токеном."""
        for attempt in range(2):
            bearer = token or await self._identity.service_token()
            try:
                async with self._identity.http() as client:
                    response = await client.get(
                        f"{self._base_url}{path}",
                        params=params,
                        headers={"Authorization": f"Bearer {bearer}"},
                    )
            except httpx.HTTPError as error:
                raise FspUnavailableError() from error
            if response.status_code == httpx.codes.UNAUTHORIZED and token is None and attempt == 0:
                self._identity.forget_service_token()
                continue
            if response.status_code != httpx.codes.OK:
                raise FspUnavailableError(
                    "Реестр ФСП не выдал данные участника",
                    details={"status": response.status_code},
                )
            return read_json(response)
        raise FspUnavailableError()

    async def achievements(
        self, participant_id: str, *, access_token: str | None = None
    ) -> RegistryRecord:
        """История соревнований участника. Ответ проверяется схемой до записи в базу."""
        payload = await self._get(f"/participants/{participant_id}/achievements", {}, access_token)
        try:
            record = RegistryRecord.model_validate(payload)
        except ValidationError as error:
            raise FspUnavailableError("Реестр ФСП вернул данные в неожиданном формате") from error
        if record.participant_id != participant_id:
            raise FspUnavailableError("Реестр ФСП вернул данные другого участника")
        return record

    async def participants(self, *, limit: int = 500, offset: int = 0) -> list[RegistryParticipant]:
        """Сервисный список участников (нужен демо-сиду эмулятора)."""
        payload = await self._get("/participants", {"limit": limit, "offset": offset}, None)
        try:
            return [RegistryParticipant.model_validate(item) for item in payload.get("items", [])]
        except ValidationError as error:
            raise FspUnavailableError("Реестр ФСП вернул данные в неожиданном формате") from error
