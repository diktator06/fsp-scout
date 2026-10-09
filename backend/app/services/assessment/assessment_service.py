import logging
import secrets
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from random import Random
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ConflictError, DomainValidationError, NotFoundError
from app.crud import (
    assessment_item_crud,
    assessment_session_crud,
    candidate_profile_crud,
    candidate_skill_crud,
    category_crud,
    competency_crud,
    grade_crud,
    grade_history_crud,
    industry_crud,
    item_family_crud,
    skill_lookup_crud,
    specialization_competency_crud,
    specialization_crud,
    survey_crud,
)
from app.crud.assessment import FamilyCounters
from app.models.assessment import (
    AssessmentItem,
    AssessmentMode,
    AssessmentSession,
    Competency,
    GradeChangeReason,
    GradeHistory,
    ItemFamily,
    ItemFamilyStatus,
    SessionOutcome,
    SessionStatus,
    SpecializationCompetency,
    SurveyResponse,
)
from app.models.candidate import CandidateProfile, SkillSource
from app.models.dictionary import Category, Grade
from app.models.user import User
from app.schemas.assessment import (
    AssessmentHistoryRead,
    BlueprintCompetency,
    BlueprintRead,
    CompetencyResult,
    EligibilityRead,
    GradeHistoryRead,
    GradeOptionRead,
    GradeScalePoint,
    IntegrityEvent,
    ItemView,
    SessionRead,
    SessionResult,
    SessionSummaryRead,
    SurveyCreate,
    SurveyRead,
)
from app.schemas.dictionary import CategoryRead, GradeBrief, SpecializationBrief
from app.services.assessment.adaptive_engine import (
    ALGORITHM_VERSION,
    EXPRESS_CONFIG,
    EngineConfig,
    PoolItem,
    select_next_item,
    should_stop,
)
from app.services.assessment.blueprint import CompetencyWeight, build_blueprint
from app.services.assessment.grade_policy import (
    GradeInfo,
    GradeOption,
    PolicyConfig,
    SessionSummary,
    evaluate_eligibility,
)
from app.services.assessment.grading import GradeLevel, decide_grade
from app.services.assessment.irt import (
    AbilityEstimate,
    ItemParameters,
    estimate_ability,
    estimate_ability_wle,
)
from app.services.assessment.item_generators import REGISTRY, generate_instance, instance_seed
from app.services.assessment.scoring import score_answer
from app.services.candidate.profile_service import CandidateProfileService

logger = logging.getLogger(__name__)

SURVEY_VERSION = "2026-10"
VERIFY_MIN_ITEMS = 2
VERIFY_MIN_SHARE = 0.6
FAST_ANSWER_SHARE = 0.12
FAST_ANSWER_MAX_MS = 8000


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


def _grade_brief(grade: Grade) -> GradeBrief:
    """Краткие сведения о грейде."""
    return GradeBrief.model_validate(grade)


def _scored(items: Sequence[AssessmentItem]) -> list[AssessmentItem]:
    """Отвеченные задания, которые влияют на результат (без пилотных)."""
    return [item for item in items if item.score is not None and not item.is_pilot]


