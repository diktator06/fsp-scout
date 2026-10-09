import enum
import uuid
from collections.abc import Collection, Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import delete, func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.models.candidate import CandidateProfile
from app.models.employer import Company
from app.models.integration import WebhookDelivery
from app.models.matching import ShortlistEntry
from app.models.user import User


def _plain(value: Any) -> Any:
    """Значение колонки в виде, пригодном для JSON."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.value
    return value


class PersonalDataCRUD:
    """Доступ к данным одного человека по всем таблицам — для выгрузки и удаления (152-ФЗ).

    Выгрузка идёт по списку «таблица — колонка-владелец», который задаёт сервис:
    так новая колонка в любой из таблиц попадает в выгрузку без правки кода.
    """

    async def rows(
        self,
        session: AsyncSession,
        model: type[Base],
        owner: str,
        values: Sequence[uuid.UUID],
        hidden: Collection[str] = (),
    ) -> list[dict[str, Any]]:
        """Строки таблицы, принадлежащие владельцу, в виде словарей для выгрузки.

        `owner` — имя колонки-владельца (пользователь, профиль, сессия), `hidden` —
        колонки, которые наружу не отдаются (хеши, ключи ответов). Берутся все
        остальные колонки, поэтому новая колонка попадает в выгрузку без правки кода.
        """
        if not values:
            return []
        column = getattr(model, owner)
        result = await session.scalars(select(model).where(column.in_(list(values))))
        mapper = inspect(model)
        return [
            {
                attribute.key: _plain(getattr(row, attribute.key))
                for attribute in mapper.column_attrs
                if attribute.key not in hidden
            }
            for row in result.all()
        ]

    async def shortlist_appearances(self, session: AsyncSession, candidate_id: uuid.UUID) -> int:
        """Сколько раз профиль попадал в подборки работодателей."""
        total = await session.scalar(
            select(func.count())
            .select_from(ShortlistEntry)
            .where(ShortlistEntry.candidate_id == candidate_id)
        )
        return int(total or 0)

    async def delete_webhook_copies(self, session: AsyncSession, candidate_id: uuid.UUID) -> int:
        """Удаляет из журнала доставок ATS события с данными кандидата.

        Копия в ATS работодателя — уже его зона ответственности как оператора ПДн, а
        наша копия в outbox должна исчезнуть вместе с аккаунтом.
        """
        result = await session.execute(
            delete(WebhookDelivery).where(
                WebhookDelivery.payload["data"]["candidate"]["candidate_id"].astext
                == str(candidate_id)
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def delete_company(self, session: AsyncSession, company_id: uuid.UUID) -> None:
        """Удаляет компанию; вакансии, подборки, приглашения и вебхуки уходят каскадом."""
        await session.execute(delete(Company).where(Company.id == company_id))

    async def delete_candidate_profile(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        """Удаляет профиль кандидата со всем, что на нём держится, до удаления аккаунта.

        Если удалить сразу аккаунт, PostgreSQL пойдёт двумя путями к одной строке
        события приглашения: удалить её каскадом через приглашение и обнулить автора
        через `SET NULL` — и второй путь упрётся во внешний ключ уже удалённого
        приглашения.
        """
        await session.execute(delete(CandidateProfile).where(CandidateProfile.user_id == user_id))

    async def delete_user(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        """Удаляет учётную запись; профиль и всё, что на нём держится, уходит каскадом в БД."""
        await session.execute(delete(User).where(User.id == user_id))


personal_data_crud = PersonalDataCRUD()
