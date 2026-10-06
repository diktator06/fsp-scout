from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    """База для схем ответа, которые строятся прямо из ORM-объектов."""

    model_config = ConfigDict(from_attributes=True)


class ErrorBody(BaseModel):
    """Тело ошибки: машинный код для фронтенда и текст для человека."""

    code: str = Field(examples=["email_already_registered"])
    message: str = Field(examples=["Пользователь с таким email уже зарегистрирован"])
    details: dict[str, Any] | list[Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Единый формат ошибок API."""

    error: ErrorBody


class Page[ItemT](BaseModel):
    """Страница списка с общим количеством записей для пагинации."""

    items: list[ItemT]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class MessageResponse(BaseModel):
    """Короткий ответ без данных: для операций вроде повторной отправки письма."""

    message: str
