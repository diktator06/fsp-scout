from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, DomainValidationError, NotFoundError
from app.crud import (
    category_crud,
    grade_crud,
    skill_crud,
    specialization_crud,
    specialization_skill_crud,
)
from app.models.dictionary import Category, Grade, Skill, Specialization
from app.schemas.dictionary import (
    SkillCreate,
    SkillUpdate,
    SpecializationCreate,
    SpecializationUpdate,
)

DEFAULT_SKILL_WEIGHT = 0.5


def build_category_code(specialization: Specialization, grade: Grade) -> str:
    """Код категории вида `backend-middle`: читается в URL и логах."""
    return f"{specialization.code.replace('_', '-')}-{grade.code}"


def build_category_title(specialization: Specialization, grade: Grade) -> str:
    """Название категории, которое видит работодатель: «Backend-разработка · Middle»."""
    return f"{specialization.name} · {grade.name}"


class DictionaryService:
    """Изменение справочников методистом.

    Чтение справочников логики не содержит, и роутеры берут его прямо из CRUD.
    Здесь собраны только операции с правилами: создание специализации тянет за собой
    категории, а удаление не должно ломать ссылки.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Получает сессию БД."""
        self._session = session

    async def create_specialization(self, payload: SpecializationCreate) -> Specialization:
        """Создаёт специализацию и по категории на каждый грейд.

        Категория обязана существовать для любой пары «специализация × грейд»:
        тест присваивает кандидату именно категорию, а не два отдельных поля.
        """
        if await specialization_crud.get_by_code(self._session, payload.code):
            raise ConflictError("Специализация с таким кодом уже существует")
        specialization = await specialization_crud.create(self._session, payload)
        for grade in await grade_crud.list_all(self._session):
            await category_crud.create(
                self._session,
                {
                    "specialization_id": specialization.id,
                    "grade_id": grade.id,
                    "code": build_category_code(specialization, grade),
                    "title": build_category_title(specialization, grade),
                    "theta_cut": grade.default_theta_cut,
                },
            )
        await self._session.commit()
        return specialization

    async def update_specialization(
        self, specialization_id: int, payload: SpecializationUpdate
    ) -> Specialization:
        """Меняет специализацию. При смене названия обновляются и названия её категорий."""
        specialization = await self._get_specialization(specialization_id)
        renamed = payload.name is not None and payload.name != specialization.name
        await specialization_crud.update(self._session, specialization, payload)
        if renamed:
            grades = {grade.id: grade for grade in await grade_crud.list_all(self._session)}
            for category in await category_crud.list_for_specialization(
                self._session, specialization.id
            ):
                await category_crud.update(
                    self._session,
                    category,
                    {"title": build_category_title(specialization, grades[category.grade_id])},
                )
        await self._session.commit()
        return specialization

    async def delete_specialization(self, specialization_id: int) -> None:
        """Удаляет специализацию вместе с её категориями.

        Если на категории уже ссылаются данные (кандидаты, задания), база откажет по
        внешнему ключу. Такой отказ превращаем в понятный конфликт.
        """
        specialization = await self._get_specialization(specialization_id)
        try:
            await specialization_crud.delete(self._session, specialization)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("Специализация используется и не может быть удалена") from exc

    async def create_skill(self, payload: SkillCreate) -> Skill:
        """Создаёт навык и при необходимости привязывает его к специализациям."""
        if await skill_crud.get_by_slug(self._session, payload.slug):
            raise ConflictError("Навык с таким slug уже существует")
        await self._ensure_specializations_exist(payload.specialization_ids)
        skill = await skill_crud.create(
            self._session, payload.model_dump(exclude={"specialization_ids"})
        )
        if payload.specialization_ids:
            await specialization_skill_crud.replace_for_skill(
                self._session,
                skill.id,
                dict.fromkeys(payload.specialization_ids, DEFAULT_SKILL_WEIGHT),
            )
        await self._session.commit()
        return skill

    async def update_skill(self, skill_id: int, payload: SkillUpdate) -> Skill:
        """Меняет название, тип или алиасы навыка."""
        skill = await skill_crud.get(self._session, skill_id)
        if skill is None:
            raise NotFoundError("Навык не найден")
        await skill_crud.update(self._session, skill, payload)
        await self._session.commit()
        return skill

    async def delete_skill(self, skill_id: int) -> None:
        """Удаляет навык, если на него ещё никто не ссылается."""
        skill = await skill_crud.get(self._session, skill_id)
        if skill is None:
            raise NotFoundError("Навык не найден")
        try:
            await skill_crud.delete(self._session, skill)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("Навык используется и не может быть удалён") from exc

    async def get_category(self, code: str) -> Category:
        """Категория по коду или ошибка «не найдено»."""
        category = await category_crud.get_by_code(self._session, code)
        if category is None:
            raise NotFoundError("Категория не найдена")
        return category

    async def _get_specialization(self, specialization_id: int) -> Specialization:
        """Специализация по id или ошибка «не найдено»."""
        specialization = await specialization_crud.get(self._session, specialization_id)
        if specialization is None:
            raise NotFoundError("Специализация не найдена")
        return specialization

    async def _ensure_specializations_exist(self, ids: list[int]) -> None:
        """Проверяет, что все указанные специализации существуют, и перечисляет отсутствующие."""
        if not ids:
            return
        found = {spec.id for spec in await specialization_crud.get_many(self._session, ids)}
        missing = sorted(set(ids) - found)
        if missing:
            raise DomainValidationError(
                "Указаны несуществующие специализации", details={"specialization_ids": missing}
            )
