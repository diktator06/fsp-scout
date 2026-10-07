import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.dictionary import Skill
from app.models.matching import (
    HiringNeed,
    NeedSkill,
    NeedStatus,
    Shortlist,
    ShortlistEntry,
    ShortlistMark,
    ShortlistMarkKind,
    SkillImportance,
)


class HiringNeedCRUD(CRUDBase[HiringNeed]):
    """Доступ к потребностям работодателей."""

    async def get_for_company(
        self,
        session: AsyncSession,
        need_id: uuid.UUID,
        company_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> HiringNeed | None:
        """Потребность компании. Чужую потребность не найти даже по точному id."""
        statement = (
            select(HiringNeed)
            .options(selectinload(HiringNeed.specialization))
            .where(HiringNeed.id == need_id, HiringNeed.company_id == company_id)
        )
        if for_update:
            statement = statement.with_for_update(of=HiringNeed)
        return await session.scalar(statement)

    async def list_for_company(
        self, session: AsyncSession, company_id: uuid.UUID, status: NeedStatus | None = None
    ) -> Sequence[HiringNeed]:
        """Потребности компании, от новых к старым."""
        statement = (
            select(HiringNeed)
            .options(selectinload(HiringNeed.specialization))
            .where(HiringNeed.company_id == company_id)
            .order_by(HiringNeed.created_at.desc())
        )
        if status is not None:
            statement = statement.where(HiringNeed.status == status)
        result = await session.scalars(statement)
        return result.all()


class NeedSkillCRUD(CRUDBase[NeedSkill]):
    """Доступ к навыкам потребности."""

    async def list_with_skills(
        self, session: AsyncSession, need_ids: Iterable[uuid.UUID]
    ) -> Sequence[tuple[NeedSkill, Skill]]:
        """Навыки потребностей вместе со справочником: сначала must, затем по алфавиту."""
        ids = list(need_ids)
        if not ids:
            return []
        result = await session.execute(
            select(NeedSkill, Skill)
            .join(Skill, Skill.id == NeedSkill.skill_id)
            .where(NeedSkill.need_id.in_(ids))
            .order_by(NeedSkill.importance, Skill.name)
        )
        return [(need_skill, skill) for need_skill, skill in result.all()]

    async def replace_for_need(
        self, session: AsyncSession, need_id: uuid.UUID, skills: Mapping[int, SkillImportance]
    ) -> None:
        """Полностью заменяет набор навыков потребности."""
        await session.execute(delete(NeedSkill).where(NeedSkill.need_id == need_id))
        session.add_all(
            NeedSkill(need_id=need_id, skill_id=skill_id, importance=importance)
            for skill_id, importance in skills.items()
        )
        await session.flush()


class ShortlistCRUD(CRUDBase[Shortlist]):
    """Доступ к версиям подборок."""

    async def latest_version(self, session: AsyncSession, need_id: uuid.UUID) -> int:
        """Номер последней версии подборки (0, если подборок ещё не было)."""
        version = await session.scalar(
            select(func.max(Shortlist.version)).where(Shortlist.need_id == need_id)
        )
        return int(version or 0)

    async def get_version(
        self, session: AsyncSession, need_id: uuid.UUID, version: int
    ) -> Shortlist | None:
        """Конкретная версия подборки."""
        return await session.scalar(
            select(Shortlist).where(Shortlist.need_id == need_id, Shortlist.version == version)
        )

    async def list_for_need(self, session: AsyncSession, need_id: uuid.UUID) -> Sequence[Shortlist]:
        """Все версии подборки, от новых к старым."""
        result = await session.scalars(
            select(Shortlist).where(Shortlist.need_id == need_id).order_by(Shortlist.version.desc())
        )
        return result.all()


class ShortlistEntryCRUD(CRUDBase[ShortlistEntry]):
    """Доступ к строкам подборки."""

    async def create_many(
        self, session: AsyncSession, shortlist_id: uuid.UUID, entries: Sequence[Mapping[str, Any]]
    ) -> None:
        """Записывает строки версии подборки одной пачкой."""
        session.add_all(ShortlistEntry(shortlist_id=shortlist_id, **entry) for entry in entries)
        await session.flush()

    async def list_for_shortlist(
        self, session: AsyncSession, shortlist_id: uuid.UUID
    ) -> Sequence[ShortlistEntry]:
        """Строки подборки по месту."""
        result = await session.scalars(
            select(ShortlistEntry)
            .where(ShortlistEntry.shortlist_id == shortlist_id)
            .order_by(ShortlistEntry.rank)
        )
        return result.all()


class ShortlistMarkCRUD(CRUDBase[ShortlistMark]):
    """Доступ к отметкам «закреплён / скрыт»."""

    async def list_for_need(
        self, session: AsyncSession, need_id: uuid.UUID
    ) -> dict[uuid.UUID, ShortlistMark]:
        """Отметки потребности по кандидатам."""
        result = await session.scalars(
            select(ShortlistMark).where(ShortlistMark.need_id == need_id)
        )
        return {mark.candidate_id: mark for mark in result.all()}

    async def upsert(
        self,
        session: AsyncSession,
        *,
        need_id: uuid.UUID,
        candidate_id: uuid.UUID,
        mark: ShortlistMarkKind,
        note: str,
    ) -> None:
        """Ставит или меняет отметку кандидата в потребности."""
        statement = insert(ShortlistMark).values(
            need_id=need_id, candidate_id=candidate_id, mark=mark, note=note
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[ShortlistMark.need_id, ShortlistMark.candidate_id],
                set_={"mark": mark, "note": note, "updated_at": func.now()},
            )
        )

    async def remove(
        self, session: AsyncSession, need_id: uuid.UUID, candidate_id: uuid.UUID
    ) -> None:
        """Снимает отметку."""
        await session.execute(
            delete(ShortlistMark).where(
                ShortlistMark.need_id == need_id, ShortlistMark.candidate_id == candidate_id
            )
        )


hiring_need_crud = HiringNeedCRUD(HiringNeed)
need_skill_crud = NeedSkillCRUD(NeedSkill)
shortlist_crud = ShortlistCRUD(Shortlist)
shortlist_entry_crud = ShortlistEntryCRUD(ShortlistEntry)
shortlist_mark_crud = ShortlistMarkCRUD(ShortlistMark)
