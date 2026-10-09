import uuid
from collections.abc import Sequence
from random import SystemRandom

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ConflictError, DomainValidationError, NotFoundError
from app.crud import (
    assessment_session_crud,
    audit_log_crud,
    category_crud,
    competency_crud,
    item_family_crud,
    specialization_competency_crud,
    specialization_crud,
    vacancy_crud,
)
from app.crud.vacancy import VacancyQuery
from app.models.assessment import ItemFamily, ItemFamilyStatus
from app.models.dictionary import Category, Specialization
from app.models.user import User
from app.schemas.dictionary import GradeBrief, SpecializationBrief
from app.schemas.methodist import (
    MAX_SAMPLES,
    AssessmentSettingsRead,
    BankCompetencyRead,
    EngineSettingsRead,
    FamilyStatusUpdate,
    ItemBankRead,
    ItemFamilyRead,
    ItemSamplesRead,
    MethodistVacancyRow,
    PolicySettingsRead,
    ScaleCategory,
    SpecializationScale,
    ThetaCutUpdate,
    VacancyTestRead,
)
from app.services.assessment.adaptive_engine import ALGORITHM_VERSION, EXPRESS_CONFIG, EngineConfig
from app.services.assessment.grade_policy import PolicyConfig
from app.services.assessment.item_generators import REGISTRY
from app.services.assessment.vacancy_test_service import (
    SEED_BITS,
    VacancyTestService,
    family_read,
    instance,
)

MIN_CUT_GAP = 0.3
INTERIM_ESTIMATOR = "EAP с априорным N(0, 1): выбор заданий и правило остановки"
FINAL_ESTIMATOR = "WLE (взвешенное правдоподобие Уорма): итоговое решение о грейде"


def _engine_read(config: EngineConfig) -> EngineSettingsRead:
    """Параметры движка для экрана настроек."""
    return EngineSettingsRead(
        min_items=config.min_items,
        max_items=config.max_items,
        confidence_z=config.confidence_z,
        target_se=config.target_se,
        randomesque=config.randomesque,
        max_exposure_rate=config.max_exposure_rate,
        pilot_items=config.pilot_items,
    )


