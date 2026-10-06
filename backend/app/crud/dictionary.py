from collections.abc import Iterable, Sequence

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.dictionary import (
    Category,
    Grade,
    Industry,
    Skill,
    SkillKind,
    Specialization,
    SpecializationSkill,
)


class IndustryCRUD(CRUDBase[Industry]):
    """Доступ к справочнику отраслей."""

    async def list_all(self, session: AsyncSession) -> Sequence[Industry]:
        """Все отрасли в порядке показа."""
        result = await session.scalars(
            select(Industry).order_by(Industry.sort_order, Industry.name)
        )
        return result.all()

    async def get_by_code(self, session: AsyncSession, code: str) -> Industry | None:
        """Отрасль по коду."""
        return await session.scalar(select(Industry).where(Industry.code == code))


class SpecializationCRUD(CRUDBase[Specialization]):
    """Доступ к справочнику специализаций."""

    async def list_all(self, session: AsyncSession) -> Sequence[Specialization]:
        """Все специализации в порядке показа."""
        result = await session.scalars(
            select(Specialization).order_by(Specialization.sort_order, Specialization.name)
        )
        return result.all()

    async def get_by_code(self, session: AsyncSession, code: str) -> Specialization | None:
        """Специализация по коду."""
        return await session.scalar(select(Specialization).where(Specialization.code == code))

    async def get_many(self, session: AsyncSession, ids: Iterable[int]) -> Sequence[Specialization]:
        """Специализации по списку идентификаторов (несуществующие просто не попадут в ответ)."""
        id_list = list(set(ids))
        if not id_list:
            return []
        result = await session.scalars(select(Specialization).where(Specialization.id.in_(id_list)))
        return result.all()


class GradeCRUD(CRUDBase[Grade]):
    """Доступ к справочнику грейдов."""

    async def list_all(self, session: AsyncSession) -> Sequence[Grade]:
        """Все грейды по возрастанию уровня."""
        result = await session.scalars(select(Grade).order_by(Grade.rank))
        return result.all()

    async def get_by_code(self, session: AsyncSession, code: str) -> Grade | None:
        """Грейд по коду."""
        return await session.scalar(select(Grade).where(Grade.code == code))


class CategoryCRUD(CRUDBase[Category]):
    """Доступ к категориям. Специализация и грейд подгружаются явно: ленивая загрузка запрещена."""

    def _with_relations(self) -> Select[Category]:
        """Базовый запрос категорий вместе со специализацией и грейдом."""
        return select(Category).options(
            selectinload(Category.specialization), selectinload(Category.grade)
        )

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        specialization_id: int | None = None,
        grade_id: int | None = None,
    ) -> Sequence[Category]:
        """Категории с необязательным фильтром по специализации и грейду.

        Порядок такой же, как в интерфейсе: специализации по `sort_order`, внутри них
        грейды по возрастанию.
        """
        statement = (
            self._with_relations()
            .join(Category.specialization)
            .join(Category.grade)
            .order_by(Specialization.sort_order, Specialization.name, Grade.rank)
        )
        if specialization_id is not None:
            statement = statement.where(Category.specialization_id == specialization_id)
        if grade_id is not None:
            statement = statement.where(Category.grade_id == grade_id)
        result = await session.scalars(statement)
        return result.all()

    async def get_by_code(self, session: AsyncSession, code: str) -> Category | None:
        """Категория по коду вместе со связями."""
        return await session.scalar(self._with_relations().where(Category.code == code))

    async def get_by_pair(
        self, session: AsyncSession, specialization_id: int, grade_id: int
    ) -> Category | None:
        """Категория по паре «специализация + грейд»."""
        return await session.scalar(
            select(Category).where(
                Category.specialization_id == specialization_id, Category.grade_id == grade_id
            )
        )

    async def list_for_specialization(
        self, session: AsyncSession, specialization_id: int
    ) -> Sequence[Category]:
        """Все категории одной специализации (без связей, для массовых изменений)."""
        result = await session.scalars(
            select(Category).where(Category.specialization_id == specialization_id)
        )
        return result.all()


class SkillCRUD(CRUDBase[Skill]):
    """Доступ к справочнику навыков."""

    async def get_by_slug(self, session: AsyncSession, slug: str) -> Skill | None:
        """Навык по slug."""
        return await session.scalar(select(Skill).where(Skill.slug == slug))

    async def search(
        self,
        session: AsyncSession,
        *,
        query: str | None = None,
        kind: SkillKind | None = None,
        specialization_id: int | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[Skill], int]:
        """Поиск навыков по подстроке в названии, slug или алиасах.

        Возвращает страницу и общее количество найденного. Алиасы склеиваются в строку
        прямо в запросе (`array_to_string`). Для справочника на сотни записей этого
        достаточно, а при росте поможет триграммный индекс.
        """
        statement = select(Skill)
        if query:
            pattern = f"%{query.strip()}%"
            statement = statement.where(
                or_(
                    Skill.name.ilike(pattern),
                    Skill.slug.ilike(pattern),
                    func.array_to_string(Skill.aliases, " ").ilike(pattern),
                )
            )
        if kind is not None:
            statement = statement.where(Skill.kind == kind)
        if specialization_id is not None:
            statement = statement.join(
                SpecializationSkill, SpecializationSkill.skill_id == Skill.id
            ).where(SpecializationSkill.specialization_id == specialization_id)

        total = await session.scalar(select(func.count()).select_from(statement.subquery()))
        page = await session.scalars(statement.order_by(Skill.name).offset(offset).limit(limit))
        return page.all(), int(total or 0)


class SpecializationSkillCRUD(CRUDBase[SpecializationSkill]):
    """Доступ к связям «специализация ↔ навык»."""

    async def replace_for_skill(
        self, session: AsyncSession, skill_id: int, weights: dict[int, float]
    ) -> None:
        """Полностью заменяет набор специализаций навыка новыми весами."""
        await session.execute(
            delete(SpecializationSkill).where(SpecializationSkill.skill_id == skill_id)
        )
        session.add_all(
            SpecializationSkill(specialization_id=spec_id, skill_id=skill_id, typical_weight=weight)
            for spec_id, weight in weights.items()
        )
        await session.flush()


industry_crud = IndustryCRUD(Industry)
specialization_crud = SpecializationCRUD(Specialization)
grade_crud = GradeCRUD(Grade)
category_crud = CategoryCRUD(Category)
skill_crud = SkillCRUD(Skill)
specialization_skill_crud = SpecializationSkillCRUD(SpecializationSkill)
