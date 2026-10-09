import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.employer import Company, Recruiter


class CompanyCRUD(CRUDBase[Company]):
    """Доступ к компаниям."""

    async def get_with_industry(
        self, session: AsyncSession, company_id: uuid.UUID
    ) -> Company | None:
        """Компания вместе с отраслью (её показываем кандидату в приглашении)."""
        return await session.scalar(
            select(Company).options(selectinload(Company.industry)).where(Company.id == company_id)
        )

    async def lock(self, session: AsyncSession, company_id: uuid.UUID) -> None:
        """Блокирует строку компании до конца транзакции.

        Нужна, когда правило касается всей компании, а не одной записи: например,
        лимит одновременно опубликованных вакансий при параллельных публикациях.
        """
        await session.execute(select(Company.id).where(Company.id == company_id).with_for_update())


class RecruiterCRUD(CRUDBase[Recruiter]):
    """Доступ к рекрутерам — связке «пользователь ↔ компания»."""

    async def get_by_user_id(self, session: AsyncSession, user_id: uuid.UUID) -> Recruiter | None:
        """Рекрутер по пользователю вместе с компанией и её отраслью."""
        return await session.scalar(
            select(Recruiter)
            .options(selectinload(Recruiter.company).selectinload(Company.industry))
            .where(Recruiter.user_id == user_id)
        )

    async def user_ids_for_company(
        self, session: AsyncSession, company_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Все пользователи компании: им уходят уведомления по приглашениям."""
        result = await session.scalars(
            select(Recruiter.user_id).where(Recruiter.company_id == company_id)
        )
        return list(result.all())


company_crud = CompanyCRUD(Company)
recruiter_crud = RecruiterCRUD(Recruiter)
