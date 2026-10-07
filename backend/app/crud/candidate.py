import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import distinct_on, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.assessment import AssessmentSession, SessionStatus
from app.models.candidate import (
    CandidateProfile,
    CandidateSkill,
    Education,
    PrivacySettings,
    SkillSource,
    WorkExperience,
)
from app.models.dictionary import Category, Skill
from app.models.user import User


class CandidateProfileCRUD(CRUDBase[CandidateProfile]):
    """Доступ к профилям кандидатов."""

    async def get_by_user_id(
        self, session: AsyncSession, user_id: uuid.UUID, *, for_update: bool = False
    ) -> CandidateProfile | None:
        """Профиль по владельцу вместе с текущей категорией.

        `for_update` блокирует строку профиля: так сериализуются операции, которые
        меняют категорию (два одновременных завершения теста не присвоят грейд дважды).
        """
        statement = (
            select(CandidateProfile)
            .where(CandidateProfile.user_id == user_id)
            .options(
                selectinload(CandidateProfile.current_category).selectinload(
                    Category.specialization
                ),
                selectinload(CandidateProfile.current_category).selectinload(Category.grade),
            )
        )
        if for_update:
            statement = statement.with_for_update(of=CandidateProfile)
        return await session.scalar(statement)

    async def list_with_theta_by_email_prefix(
        self, session: AsyncSession, prefix: str
    ) -> list[tuple[CandidateProfile, User, float | None]]:
        """Профили и владельцы по префиксу email вместе с θ последнего завершённого теста."""
        latest = (
            select(AssessmentSession.candidate_id, AssessmentSession.theta)
            .where(AssessmentSession.status == SessionStatus.COMPLETED)
            .order_by(AssessmentSession.candidate_id, AssessmentSession.finished_at.desc())
            .ext(distinct_on(AssessmentSession.candidate_id))
            .subquery()
        )
        result = await session.execute(
            select(CandidateProfile, User, latest.c.theta)
            .join(User, User.id == CandidateProfile.user_id)
            .outerjoin(latest, latest.c.candidate_id == CandidateProfile.id)
            .where(User.email.startswith(prefix, autoescape=True))
            .order_by(User.email)
        )
        return [
            (profile, user, float(theta) if theta is not None else None)
            for profile, user, theta in result.all()
        ]

    async def alias_taken(self, session: AsyncSession, alias: str) -> bool:
        """Занят ли публичный псевдоним."""
        found = await session.scalar(
            select(CandidateProfile.id).where(CandidateProfile.public_alias == alias)
        )
        return found is not None

    async def set_category(
        self, session: AsyncSession, profile: CandidateProfile, category: Category, at: datetime
    ) -> CandidateProfile:
        """Присваивает кандидату категорию.

        Связь выставляется объектом, а не только внешним ключом: иначе в памяти остался
        бы прежний `current_category`, а ленивая подгрузка в асинхронной сессии запрещена.
        """
        profile.current_category = category
        return await self.update(
            session, profile, {"current_category_id": category.id, "grade_assigned_at": at}
        )


