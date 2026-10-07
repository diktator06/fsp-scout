import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.inn import is_valid_inn
from app.models.employer import CompanySize, TrustLevel
from app.models.invitation import InvitationStatus
from app.schemas.common import ORMModel
from app.schemas.dictionary import IndustryRead

_INN = re.compile(r"^\d{10}(\d{2})?$")
_PHONE = re.compile(r"^\+?[0-9()\-\s]{7,20}$")
_TELEGRAM = re.compile(r"^@?[A-Za-z0-9_]{5,32}$")
_WEBSITE = re.compile(r"^(https?://)?[\w.-]+\.[a-zа-я]{2,}(/\S*)?$", re.IGNORECASE)


def _optional(value: str | None) -> str | None:
    """Пустая строка из формы — это «не указано»."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class CompanyUpdate(BaseModel):
    """Профиль компании и данные рекрутера, который его заполняет."""

    name: str = Field(min_length=2, max_length=200, examples=["Кедр Технологии"])
    inn: str | None = Field(default=None, examples=["7701234560"])
    website: str | None = Field(default=None, max_length=200, examples=["https://kedr.example"])
    industry_id: int | None = None
    description: str = Field(default="", max_length=3000)
    size: CompanySize | None = None
    city: str | None = Field(default=None, max_length=120)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_telegram: str | None = Field(default=None, max_length=64)
    recruiter_full_name: str = Field(min_length=2, max_length=200, examples=["Мария Соколова"])
    recruiter_position: str = Field(default="", max_length=120, examples=["HR-партнёр"])

    @field_validator("name", "city", "recruiter_full_name", "recruiter_position", "description")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        """Убирает пробелы по краям."""
        return value.strip() if isinstance(value, str) else value

    @field_validator("inn")
    @classmethod
    def check_inn(cls, value: str | None) -> str | None:
        """ИНН — 10 цифр у организации или 12 у ИП, с верными контрольными цифрами."""
        cleaned = _optional(value)
        if cleaned is not None and not _INN.match(cleaned):
            raise ValueError("ИНН состоит из 10 или 12 цифр")
        if cleaned is not None and not is_valid_inn(cleaned):
            raise ValueError("Контрольные цифры ИНН не сходятся — проверьте номер")
        return cleaned

    @field_validator("website")
    @classmethod
    def check_website(cls, value: str | None) -> str | None:
        """Адрес сайта; схема https:// добавляется, если её не указали."""
        cleaned = _optional(value)
        if cleaned is None:
            return None
        if not _WEBSITE.match(cleaned):
            raise ValueError("Укажите адрес сайта, например kedr.example")
        return cleaned if cleaned.startswith(("http://", "https://")) else f"https://{cleaned}"

    @field_validator("contact_phone")
    @classmethod
    def check_phone(cls, value: str | None) -> str | None:
        """Телефон — цифры, пробелы, скобки и дефисы."""
        cleaned = _optional(value)
        if cleaned is not None and not _PHONE.match(cleaned):
            raise ValueError("Укажите телефон в формате +7 999 123-45-67")
        return cleaned

    @field_validator("contact_telegram")
    @classmethod
    def check_telegram(cls, value: str | None) -> str | None:
        """Ник Telegram храним с «@»."""
        cleaned = _optional(value)
        if cleaned is None:
            return None
        if not _TELEGRAM.match(cleaned):
            raise ValueError("Ник Telegram: 5–32 латинских букв, цифр или «_»")
        return cleaned if cleaned.startswith("@") else f"@{cleaned}"


class CompanyRead(ORMModel):
    """Профиль компании."""

    id: uuid.UUID
    name: str
    inn: str | None
    website: str | None
    industry: IndustryRead | None
    description: str
    size: CompanySize | None
    city: str | None
    contact_email: str | None
    contact_phone: str | None
    contact_telegram: str | None
    trust_level: TrustLevel
    restricted_at: datetime | None
    restriction_reason: str
    created_at: datetime


class RecruiterRead(ORMModel):
    """Рекрутер компании."""

    full_name: str
    position: str


class InvitationQuotaRead(BaseModel):
    """Дневная квота приглашений: защита кандидатов от массовых рассылок."""

    daily_limit: int
    used_today: int
    remaining: int


class EmployerProfileRead(BaseModel):
    """Кабинет работодателя: компания, рекрутер и квота. Без компании — пустые поля."""

    company: CompanyRead | None
    recruiter: RecruiterRead | None
    quota: InvitationQuotaRead | None


class EmployerDashboardRead(BaseModel):
    """Сводка для главной кабинета работодателя."""

    active_needs: int
    invitations: dict[InvitationStatus, int]
    accepted_contacts: int
    quota: InvitationQuotaRead
