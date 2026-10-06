import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.assessment import (
    AssessmentItem,
    AssessmentSession,
    Competency,
    GradeHistory,
    ItemFamily,
    ItemFamilyStatus,
    SessionStatus,
    SpecializationCompetency,
    SurveyResponse,
)
from app.models.dictionary import Category


class CompetencyCRUD(CRUDBase[Competency]):
    """Доступ к компетенциям."""

    async def get_by_code(self, session: AsyncSession, code: str) -> Competency | None:
        """Компетенция по коду."""
        return await session.scalar(select(Competency).where(Competency.code == code))

    async def list_all(self, session: AsyncSession) -> Sequence[Competency]:
        """Все компетенции."""
        result = await session.scalars(select(Competency).order_by(Competency.name))
        return result.all()

    async def ids_by_codes(self, session: AsyncSession, codes: Iterable[str]) -> list[int]:
        """Идентификаторы компетенций по кодам."""
        values = list(set(codes))
        if not values:
            return []
        result = await session.scalars(select(Competency.id).where(Competency.code.in_(values)))
        return sorted(result.all())


class SpecializationCompetencyCRUD(CRUDBase[SpecializationCompetency]):
    """Доступ к blueprint специализаций."""

    async def list_for_specialization(
        self, session: AsyncSession, specialization_id: int
    ) -> Sequence[tuple[SpecializationCompetency, Competency]]:
        """Веса компетенций специализации вместе с самими компетенциями."""
        result = await session.execute(
            select(SpecializationCompetency, Competency)
            .join(Competency, Competency.id == SpecializationCompetency.competency_id)
            .where(SpecializationCompetency.specialization_id == specialization_id)
            .order_by(SpecializationCompetency.weight.desc())
        )
        return [(row[0], row[1]) for row in result.all()]

    async def get_pair(
        self, session: AsyncSession, specialization_id: int, competency_id: int
    ) -> SpecializationCompetency | None:
        """Вес конкретной компетенции в специализации."""
        return await session.get(SpecializationCompetency, (specialization_id, competency_id))


class ItemFamilyCRUD(CRUDBase[ItemFamily]):
    """Доступ к банку семейств заданий."""

    async def get_by_code(self, session: AsyncSession, code: str) -> ItemFamily | None:
        """Семейство по коду генератора."""
        return await session.scalar(select(ItemFamily).where(ItemFamily.code == code))

    async def list_for_competencies(
        self,
        session: AsyncSession,
        competency_ids: Iterable[int],
        statuses: Iterable[ItemFamilyStatus],
    ) -> Sequence[ItemFamily]:
        """Семейства нужных компетенций в заданных статусах, с подгруженной компетенцией."""
        ids = list(competency_ids)
        if not ids:
            return []
        result = await session.scalars(
            select(ItemFamily)
            .options(selectinload(ItemFamily.competency))
            .where(ItemFamily.competency_id.in_(ids), ItemFamily.status.in_(list(statuses)))
            .order_by(ItemFamily.code)
        )
        return result.all()

    async def count_by_competency(
        self, session: AsyncSession, statuses: Iterable[ItemFamilyStatus]
    ) -> dict[int, int]:
        """Сколько семейств в каждой компетенции (для описания blueprint)."""
        result = await session.execute(
            select(ItemFamily.competency_id, func.count())
            .where(ItemFamily.status.in_(list(statuses)))
            .group_by(ItemFamily.competency_id)
        )
        return dict(result.tuples().all())

    async def register_exposure(self, session: AsyncSession, family_id: int) -> None:
        """Атомарно увеличивает счётчик показов семейства.

        UPDATE … SET exposure_count = exposure_count + 1 не теряет показы при
        параллельных сессиях, в отличие от «прочитать, прибавить, записать».
        """
        await session.execute(
            update(ItemFamily)
            .where(ItemFamily.id == family_id)
            .values(exposure_count=ItemFamily.exposure_count + 1)
        )

    async def register_response(self, session: AsyncSession, family_id: int, correct: bool) -> None:
        """Атомарно учитывает ответ на семейство (для калибровки и детектора дрейфа)."""
        await session.execute(
            update(ItemFamily)
            .where(ItemFamily.id == family_id)
            .values(
                responses_count=ItemFamily.responses_count + 1,
                correct_count=ItemFamily.correct_count + (1 if correct else 0),
            )
        )