class CandidateSkillCRUD(CRUDBase[CandidateSkill]):
    """Доступ к навыкам кандидата."""

    async def list_with_skills(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> Sequence[tuple[CandidateSkill, Skill]]:
        """Навыки кандидата вместе с записями справочника, по алфавиту."""
        result = await session.execute(
            select(CandidateSkill, Skill)
            .join(Skill, Skill.id == CandidateSkill.skill_id)
            .where(CandidateSkill.candidate_id == candidate_id)
            .order_by(Skill.name)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def replace_declared(
        self,
        session: AsyncSession,
        candidate_id: uuid.UUID,
        levels: dict[int, int | None],
    ) -> None:
        """Заменяет набор заявленных навыков, не трогая подтверждённые тестом.

        Подтверждённый навык нельзя «потерять», убрав его из анкеты: работодатель
        видит его как результат теста, а не как самоописание.
        """
        await session.execute(
            delete(CandidateSkill).where(
                CandidateSkill.candidate_id == candidate_id,
                CandidateSkill.is_verified.is_(False),
                CandidateSkill.skill_id.not_in(list(levels) or [-1]),
            )
        )
        await self.upsert_declared(session, candidate_id, levels, SkillSource.PROFILE)

    async def upsert_declared(
        self,
        session: AsyncSession,
        candidate_id: uuid.UUID,
        levels: dict[int, int | None],
        source: SkillSource,
    ) -> None:
        """Добавляет навыки или обновляет уровень, сохраняя признак подтверждения."""
        if not levels:
            return
        rows: list[dict[str, Any]] = [
            {
                "candidate_id": candidate_id,
                "skill_id": skill_id,
                "self_level": level,
                "source": source,
                "is_verified": False,
            }
            for skill_id, level in levels.items()
        ]
        statement = insert(CandidateSkill).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=[CandidateSkill.candidate_id, CandidateSkill.skill_id],
            set_={"self_level": statement.excluded.self_level},
        )
        await session.execute(statement)

    async def mark_verified(
        self, session: AsyncSession, candidate_id: uuid.UUID, skill_ids: Iterable[int], at: datetime
    ) -> None:
        """Отмечает навыки подтверждёнными тестом; отсутствующие в профиле добавляет."""
        ids = sorted(set(skill_ids))
        if not ids:
            return
        statement = insert(CandidateSkill).values(
            [
                {
                    "candidate_id": candidate_id,
                    "skill_id": skill_id,
                    "source": SkillSource.TEST,
                    "is_verified": True,
                    "verified_at": at,
                }
                for skill_id in ids
            ]
        )
        statement = statement.on_conflict_do_update(
            index_elements=[CandidateSkill.candidate_id, CandidateSkill.skill_id],
            set_={"is_verified": True, "verified_at": at},
        )
        await session.execute(statement)


class WorkExperienceCRUD(CRUDBase[WorkExperience]):
    """Доступ к опыту работы."""

    async def list_for_candidate(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> Sequence[WorkExperience]:
        """Места работы, начиная с последнего."""
        result = await session.scalars(
            select(WorkExperience)
            .where(WorkExperience.candidate_id == candidate_id)
            .order_by(WorkExperience.started_on.desc())
        )
        return result.all()

    async def replace_all(
        self, session: AsyncSession, candidate_id: uuid.UUID, items: Iterable[dict[str, Any]]
    ) -> None:
        """Полностью заменяет список мест работы (форма редактирует его целиком)."""
        await session.execute(
            delete(WorkExperience).where(WorkExperience.candidate_id == candidate_id)
        )
        session.add_all(WorkExperience(candidate_id=candidate_id, **item) for item in items)
        await session.flush()


class EducationCRUD(CRUDBase[Education]):
    """Доступ к образованию."""

    async def list_for_candidate(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> Sequence[Education]:
        """Записи об образовании, начиная с последней."""
        result = await session.scalars(
            select(Education)
            .where(Education.candidate_id == candidate_id)
            .order_by(Education.graduated_year.desc().nulls_last())
        )
        return result.all()

    async def replace_all(
        self, session: AsyncSession, candidate_id: uuid.UUID, items: Iterable[dict[str, Any]]
    ) -> None:
        """Полностью заменяет список записей об образовании."""
        await session.execute(delete(Education).where(Education.candidate_id == candidate_id))
        session.add_all(Education(candidate_id=candidate_id, **item) for item in items)
        await session.flush()


class PrivacySettingsCRUD(CRUDBase[PrivacySettings]):
    """Доступ к настройкам приватности."""

    async def get_or_create(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> PrivacySettings:
        """Настройки кандидата; при первом обращении создаются значения по умолчанию."""
        existing = await session.get(PrivacySettings, candidate_id)
        if existing is not None:
            return existing
        return await self.create(session, {"candidate_id": candidate_id})


class CandidateSkillLookupCRUD:
    """Вспомогательные выборки навыков для сервиса оценки."""

    async def skill_slugs(self, session: AsyncSession, skill_ids: Iterable[int]) -> list[str]:
        """Slug навыков по их идентификаторам."""
        ids = list(set(skill_ids))
        if not ids:
            return []
        result = await session.scalars(select(Skill.slug).where(Skill.id.in_(ids)))
        return list(result.all())

    async def ids_by_slugs(self, session: AsyncSession, slugs: Iterable[str]) -> dict[str, int]:
        """Идентификаторы навыков по slug."""
        values = list(set(slugs))
        if not values:
            return {}
        result = await session.execute(select(Skill.slug, Skill.id).where(Skill.slug.in_(values)))
        return dict(result.all())

    async def existing_ids(self, session: AsyncSession, skill_ids: Iterable[int]) -> set[int]:
        """Какие из переданных идентификаторов навыков существуют."""
        ids = list(set(skill_ids))
        if not ids:
            return set()
        result = await session.scalars(select(Skill.id).where(Skill.id.in_(ids)))
        return set(result.all())


candidate_profile_crud = CandidateProfileCRUD(CandidateProfile)
candidate_skill_crud = CandidateSkillCRUD(CandidateSkill)
work_experience_crud = WorkExperienceCRUD(WorkExperience)
education_crud = EducationCRUD(Education)
privacy_settings_crud = PrivacySettingsCRUD(PrivacySettings)
skill_lookup_crud = CandidateSkillLookupCRUD()
