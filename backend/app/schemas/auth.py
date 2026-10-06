import re
import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import UserRole
from app.schemas.user import UserRead

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
_HAS_LETTER = re.compile(r"[A-Za-zА-Яа-яЁё]")
_HAS_DIGIT = re.compile(r"\d")


def normalize_email(value: str) -> str:
    """Приводит email к нижнему регистру: адреса сравниваются без учёта регистра."""
    return value.strip().lower()


class RegisterRequest(BaseModel):
    """Регистрация кандидата или работодателя."""

    email: EmailStr = Field(examples=["ivan.petrov@example.com"])
    password: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH, examples=["Sk0ut-2026"]
    )
    role: Literal[UserRole.CANDIDATE, UserRole.EMPLOYER] = Field(
        description=(
            "Методисты не регистрируются самостоятельно, их заводит администратор платформы"
        ),
        examples=["candidate"],
    )
    accept_personal_data_processing: bool = Field(
        description=(
            "Согласие на обработку персональных данных (152-ФЗ), без него регистрация невозможна"
        )
    )

    @field_validator("email")
    @classmethod
    def lower_email(cls, value: str) -> str:
        """Нормализует email перед проверкой уникальности."""
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def check_password_strength(cls, value: str) -> str:
        """Минимальные требования к паролю: буквы и цифры, без пробелов по краям.

        Жёстких правил вроде «обязательный спецсимвол» намеренно не вводим: они
        мешают пользователям, а надёжность пароля в основном определяет длина.
        """
        if value != value.strip():
            raise ValueError("Пароль не должен начинаться или заканчиваться пробелом")
        if not _HAS_LETTER.search(value) or not _HAS_DIGIT.search(value):
            raise ValueError("Пароль должен содержать хотя бы одну букву и одну цифру")
        return value

    @field_validator("accept_personal_data_processing")
    @classmethod
    def require_consent(cls, value: bool) -> bool:
        """Без согласия на обработку ПДн аккаунт создавать нельзя."""
        if not value:
            raise ValueError("Необходимо согласие на обработку персональных данных")
        return value


class RegisterResponse(BaseModel):
    """Результат регистрации: аккаунт создан и ждёт подтверждения email."""

    user_id: uuid.UUID
    email: str
    verification_email_sent: bool = Field(
        description="false, если почтовый сервер недоступен: письмо можно запросить повторно"
    )


class VerifyEmailRequest(BaseModel):
    """Токен из ссылки в письме."""

    token: str = Field(min_length=16, max_length=256)


class ResendVerificationRequest(BaseModel):
    """Запрос повторной отправки письма с подтверждением."""

    email: EmailStr

    @field_validator("email")
    @classmethod
    def lower_email(cls, value: str) -> str:
        """Нормализует email так же, как при регистрации."""
        return normalize_email(value)


class LoginRequest(BaseModel):
    """Вход по email и паролю."""

    email: EmailStr = Field(examples=["candidate@example.com"])
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH, examples=["ScoutDemo2026"])

    @field_validator("email")
    @classmethod
    def lower_email(cls, value: str) -> str:
        """Нормализует email так же, как при регистрации."""
        return normalize_email(value)


class TokenResponse(BaseModel):
    """Access-токен и сведения о пользователе. Refresh-токен уходит отдельно в httpOnly-cookie."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Срок жизни access-токена в секундах")
    user: UserRead
