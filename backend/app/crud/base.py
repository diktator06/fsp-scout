from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.db.base import Base

type Payload = BaseModel | Mapping[str, Any]


class CRUDBase[ModelT: Base]:
    """Обобщённые CRUD-операции над одной ORM-моделью.

    Правила слоя:
    * здесь живёт вся работа с сессией (`select`, `add`, `delete`, `flush`);
    * бизнес-правил нет: решения «можно ли» принимает сервис;
    * `commit` не вызывается никогда, транзакцией целиком управляет сервис.
      `flush` нужен, чтобы получить сгенерированные значения (id, created_at) и
      поймать нарушение ограничений в пределах той же транзакции.
    """

    def __init__(self, model: type[ModelT]) -> None:
        """Запоминает модель, с которой работает экземпляр."""
        self.model = model

    async def get(self, session: AsyncSession, entity_id: Any) -> ModelT | None:
        """Возвращает объект по первичному ключу или `None`."""
        return await session.get(self.model, entity_id)

    async def get_multi(
        self,
        session: AsyncSession,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: Sequence[ColumnElement[Any] | InstrumentedAttribute[Any]] = (),
    ) -> Sequence[ModelT]:
        """Возвращает страницу объектов в заданном порядке."""
        statement = select(self.model).offset(offset).limit(limit)
        if order_by:
            statement = statement.order_by(*order_by)
        result = await session.scalars(statement)
        return result.all()

    async def count(self, session: AsyncSession) -> int:
        """Количество записей в таблице."""
        total = await session.scalar(select(func.count()).select_from(self.model))
        return int(total or 0)

    async def create(self, session: AsyncSession, data: Payload) -> ModelT:
        """Создаёт объект из схемы или словаря полей."""
        values = data.model_dump() if isinstance(data, BaseModel) else dict(data)
        entity = self.model(**values)
        session.add(entity)
        await session.flush()
        return entity

    async def update(self, session: AsyncSession, entity: ModelT, data: Payload) -> ModelT:
        """Обновляет только переданные поля.

        У схемы берутся поля, явно заданные в запросе (`exclude_unset`). Поэтому PATCH
        с одним полем не затирает остальные значениями по умолчанию.
        """
        values = data.model_dump(exclude_unset=True) if isinstance(data, BaseModel) else dict(data)
        for field, value in values.items():
            setattr(entity, field, value)
        await session.flush()
        return entity

    async def delete(self, session: AsyncSession, entity: ModelT) -> None:
        """Удаляет объект."""
        await session.delete(entity)
        await session.flush()