class MethodistService:
    """Кабинет методиста: банк заданий, тест под вакансию и настройки оценки.

    Экземпляры генерируются теми же генераторами, что в сессии теста, поэтому
    методист видит ровно то, что увидит кандидат. Смена статуса семейства и порога
    категории пишется в журнал аудита: от этих решений зависят грейды людей.
    """

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        """Получает сессию БД и настройки оценки."""
        self._session = session
        self._settings = settings
        self._vacancy_tests = VacancyTestService(session, settings)
        self._random = SystemRandom()

    async def item_bank(self, specialization_id: int | None) -> ItemBankRead:
        """Банк заданий целиком или компетенции одной специализации с весами."""
        specialization: Specialization | None = None
        sessions_total: int | None = None
        weights: dict[int, float] = {}
        sessions: dict[str, int]
        if specialization_id is not None:
            specialization = await self._specialization(specialization_id)
            links = await specialization_competency_crud.list_for_specialization(
                self._session, specialization_id
            )
            competencies = [competency for _, competency in links]
            weights = {competency.id: link.weight for link, competency in links}
            sessions_total = await assessment_session_crud.count_for_specialization(
                self._session, specialization_id
            )
            families = await item_family_crud.list_bank(
                self._session, [competency.id for competency in competencies]
            )
            sessions = await assessment_session_crud.count_by_competency(
                self._session, [competency.code for competency in competencies]
            )
        else:
            competencies = list(await competency_crud.list_all(self._session))
            families = await item_family_crud.list_bank(self._session)
            sessions = await assessment_session_crud.count_by_competency(
                self._session, [competency.code for competency in competencies]
            )
        return ItemBankRead(
            specialization=SpecializationBrief.model_validate(specialization)
            if specialization
            else None,
            sessions_total=sessions_total,
            competencies=[
                BankCompetencyRead(
                    code=competency.code,
                    name=competency.name,
                    description=competency.description,
                    weight=weights.get(competency.id),
                    gate_skills=list(competency.gate_skill_slugs),
                    verifies_skills=list(competency.verifies_skill_slugs),
                    active_families=sum(
                        1
                        for family in families
                        if family.competency_id == competency.id
                        and family.status is ItemFamilyStatus.ACTIVE
                    ),
                    total_families=sum(
                        1 for family in families if family.competency_id == competency.id
                    ),
                )
                for competency in competencies
            ],
            families=[family_read(family, sessions) for family in families],
        )

    async def samples(
        self, family_id: int, count: int, seeds: Sequence[int] = ()
    ) -> ItemSamplesRead:
        """Экземпляры семейства: случайные или по заданным seed для воспроизведения."""
        family = await self._family(family_id)
        spec = REGISTRY.get(family.code)
        if spec is None:
            raise ConflictError("У семейства нет генератора экземпляров")
        chosen = list(seeds)[:MAX_SAMPLES] or [
            self._random.getrandbits(SEED_BITS) for _ in range(min(count, MAX_SAMPLES))
        ]
        return ItemSamplesRead(
            family=family_read(family, None),
            instances=[instance(spec, seed) for seed in chosen],
        )

    async def set_family_status(
        self, user: User, family_id: int, payload: FamilyStatusUpdate
    ) -> ItemFamilyRead:
        """Включает семейство в оценку, переводит в пилот или выводит из ротации."""
        family = await self._family(family_id)
        status = ItemFamilyStatus(payload.status)
        if status is family.status:
            return family_read(family, None)
        if status is ItemFamilyStatus.ACTIVE and family.code not in REGISTRY:
            raise ConflictError("Нельзя включить семейство без генератора экземпляров")
        if family.status is ItemFamilyStatus.ACTIVE:
            active = await item_family_crud.count_by_competency(
                self._session, [ItemFamilyStatus.ACTIVE]
            )
            if active.get(family.competency_id, 0) <= 1:
                raise ConflictError(
                    "Это последнее активное семейство компетенции: без него компетенция "
                    "выпадет из теста. Сначала включите замену."
                )
        previous = family.status
        await item_family_crud.update(self._session, family, {"status": status})
        await audit_log_crud.record(
            self._session,
            actor_user_id=user.id,
            action="item_family_status_changed",
            entity_type="item_family",
            entity_id=str(family.id),
            meta={"code": family.code, "from": previous, "to": status, "reason": payload.reason},
        )
        await self._session.commit()
        return family_read(family, None)

    async def vacancies(self) -> list[MethodistVacancyRow]:
        """Опубликованные вакансии — из них методист выбирает, чей тест посмотреть."""
        vacancies = list(await vacancy_crud.list_published(self._session, VacancyQuery()))
        return await self._vacancy_tests.rows(vacancies)

    async def vacancy_test(self, vacancy_id: uuid.UUID) -> VacancyTestRead:
        """Вакансия → категория → состав теста → экземпляры и микрозадачи."""
        return await self._vacancy_tests.for_methodist(vacancy_id)

    async def settings(self) -> AssessmentSettingsRead:
        """Параметры алгоритма, правила пересдачи и пороги всех категорий."""
        policy = PolicyConfig(
            grade_change_cooldown_days=self._settings.grade_change_cooldown_days,
            upgrade_retry_days=self._settings.upgrade_retry_days,
            onboarding_retry_hours=self._settings.onboarding_retry_hours,
        )
        categories = await category_crud.list_filtered(self._session)
        scales: dict[int, SpecializationScale] = {}
        for category in categories:
            scale = scales.setdefault(
                category.specialization_id,
                SpecializationScale(
                    specialization=SpecializationBrief.model_validate(category.specialization),
                    categories=[],
                ),
            )
            scale.categories.append(self._scale_category(category))
        return AssessmentSettingsRead(
            algorithm_version=ALGORITHM_VERSION,
            interim_estimator=INTERIM_ESTIMATOR,
            final_estimator=FINAL_ESTIMATOR,
            full=_engine_read(EngineConfig()),
            express=_engine_read(EXPRESS_CONFIG),
            express_enabled=self._settings.assessment_express_enabled,
            policy=PolicySettingsRead(
                grade_change_cooldown_days=policy.grade_change_cooldown_days,
                upgrade_retry_days=policy.upgrade_retry_days,
                onboarding_retry_hours=policy.onboarding_retry_hours,
                confident_upgrade_window_hours=policy.confident_upgrade_window_hours,
            ),
            scales=list(scales.values()),
        )

    async def update_theta_cut(
        self, user: User, category_id: int, payload: ThetaCutUpdate
    ) -> SpecializationScale:
        """Меняет порог категории, сохраняя порядок грейдов на шкале.

        Порог должен лежать между соседними грейдами с зазором не меньше 0,3: иначе
        два грейда станут неразличимы при типичной ошибке измерения. Новый порог
        действует для тестов, завершённых после изменения; уже присвоенные
        категории не пересчитываются.
        """
        category = await category_crud.get_with_relations(self._session, category_id)
        if category is None:
            raise NotFoundError("Категория не найдена")
        siblings = await category_crud.list_filtered(
            self._session, specialization_id=category.specialization_id
        )
        value = round(payload.theta_cut, 2)
        lower = [item for item in siblings if item.grade.rank < category.grade.rank]
        higher = [item for item in siblings if item.grade.rank > category.grade.rank]
        if lower and value < max(item.theta_cut for item in lower) + MIN_CUT_GAP:
            raise DomainValidationError(
                "Порог должен быть выше порога младшего грейда хотя бы на 0,3",
                details={"field": "theta_cut"},
            )
        if higher and value > min(item.theta_cut for item in higher) - MIN_CUT_GAP:
            raise DomainValidationError(
                "Порог должен быть ниже порога старшего грейда хотя бы на 0,3",
                details={"field": "theta_cut"},
            )
        previous = category.theta_cut
        await category_crud.update(self._session, category, {"theta_cut": value})
        await audit_log_crud.record(
            self._session,
            actor_user_id=user.id,
            action="category_theta_cut_changed",
            entity_type="category",
            entity_id=str(category.id),
            meta={"code": category.code, "from": previous, "to": value, "reason": payload.reason},
        )
        await self._session.commit()
        return SpecializationScale(
            specialization=SpecializationBrief.model_validate(category.specialization),
            categories=[self._scale_category(item) for item in siblings],
        )

    async def _specialization(self, specialization_id: int) -> Specialization:
        """Специализация или 404."""
        specialization = await specialization_crud.get(self._session, specialization_id)
        if specialization is None:
            raise NotFoundError("Специализация не найдена")
        return specialization

    async def _family(self, family_id: int) -> ItemFamily:
        """Семейство со связями или 404."""
        family = await item_family_crud.get_with_relations(self._session, family_id)
        if family is None:
            raise NotFoundError("Семейство заданий не найдено")
        return family

    @staticmethod
    def _scale_category(category: Category) -> ScaleCategory:
        """Категория на шкале специализации."""
        return ScaleCategory(
            category_id=category.id,
            code=category.code,
            grade=GradeBrief.model_validate(category.grade),
            theta_cut=category.theta_cut,
            default_theta_cut=category.grade.default_theta_cut,
        )
