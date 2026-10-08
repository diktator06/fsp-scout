import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class PersonalDataExport(BaseModel):
    """Выгрузка персональных данных пользователя (ст. 14 152-ФЗ — право на доступ).

    Разделы — таблицы, в которых есть данные человека, строки — записи как есть, без
    служебных секретов: хешей паролей и токенов, ключей ответов и seed заданий.
    """

    format_version: str = "1"
    generated_at: datetime
    operator: str
    purposes: list[str]
    user_id: uuid.UUID
    role: UserRole
    sections: dict[str, list[dict[str, Any]]]
    counters: dict[str, int] = Field(description="Сводные числа без самих записей")


class AccountDeletionRequest(BaseModel):
    """Подтверждение удаления аккаунта: человек вводит свой email."""

    confirm_email: EmailStr