class AssessmentService:
    """Опрос, адаптивный тест на грейд и присвоение категории.

    Сервис связывает чистые модули (blueprint, движок CAT, IRT, решение по грейду,
    политика смены грейда) с базой. Каждый публичный метод — одна транзакция.
    Сессия блокируется на время обработки ответа, поэтому двойной клик или две
    вкладки не создадут два задания на одну позицию.
    """

    def __init__(
        self, session: AsyncSession, settings: Settings, clock: Callable[[], datetime] = _now
    ) -> None:
        """Собирает конфигурацию движка и политики из настроек.

        `clock` подменяется только генератором демо-популяции: синтетические кандидаты
        проходят тест тем же сервисом, но с правдоподобным временем ответов.
        """
        self._session = session
        self._settings = settings
        self._clock = clock
        self._counters: dict[int, FamilyCounters] = {}
        self._engine = EngineConfig()
        self._policy = PolicyConfig(
            grade_change_cooldown_days=settings.grade_change_cooldown_days,
            upgrade_retry_days=settings.upgrade_retry_days,
            onboarding_retry_hours=settings.onboarding_retry_hours,
        )
        self._profiles = CandidateProfileService(session)

    async def submit_survey(self, user: User, payload: SurveyCreate) -> SurveyRead:
        """Сохраняет опрос и переносит ответы в профиль.

        Стек из опроса записывается в навыки профиля как заявленный (не подтверждённый).
        Опыт и форматы работы обновляют анкету: человеку не нужно заполнять одно и
        то же дважды.
        """
        profile = await self._profiles.ensure_profile(user, for_update=True)
        specialization = await specialization_crud.get(self._session, payload.specialization_id)
        grade = await grade_crud.get(self._session, payload.claimed_grade_id)
        if specialization is None:
            raise DomainValidationError(
                "Специализация не найдена", details={"field": "specialization_id"}
            )
        if grade is None:
            raise DomainValidationError("Грейд не найден", details={"field": "claimed_grade_id"})
        missing_skills = sorted(
            set(payload.primary_skill_ids)
            - await skill_lookup_crud.existing_ids(self._session, payload.primary_skill_ids)
        )
        if missing_skills:
            raise DomainValidationError(
                "Указаны несуществующие навыки", details={"skill_ids": missing_skills}
            )
        known_industries = {item.id for item in await industry_crud.list_all(self._session)}
        if set(payload.industry_ids) - known_industries:
            raise DomainValidationError(
                "Указаны несуществующие отрасли", details={"field": "industry_ids"}
            )

        survey = await survey_crud.create(
            self._session,
            {
                "candidate_id": profile.id,
                "specialization_id": specialization.id,
                "claimed_grade_id": grade.id,
                "industry_ids": payload.industry_ids,
                "primary_skill_ids": payload.primary_skill_ids,
                "experience_years": payload.experience_years,
                "team_roles": list(payload.team_roles),
                "answers": {"work_formats": [str(item) for item in payload.work_formats]},
                "survey_version": SURVEY_VERSION,
            },
        )
        profile_changes: dict[str, Any] = {"experience_years": payload.experience_years}
        if payload.team_roles:
            profile_changes["team_roles"] = list(payload.team_roles)
        if payload.work_formats:
            profile_changes["work_formats"] = [str(item) for item in payload.work_formats]
        await candidate_profile_crud.update(self._session, profile, profile_changes)
        await candidate_skill_crud.upsert_declared(
            self._session, profile.id, dict.fromkeys(payload.primary_skill_ids), SkillSource.SURVEY
        )
        await self._commit()
        return await self._survey_view(survey)

    async def latest_survey(self, user: User) -> SurveyRead | None:
        """Последний опрос кандидата."""
        profile = await self._profiles.ensure_profile(user)
        await self._commit()
        survey = await survey_crud.latest_for_candidate(self._session, profile.id)
        return await self._survey_view(survey) if survey else None

    async def preview_blueprint(
        self, specialization_id: int, skill_ids: Sequence[int]
    ) -> BlueprintRead:
        """Из каких компетенций будет состоять тест при выбранной специализации и стеке."""
        specialization = await specialization_crud.get(self._session, specialization_id)
        if specialization is None:
            raise NotFoundError("Специализация не найдена")
        skill_slugs = await skill_lookup_crud.skill_slugs(self._session, skill_ids)
        weights, competencies = await self._blueprint(specialization.id, skill_slugs)
        sizes = await item_family_crud.count_by_competency(self._session, [ItemFamilyStatus.ACTIVE])
        return BlueprintRead(
            specialization=SpecializationBrief.model_validate(specialization),
            competencies=[
                BlueprintCompetency(
                    code=competency.code,
                    name=competency.name,
                    weight=weights.get(competency.code, 0.0),
                    bank_size=sizes.get(competency.id, 0),
                    included=competency.code in weights,
                )
                for _, competency in competencies
            ],
            min_items=self._engine.min_items,
            max_items=self._engine.max_items,
            available=bool(weights),
        )

    async def eligibility(self, user: User) -> EligibilityRead:
        """Какие тесты кандидат может пройти сейчас."""
        profile = await self._profiles.ensure_profile(user)
        await self._commit()
        options = await self._grade_options(profile)
        active = await assessment_session_crud.active_for_candidate(self._session, profile.id)
        survey = await survey_crud.latest_for_candidate(self._session, profile.id)
        return EligibilityRead(
            express_available=self._settings.assessment_express_enabled,
            current_category=self._category_view(profile.current_category),
            active_session_id=active.id if active else None,
            survey=await self._survey_view(survey) if survey else None,
            options=[
                GradeOptionRead(
                    grade=GradeBrief(
                        id=option.grade.grade_id,
                        code=option.grade.code,
                        name=option.grade.name,
                        rank=option.grade.rank,
                    ),
                    allowed=option.allowed,
                    reason=option.reason,
                    available_at=option.available_at,
                )
                for option in options
            ],
        )

    async def start_session(
        self, user: User, target_grade_id: int, mode: AssessmentMode = AssessmentMode.FULL
    ) -> SessionRead:
        """Начинает адаптивный тест на выбранный грейд по последнему опросу.

        Экспресс-режим (6–8 заданий) нужен для демонстрации и ручной проверки жюри:
        менторы попросили дать возможность пройти тест за несколько минут. Механика та
        же, меньше только длина. Режим сохраняется в сессии и виден в результате.
        """
        now = self._clock()
        if mode is AssessmentMode.EXPRESS and not self._settings.assessment_express_enabled:
            raise DomainValidationError("Экспресс-режим на этом стенде выключен")
        engine = self._engine_for(mode)
        profile = await self._profiles.ensure_profile(user, for_update=True)
        survey = await survey_crud.latest_for_candidate(self._session, profile.id)
        if survey is None:
            raise DomainValidationError(
                "Сначала пройдите опрос: он определяет специализацию и состав теста"
            )
        target = await grade_crud.get(self._session, target_grade_id)
        if target is None:
            raise DomainValidationError("Грейд не найден", details={"field": "target_grade_id"})

        option = next(
            o for o in await self._grade_options(profile, now) if o.grade.grade_id == target.id
        )
        if not option.allowed:
            raise ConflictError(
                option.reason,
                details={
                    "available_at": option.available_at.isoformat() if option.available_at else None
                },
            )

        skill_slugs = await skill_lookup_crud.skill_slugs(self._session, survey.primary_skill_ids)
        blueprint, _ = await self._blueprint(survey.specialization_id, skill_slugs)
        if not blueprint:
            raise DomainValidationError("Для этой специализации банк заданий пока не готов")

        pilots = await self._pilot_families(blueprint)
        pilot_positions = (
            sorted(
                Random(secrets.randbits(32)).sample(
                    range(3, engine.min_items + 1), engine.pilot_items
                )
            )
            if pilots and engine.pilot_items
            else []
        )
        assessment = await assessment_session_crud.create(
            self._session,
            {
                "candidate_id": profile.id,
                "survey_response_id": survey.id,
                "specialization_id": survey.specialization_id,
                "target_grade_id": target.id,
                "status": SessionStatus.IN_PROGRESS,
                "mode": mode,
                "seed_salt": secrets.token_hex(16),
                "blueprint": blueprint,
                "pilot_positions": pilot_positions,
                "algorithm_version": ALGORITHM_VERSION,
                "started_at": now,
                "expires_at": now + timedelta(minutes=self._settings.assessment_session_minutes),
            },
        )
        await self._advance(assessment, profile, [], now)
        await self._commit()
        logger.info("Начата сессия %s на грейд %s", assessment.id, target.code)
        return await self._session_view(assessment, profile)

    async def get_session(self, user: User, session_id: uuid.UUID) -> SessionRead:
        """Состояние сессии. Попутно закрывает просроченное задание или всю сессию.

        Если кандидат закрыл вкладку и вернулся после дедлайна, задание засчитывается
        как неотвеченное, и тест продолжается со следующего. Таймер живёт на сервере,
        а не в браузере.
        """
        profile = await self._profiles.ensure_profile(user, for_update=True)
        assessment = await self._owned_session(profile, session_id, for_update=True)
        if assessment.status is SessionStatus.IN_PROGRESS:
            await self._handle_timeouts(assessment, profile, self._clock())
        await self._commit()
        return await self._session_view(assessment, profile)

    async def submit_answer(
        self, user: User, session_id: uuid.UUID, item_id: uuid.UUID, answer: str
    ) -> SessionRead:
        """Принимает ответ на текущее задание, пересчитывает θ и выдаёт следующее задание.

        Правильность ответа кандидату не сообщается: иначе ключи ответов можно было бы
        собирать и распространять. Результат по компетенциям виден только в итоге теста.
        """
        now = self._clock()
        profile = await self._profiles.ensure_profile(user, for_update=True)
        assessment = await self._owned_session(profile, session_id, for_update=True)
        if not self._is_active(assessment):
            raise ConflictError("Тест уже завершён")
        await self._handle_timeouts(assessment, profile, now)
        if not self._is_active(assessment):
            await self._commit()
            return await self._session_view(assessment, profile)

        items = list(await assessment_item_crud.list_for_session(self._session, assessment.id))
        current = next((item for item in items if item.answered_at is None), None)
        if current is None or current.id != item_id:
            raise ConflictError("Это задание уже закрыто, обновите страницу")

        elapsed_ms = int((now - current.presented_at).total_seconds() * 1000)
        score = score_answer(current.answer_key, answer)
        await assessment_item_crud.update(
            self._session,
            current,
            {
                "response": {"raw": answer},
                "score": score,
                "answered_at": now,
                "response_time_ms": elapsed_ms,
            },
        )
        self._count_response(current.family_id, correct=score >= 1.0)
        if score >= 1.0 and elapsed_ms < min(
            FAST_ANSWER_MAX_MS, FAST_ANSWER_SHARE * current.family.time_limit_sec * 1000
        ):
            await self._bump_integrity(assessment, "fast_correct")
        await self._after_answer(assessment, profile, items, now)
        await self._commit()
        return await self._session_view(assessment, profile)

    async def abandon(self, user: User, session_id: uuid.UUID) -> SessionRead:
        """Прерывает тест. Попытка учитывается в лимите, грейд не меняется."""
        profile = await self._profiles.ensure_profile(user, for_update=True)
        assessment = await self._owned_session(profile, session_id, for_update=True)
        if assessment.status is not SessionStatus.IN_PROGRESS:
            raise ConflictError("Тест уже завершён")
        await assessment_session_crud.update(
            self._session,
            assessment,
            {"status": SessionStatus.ABANDONED, "finished_at": self._clock()},
        )
        await self._commit()
        return await self._session_view(assessment, profile)

    async def record_integrity_event(
        self, user: User, session_id: uuid.UUID, event: IntegrityEvent
    ) -> None:
        """Учитывает сигнал целостности (потеря фокуса, вставка текста).

        Такие события не прерывают тест и не меняют оценку автоматически. Они
        отображаются в результате и при необходимости требуют подтвердить уровень
        микрозадачей.
        """
        profile = await self._profiles.ensure_profile(user)
        assessment = await self._owned_session(profile, session_id, for_update=True)
        if assessment.status is SessionStatus.IN_PROGRESS:
            await self._bump_integrity(assessment, event)
            await self._commit()

    async def accept_suggested_grade(self, user: User, session_id: uuid.UUID) -> SessionRead:
        """Присваивает предложенный нижний грейд без пересдачи (только в онбординге)."""
        now = self._clock()
        profile = await self._profiles.ensure_profile(user, for_update=True)
        assessment = await self._owned_session(profile, session_id, for_update=True)
        if not await self._can_accept_suggested(assessment, profile):
            raise ConflictError("Предложенный грейд принять нельзя")
        category = await category_crud.get_by_pair(
            self._session, assessment.specialization_id, assessment.suggested_grade_id or 0
        )
        if category is None:
            raise NotFoundError("Категория не найдена")
        await self._assign_category(
            profile, category, GradeChangeReason.ACCEPTED_LOWER, assessment, now
        )
        await assessment_session_crud.update(
            self._session, assessment, {"resulting_category_id": category.id}
        )
        await self._commit()
        return await self._session_view(assessment, profile)

    async def history(self, user: User) -> AssessmentHistoryRead:
        """История тестов и смен категории."""
        profile = await self._profiles.ensure_profile(user)
        await self._commit()
        sessions = await assessment_session_crud.list_for_candidate(self._session, profile.id)
        specializations = {s.id: s for s in await specialization_crud.list_all(self._session)}
        grades = {g.id: g for g in await grade_crud.list_all(self._session)}
        changes = await grade_history_crud.list_for_candidate(self._session, profile.id)
        return AssessmentHistoryRead(
            sessions=[
                SessionSummaryRead(
                    id=item.id,
                    status=item.status,
                    mode=item.mode,
                    outcome=item.outcome,
                    specialization=SpecializationBrief.model_validate(
                        specializations[item.specialization_id]
                    ),
                    target_grade=_grade_brief(grades[item.target_grade_id]),
                    items_scored=item.items_scored,
                    theta=round(item.theta, 3) if item.status is SessionStatus.COMPLETED else None,
                    started_at=item.started_at,
                    finished_at=item.finished_at,
                )
                for item in sessions
            ],
            grade_changes=[
                GradeHistoryRead(
                    category=CategoryRead.model_validate(category),
                    reason=change.reason,
                    changed_at=change.changed_at,
                    session_id=change.session_id,
                )
                for change, category in changes
            ],
        )

    def _count_response(self, family_id: int, *, correct: bool) -> None:
        """Учитывает ответ на семейство (для калибровки и детектора дрейфа)."""
        counters = self._counters.setdefault(family_id, FamilyCounters())
        counters.responses += 1
        counters.correct += int(correct)

    async def _commit(self) -> None:
        """Фиксирует транзакцию, перед этим применяя накопленные счётчики семейств.

        Счётчики общие для всех кандидатов. Если обновлять их по ходу сценария, две
        параллельные сессии захватывают строки семейств в разном порядке и ловят
        взаимоблокировку. Отложенное применение в порядке id это исключает.
        """
        if self._counters:
            await item_family_crud.apply_counters(self._session, self._counters)
            self._counters = {}
        await self._session.commit()

    async def _owned_session(
        self, profile: CandidateProfile, session_id: uuid.UUID, *, for_update: bool = False
    ) -> AssessmentSession:
        """Сессия кандидата или 404: чужие сессии для него не существуют."""
        assessment = await assessment_session_crud.get_for_candidate(
            self._session, session_id, profile.id, for_update=for_update
        )
        if assessment is None:
            raise NotFoundError("Сессия тестирования не найдена")
        return assessment

    async def _grade_options(
        self, profile: CandidateProfile, now: datetime | None = None
    ) -> list[GradeOption]:
        """Варианты грейдов по политике смены грейда."""
        grades = await grade_crud.list_all(self._session)
        rank_by_id = {g.id: g.rank for g in grades}
        sessions = await assessment_session_crud.list_for_candidate(self._session, profile.id)
        changes = await grade_history_crud.list_for_candidate(self._session, profile.id)
        rank_before = self._ranks_before_sessions(sessions, changes, rank_by_id)
        current_rank = profile.current_category.grade.rank if profile.current_category else None
        return evaluate_eligibility(
            grades=[
                GradeInfo(grade_id=g.id, code=g.code, name=g.name, rank=g.rank) for g in grades
            ],
            current_rank=current_rank,
            last_change_at=await grade_history_crud.last_change_at(self._session, profile.id),
            sessions=[
                SessionSummary(
                    status=item.status,
                    target_rank=rank_by_id[item.target_grade_id],
                    outcome=item.outcome,
                    started_at=item.started_at,
                    finished_at=item.finished_at,
                    rank_before=rank_before.get(item.id),
                )
                for item in sessions
            ],
            now=now or self._clock(),
            config=self._policy,
        )

    @staticmethod
    def _ranks_before_sessions(
        sessions: Sequence[AssessmentSession],
        changes: Sequence[tuple[GradeHistory, Category]],
        rank_by_id: dict[int, int],
    ) -> dict[uuid.UUID, int | None]:
        """Какой грейд был у кандидата в момент начала каждой сессии.

        Нужен, чтобы отличить неудачную попытку повышения от неудачи в онбординге:
        только первая включает 30-дневную паузу.
        """
        history = sorted(
            ((change.changed_at, rank_by_id[category.grade_id]) for change, category in changes)
        )
        result: dict[uuid.UUID, int | None] = {}
        for item in sessions:
            before = [rank for changed_at, rank in history if changed_at <= item.started_at]
            result[item.id] = before[-1] if before else None
        return result

    async def _blueprint(
        self, specialization_id: int, skill_slugs: Sequence[str]
    ) -> tuple[dict[str, float], Sequence[tuple[SpecializationCompetency, Competency]]]:
        """Blueprint специализации под стек кандидата и компетенции с весами."""
        competencies = await specialization_competency_crud.list_for_specialization(
            self._session, specialization_id
        )
        sizes = await item_family_crud.count_by_competency(self._session, [ItemFamilyStatus.ACTIVE])
        weights = build_blueprint(
            [
                CompetencyWeight(
                    code=competency.code,
                    weight=link.weight,
                    gate_skill_slugs=tuple(competency.gate_skill_slugs),
                )
                for link, competency in competencies
            ],
            skill_slugs,
            [competency.code for _, competency in competencies if sizes.get(competency.id, 0) > 0],
        )
        return weights, competencies

    async def _pilot_families(self, blueprint: dict[str, float]) -> list[ItemFamily]:
        """Пилотные семейства по компетенциям теста."""
        competency_ids = await self._competency_ids(blueprint)
        return list(
            await item_family_crud.list_for_competencies(
                self._session, competency_ids, [ItemFamilyStatus.PILOT]
            )
        )

    async def _competency_ids(self, blueprint: dict[str, float]) -> list[int]:
        """Идентификаторы компетенций из blueprint."""
        return await competency_crud.ids_by_codes(self._session, blueprint)

    async def _handle_timeouts(
        self, assessment: AssessmentSession, profile: CandidateProfile, now: datetime
    ) -> None:
        """Закрывает просроченное задание (счёт 0) или всю сессию по общему лимиту времени."""
        if now >= assessment.expires_at:
            await assessment_session_crud.update(
                self._session, assessment, {"status": SessionStatus.EXPIRED, "finished_at": now}
            )
            return
        items = list(await assessment_item_crud.list_for_session(self._session, assessment.id))
        current = next((item for item in items if item.answered_at is None), None)
        grace = timedelta(seconds=self._settings.item_grace_seconds)
        if current is not None and now > current.deadline_at + grace:
            await assessment_item_crud.update(
                self._session,
                current,
                {"score": 0.0, "timed_out": True, "answered_at": now, "response": {"raw": None}},
            )
            self._count_response(current.family_id, correct=False)
            await self._after_answer(assessment, profile, items, now)

    async def _after_answer(
        self,
        assessment: AssessmentSession,
        profile: CandidateProfile,
        items: list[AssessmentItem],
        now: datetime,
    ) -> None:
        """Пересчитывает θ по засчитываемым ответам и решает: следующее задание или итог."""
        estimate = self._estimate(items)
        scored = _scored(items)
        if scored:
            last = scored[-1]
            await assessment_item_crud.update(
                self._session, last, {"theta_after": estimate.theta, "se_after": estimate.se}
            )
        await assessment_session_crud.update(
            self._session,
            assessment,
            {"theta": estimate.theta, "theta_se": estimate.se, "items_scored": len(scored)},
        )
        await self._advance(assessment, profile, items, now)

    @staticmethod
    def _responses(items: Sequence[AssessmentItem]) -> list[tuple[ItemParameters, float]]:
        """Засчитываемые ответы сессии с параметрами семейств."""
        return [
            (
                ItemParameters(a=item.family.irt_a, b=item.family.irt_b, c=item.family.irt_c),
                item.score or 0.0,
            )
            for item in _scored(items)
        ]

    @classmethod
    def _estimate(cls, items: Sequence[AssessmentItem]) -> AbilityEstimate:
        """EAP-оценка θ по ходу теста: устойчива на первых ответах, по ней подбираются задания."""
        return estimate_ability(cls._responses(items))

    @classmethod
    def _final_estimate(cls, items: Sequence[AssessmentItem]) -> AbilityEstimate:
        """Итоговая оценка для решения о грейде — WLE, без стягивания к среднему популяции.

        Почему не EAP, показала валидация: EAP занижала θ сильным кандидатам на
        0,4–0,6 и переводила часть сеньоров в мидлы (docs/VALIDATION.md).
        """
        return estimate_ability_wle(cls._responses(items))

    async def _advance(
        self,
        assessment: AssessmentSession,
        profile: CandidateProfile,
        items: list[AssessmentItem],
        now: datetime,
    ) -> None:
        """Выдаёт следующее задание или завершает тест по правилу остановки."""
        estimate = self._estimate(items)
        position = len(items) + 1
        used = {item.family_id for item in items}
        cut = await self._target_cut(assessment)
        engine = self._engine_for(assessment.mode)

        if position in assessment.pilot_positions:
            pilot = await self._pick_pilot(assessment, used, position)
            if pilot is not None:
                item = await self._create_item(assessment, pilot, position, now, is_pilot=True)
                items.append(item)
                return

        pool = await self._pool(assessment, profile, used)
        if should_stop(
            scored_items=len(_scored(items)),
            estimate=estimate,
            cut=cut,
            config=engine,
            pool_exhausted=not pool,
        ):
            await self._finish(assessment, profile, items, now)
            return

        rng = Random(
            instance_seed(
                self._settings.assessment_secret, assessment.seed_salt, position, "select"
            )
        )
        administered = [item.family.competency.code for item in items if not item.is_pilot]
        chosen = select_next_item(
            [entry for entry, _ in pool],
            assessment.blueprint,
            administered,
            estimate,
            rng,
            engine,
        )
        if chosen is None:
            await self._finish(assessment, profile, items, now)
            return
        family = next(family for entry, family in pool if entry.family_id == chosen.family_id)
        items.append(await self._create_item(assessment, family, position, now, is_pilot=False))

    async def _pool(
        self, assessment: AssessmentSession, profile: CandidateProfile, used: set[int]
    ) -> list[tuple[PoolItem, ItemFamily]]:
        """Активные семейства компетенций теста, ещё не показанные в этой сессии.

        Семейства из прошлых попыток кандидата помечаются `seen_before` и получают
        пониженный приоритет, а доля показов семейства передаётся контролю экспозиции.
        Доля считается от сессий, в тест которых входила компетенция семейства, —
        не от сессий специализации: компетенции общие для нескольких специализаций.
        """
        competency_ids = await self._competency_ids(assessment.blueprint)
        families = await item_family_crud.list_for_competencies(
            self._session, competency_ids, [ItemFamilyStatus.ACTIVE]
        )
        seen = await assessment_item_crud.families_seen_by_candidate(self._session, profile.id)
        sessions = await assessment_session_crud.count_by_competency(
            self._session, assessment.blueprint.keys()
        )
        return [
            (
                PoolItem(
                    family_id=family.id,
                    code=family.code,
                    competency=family.competency.code,
                    params=ItemParameters(a=family.irt_a, b=family.irt_b, c=family.irt_c),
                    exposure_rate=family.exposure_count
                    / max(1, sessions.get(family.competency.code, 0)),
                    seen_before=family.id in seen,
                ),
                family,
            )
            for family in families
            if family.id not in used and family.code in REGISTRY
        ]

    async def _pick_pilot(
        self, assessment: AssessmentSession, used: set[int], position: int
    ) -> ItemFamily | None:
        """Случайное пилотное семейство, ещё не показанное в сессии."""
        candidates = [
            family
            for family in await self._pilot_families(assessment.blueprint)
            if family.id not in used and family.code in REGISTRY
        ]
        if not candidates:
            return None
        rng = Random(
            instance_seed(self._settings.assessment_secret, assessment.seed_salt, position, "pilot")
        )
        return rng.choice(candidates)

    async def _create_item(
        self,
        assessment: AssessmentSession,
        family: ItemFamily,
        position: int,
        now: datetime,
        *,
        is_pilot: bool,
    ) -> AssessmentItem:
        """Генерирует уникальный экземпляр семейства и сохраняет его вместе с ключом ответа."""
        seed = instance_seed(
            self._settings.assessment_secret, assessment.seed_salt, position, family.code
        )
        generated = generate_instance(REGISTRY[family.code], seed)
        payload = generated.client_payload() | {
            "competency": family.competency.code,
            "competency_name": family.competency.name,
        }
        answer_key = generated.answer | {
            "explanation": generated.explanation,
            "params": generated.params,
        }
        item = await assessment_item_crud.create(
            self._session,
            {
                "session_id": assessment.id,
                "family_id": family.id,
                "position": position,
                "is_pilot": is_pilot,
                "instance_seed": seed,
                "payload": payload,
                "answer_key": answer_key,
                "presented_at": now,
                "deadline_at": now + timedelta(seconds=family.time_limit_sec),
            },
        )
        self._counters.setdefault(family.id, FamilyCounters()).exposures += 1
        item.family = family
        return item

    async def _target_cut(self, assessment: AssessmentSession) -> float:
        """Порог θ категории «специализация × заявленный грейд»."""
        category = await category_crud.get_by_pair(
            self._session, assessment.specialization_id, assessment.target_grade_id
        )
        if category is None:
            raise NotFoundError("Категория для теста не найдена")
        return category.theta_cut

    async def _levels(self, specialization_id: int) -> list[GradeLevel]:
        """Грейды специализации с порогами её категорий."""
        categories = await category_crud.list_filtered(
            self._session, specialization_id=specialization_id
        )
        return [
            GradeLevel(
                grade_id=c.grade_id, code=c.grade.code, rank=c.grade.rank, theta_cut=c.theta_cut
            )
            for c in categories
        ]

    async def _finish(
        self,
        assessment: AssessmentSession,
        profile: CandidateProfile,
        items: Sequence[AssessmentItem],
        now: datetime,
    ) -> None:
        """Завершает тест: решение по грейду, присвоение категории, подтверждение навыков."""
        estimate = self._final_estimate(items)
        levels = await self._levels(assessment.specialization_id)
        target = next(level for level in levels if level.grade_id == assessment.target_grade_id)
        decision = decide_grade(estimate, target, levels)
        changes: dict[str, Any] = {
            "status": SessionStatus.COMPLETED,
            "outcome": decision.outcome,
            "finished_at": now,
            "theta": estimate.theta,
            "theta_se": estimate.se,
            "items_scored": len(_scored(items)),
            "suggested_grade_id": decision.suggested_lower.grade_id
            if decision.suggested_lower
            else None,
        }
        if decision.outcome is not SessionOutcome.FAILED:
            category = await category_crud.get_by_pair(
                self._session, assessment.specialization_id, assessment.target_grade_id
            )
            if category is not None:
                current = profile.current_category
                if current is None or current.id != category.id:
                    if current is None:
                        reason = GradeChangeReason.INITIAL
                    elif target.rank > current.grade.rank:
                        reason = GradeChangeReason.UPGRADE
                    else:
                        reason = GradeChangeReason.DOWNGRADE_VOLUNTARY
                    await self._assign_category(profile, category, reason, assessment, now)
                changes["resulting_category_id"] = category.id
            await self._verify_skills(profile, items, now)
        await assessment_session_crud.update(self._session, assessment, changes)
        logger.info(
            "Сессия %s завершена: %s, θ=%.2f±%.2f",
            assessment.id,
            decision.outcome.value,
            estimate.theta,
            estimate.se,
        )

    async def _assign_category(
        self,
        profile: CandidateProfile,
        category: Category,
        reason: GradeChangeReason,
        assessment: AssessmentSession,
        now: datetime,
    ) -> None:
        """Присваивает категорию и пишет смену в историю (на ней держится кулдаун)."""
        previous = profile.current_category_id
        await candidate_profile_crud.set_category(self._session, profile, category, now)
        await grade_history_crud.create(
            self._session,
            {
                "candidate_id": profile.id,
                "from_category_id": previous,
                "to_category_id": category.id,
                "reason": reason,
                "session_id": assessment.id,
                "changed_at": now,
            },
        )

    async def _verify_skills(
        self, profile: CandidateProfile, items: Sequence[AssessmentItem], now: datetime
    ) -> None:
        """Отмечает навыки подтверждёнными по компетенциям с уверенным результатом."""
        totals: defaultdict[int, list[float]] = defaultdict(list)
        competencies = {}
        for item in _scored(items):
            totals[item.family.competency_id].append(item.score or 0.0)
            competencies[item.family.competency_id] = item.family.competency
        slugs = [
            slug
            for competency_id, scores in totals.items()
            if len(scores) >= VERIFY_MIN_ITEMS and sum(scores) / len(scores) >= VERIFY_MIN_SHARE
            for slug in competencies[competency_id].verifies_skill_slugs
        ]
        ids = await skill_lookup_crud.ids_by_slugs(self._session, slugs)
        await candidate_skill_crud.mark_verified(self._session, profile.id, ids.values(), now)

    async def _can_accept_suggested(
        self, assessment: AssessmentSession, profile: CandidateProfile
    ) -> bool:
        """Принять нижний грейд можно, если он предложен, ещё не принят и не хуже текущего."""
        if (
            assessment.status is not SessionStatus.COMPLETED
            or assessment.outcome is not SessionOutcome.FAILED
            or assessment.suggested_grade_id is None
            or assessment.resulting_category_id is not None
        ):
            return False
        if profile.current_category is None:
            return True
        suggested = await grade_crud.get(self._session, assessment.suggested_grade_id)
        return suggested is not None and suggested.rank > profile.current_category.grade.rank

    def _engine_for(self, mode: AssessmentMode) -> EngineConfig:
        """Конфигурация движка для режима сессии."""
        return EXPRESS_CONFIG if mode is AssessmentMode.EXPRESS else self._engine

    @staticmethod
    def _is_active(assessment: AssessmentSession) -> bool:
        """Сессия ещё идёт (статус может смениться внутри обработки таймаутов)."""
        return assessment.status is SessionStatus.IN_PROGRESS

    async def _bump_integrity(self, assessment: AssessmentSession, key: str) -> None:
        """Увеличивает счётчик сигнала целостности.

        JSON переписывается целиком: изменение вложенного словаря ORM сама не заметит.
        """
        counters = dict(assessment.integrity or {})
        counters[key] = int(counters.get(key, 0)) + 1
        await assessment_session_crud.update(self._session, assessment, {"integrity": counters})

    @staticmethod
    def _category_view(category: Category | None) -> CategoryRead | None:
        """Категория для ответа API."""
        return CategoryRead.model_validate(category) if category is not None else None

    async def _survey_view(self, survey: SurveyResponse) -> SurveyRead:
        """Опрос для ответа API."""
        specialization = await specialization_crud.get(self._session, survey.specialization_id)
        grade = await grade_crud.get(self._session, survey.claimed_grade_id)
        if specialization is None or grade is None:
            raise NotFoundError("Справочник опроса изменился")
        return SurveyRead(
            id=survey.id,
            specialization=SpecializationBrief.model_validate(specialization),
            claimed_grade=_grade_brief(grade),
            industry_ids=survey.industry_ids,
            primary_skill_ids=survey.primary_skill_ids,
            experience_years=survey.experience_years,
            team_roles=survey.team_roles,
            created_at=survey.created_at,
        )

    async def _session_view(
        self, assessment: AssessmentSession, profile: CandidateProfile
    ) -> SessionRead:
        """Состояние сессии для кандидата: текущее задание или итог."""
        now = self._clock()
        items = list(await assessment_item_crud.list_for_session(self._session, assessment.id))
        specialization = await specialization_crud.get(self._session, assessment.specialization_id)
        target = await grade_crud.get(self._session, assessment.target_grade_id)
        if specialization is None or target is None:
            raise NotFoundError("Справочник сессии изменился")

        current_item = None
        if assessment.status is SessionStatus.IN_PROGRESS:
            current = next((item for item in items if item.answered_at is None), None)
            if current is not None:
                current_item = ItemView(
                    id=current.id,
                    position=current.position,
                    competency=current.payload["competency"],
                    competency_name=current.payload["competency_name"],
                    prompt=current.payload["prompt"],
                    response_format=current.payload["response_format"],
                    options=current.payload.get("options", []),
                    code=current.payload.get("code"),
                    code_language=current.payload.get("code_language"),
                    tables=current.payload.get("tables", []),
                    input_hint=current.payload.get("input_hint"),
                    unit=current.payload.get("unit"),
                    time_limit_sec=current.family.time_limit_sec,
                    deadline_at=current.deadline_at,
                    seconds_left=max(0, int((current.deadline_at - now).total_seconds())),
                )

        result = None
        if assessment.status is SessionStatus.COMPLETED and assessment.outcome is not None:
            result = await self._result_view(assessment, profile, items, target)
        return SessionRead(
            id=assessment.id,
            status=assessment.status,
            specialization=SpecializationBrief.model_validate(specialization),
            target_grade=_grade_brief(target),
            answered=len([item for item in items if item.answered_at is not None]),
            mode=assessment.mode,
            min_items=self._engine_for(assessment.mode).min_items,
            max_items=self._engine_for(assessment.mode).max_items + len(assessment.pilot_positions),
            started_at=assessment.started_at,
            expires_at=assessment.expires_at,
            finished_at=assessment.finished_at,
            current_item=current_item,
            result=result,
        )

    async def _result_view(
        self,
        assessment: AssessmentSession,
        profile: CandidateProfile,
        items: Sequence[AssessmentItem],
        target: Grade,
    ) -> SessionResult:
        """Итог теста: решение, шкала грейдов и результаты по компетенциям."""
        categories = await category_crud.list_filtered(
            self._session, specialization_id=assessment.specialization_id
        )
        grades = {c.grade_id: c.grade for c in categories}
        resulting = next((c for c in categories if c.id == assessment.resulting_category_id), None)
        breakdown: dict[str, CompetencyResult] = {}
        for item in _scored(items):
            competency = item.family.competency
            entry = breakdown.setdefault(
                competency.code,
                CompetencyResult(code=competency.code, name=competency.name, answered=0, correct=0),
            )
            entry.answered += 1
            entry.correct += int((item.score or 0.0) >= 1.0)

        levels = sorted(categories, key=lambda c: c.grade.rank)
        next_grade = None
        if assessment.outcome is SessionOutcome.PASSED_CONFIDENT:
            higher = [c.grade for c in levels if c.grade.rank > target.rank]
            next_grade = _grade_brief(higher[0]) if higher else None
        suggested = (
            grades.get(assessment.suggested_grade_id) if assessment.suggested_grade_id else None
        )
        can_accept = await self._can_accept_suggested(assessment, profile)
        return SessionResult(
            outcome=assessment.outcome or SessionOutcome.FAILED,
            theta=round(assessment.theta, 3),
            theta_se=round(assessment.theta_se, 3),
            items_scored=assessment.items_scored,
            target_grade=_grade_brief(target),
            resulting_category=CategoryRead.model_validate(resulting) if resulting else None,
            suggested_grade=_grade_brief(suggested) if suggested else None,
            can_accept_suggested=can_accept,
            next_grade_unlocked=next_grade,
            competencies=sorted(breakdown.values(), key=lambda entry: -entry.answered),
            scale=[
                GradeScalePoint(grade=_grade_brief(c.grade), theta_cut=c.theta_cut) for c in levels
            ],
            integrity_flags={
                key: int(value) for key, value in (assessment.integrity or {}).items()
            },
        )