class SurveyCRUD(CRUDBase[SurveyResponse]):
    """Доступ к ответам опроса."""

    async def latest_for_candidate(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> SurveyResponse | None:
        """Последний пройденный опрос кандидата."""
        return await session.scalar(
            select(SurveyResponse)
            .where(SurveyResponse.candidate_id == candidate_id)
            .order_by(SurveyResponse.created_at.desc())
            .limit(1)
        )


class AssessmentSessionCRUD(CRUDBase[AssessmentSession]):
    """Доступ к сессиям тестирования."""

    async def get_for_candidate(
        self,
        session: AsyncSession,
        session_id: uuid.UUID,
        candidate_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> AssessmentSession | None:
        """Сессия, принадлежащая кандидату. Чужую сессию не найти даже по точному id."""
        statement = select(AssessmentSession).where(
            AssessmentSession.id == session_id, AssessmentSession.candidate_id == candidate_id
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    async def list_for_candidate(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> Sequence[AssessmentSession]:
        """Все сессии кандидата, от новых к старым."""
        result = await session.scalars(
            select(AssessmentSession)
            .where(AssessmentSession.candidate_id == candidate_id)
            .order_by(AssessmentSession.started_at.desc())
        )
        return result.all()

    async def active_for_candidate(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> AssessmentSession | None:
        """Незавершённая сессия кандидата, если есть."""
        return await session.scalar(
            select(AssessmentSession).where(
                AssessmentSession.candidate_id == candidate_id,
                AssessmentSession.status == SessionStatus.IN_PROGRESS,
            )
        )

    async def count_for_specialization(self, session: AsyncSession, specialization_id: int) -> int:
        """Сколько сессий начато по специализации — знаменатель доли показов семейства."""
        total = await session.scalar(
            select(func.count())
            .select_from(AssessmentSession)
            .where(AssessmentSession.specialization_id == specialization_id)
        )
        return int(total or 0)


class AssessmentItemCRUD(CRUDBase[AssessmentItem]):
    """Доступ к показанным экземплярам заданий."""

    async def list_for_session(
        self, session: AsyncSession, session_id: uuid.UUID
    ) -> Sequence[AssessmentItem]:
        """Задания сессии по порядку, с семейством и компетенцией."""
        result = await session.scalars(
            select(AssessmentItem)
            .options(selectinload(AssessmentItem.family).selectinload(ItemFamily.competency))
            .where(AssessmentItem.session_id == session_id)
            .order_by(AssessmentItem.position)
        )
        return result.all()

    async def families_seen_by_candidate(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> set[int]:
        """Семейства, которые кандидат уже видел в прошлых сессиях."""
        result = await session.scalars(
            select(AssessmentItem.family_id)
            .join(AssessmentSession, AssessmentSession.id == AssessmentItem.session_id)
            .where(AssessmentSession.candidate_id == candidate_id)
            .distinct()
        )
        return set(result.all())


class GradeHistoryCRUD(CRUDBase[GradeHistory]):
    """Доступ к истории смен категории."""

    async def list_for_candidate(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> Sequence[tuple[GradeHistory, Category]]:
        """История смен категории с целевой категорией, от новых к старым."""
        result = await session.execute(
            select(GradeHistory, Category)
            .join(Category, Category.id == GradeHistory.to_category_id)
            .options(selectinload(Category.specialization), selectinload(Category.grade))
            .where(GradeHistory.candidate_id == candidate_id)
            .order_by(GradeHistory.changed_at.desc())
        )
        return [(row[0], row[1]) for row in result.all()]

    async def last_change_at(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> datetime | None:
        """Когда категория менялась в последний раз."""
        return await session.scalar(
            select(func.max(GradeHistory.changed_at)).where(
                GradeHistory.candidate_id == candidate_id
            )
        )


competency_crud = CompetencyCRUD(Competency)
specialization_competency_crud = SpecializationCompetencyCRUD(SpecializationCompetency)
item_family_crud = ItemFamilyCRUD(ItemFamily)
survey_crud = SurveyCRUD(SurveyResponse)
assessment_session_crud = AssessmentSessionCRUD(AssessmentSession)
assessment_item_crud = AssessmentItemCRUD(AssessmentItem)
grade_history_crud = GradeHistoryCRUD(GradeHistory)
