from datetime import datetime

from pydantic import BaseModel, Field

from app.models.fsp import FspState, FspSyncStatus
from app.schemas.cards import FspAchievementRead, VerifiedScoreRead
from app.schemas.common import ORMModel


class FspLinkStart(BaseModel):
    """Начало привязки ФСП ID. Согласие на получение данных из реестра обязательно (152-ФЗ)."""

    consent: bool = Field(description="Согласие на получение данных из реестра ФСП")


class FspAuthorizationRead(BaseModel):
    """Адрес страницы входа ФСП ID, на который фронтенд переводит браузер."""

    authorization_url: str
    expires_in: int = Field(description="Сколько секунд действует начатый вход")


class FspCallback(BaseModel):
    """Ответ ФСП ID, пришедший на адрес возврата фронтенда."""

    code: str = Field(min_length=1, max_length=512)
    state: str = Field(min_length=1, max_length=128)


class FspScoreRead(BaseModel):
    """Балл ФСП F = min(1; 0,6·R + 0,4·N) с составляющими."""

    value: float = Field(ge=0, le=1)
    results: float = Field(ge=0, le=1, description="R — результативность")
    activity: float = Field(ge=0, le=1, description="N — активность")
    effective_events: float = Field(description="M — взвешенное по давности число участий")
    events: int
    wins: int
    prizes: int
    finals: int
    online_attendance: int = Field(description="Онлайн-участия без результата")
    best_result: str | None
    summary: str
    vps_points: float = Field(description="Вклад ФСП в индекс подтверждённого профиля, баллов")


class FspSyncRead(ORMModel):
    """Последняя синхронизация с реестром."""

    status: FspSyncStatus
    achievements_count: int
    error: str | None
    synced_at: datetime


class FspProfileRead(BaseModel):
    """ФСП в кабинете кандидата: состояние привязки, участия, балл и вклад в индекс."""

    enabled: bool
    state: FspState
    message: str
    participant_id: str | None
    linked_at: datetime | None
    synced_at: datetime | None
    region: str | None
    sport_rank: str | None
    consent_active: bool
    visible_to_employers: bool
    last_sync: FspSyncRead | None
    score: FspScoreRead
    achievements: list[FspAchievementRead]
    verified_score: VerifiedScoreRead | None = Field(
        description="Индекс подтверждённого профиля кандидата, если у него есть категория"
    )
