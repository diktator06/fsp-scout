import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.assessment import ItemFamilyStatus, ItemOrigin, ResponseFormat
from app.models.matching import SkillImportance
from app.models.microtask import MicroTaskKind
from app.schemas.assessment import ItemOption, ItemTable
from app.schemas.dictionary import GradeBrief, SpecializationBrief

MIN_THETA_CUT = -3.0
MAX_THETA_CUT = 3.0
MAX_SAMPLES = 5


class CompetencyBrief(BaseModel):
    """Компетенция теста."""

    code: str
    name: str


class ItemFamilyRead(BaseModel):
    """Семейство заданий банка: параметры модели, статус и статистика показов."""

    id: int
    code: str
    title: str
    competency: CompetencyBrief
    nominal_grade: GradeBrief
    response_format: ResponseFormat
    irt_a: float = Field(description="Дискриминативность")
    irt_b: float = Field(description="Сложность по шкале θ")
    irt_c: float = Field(description="Угадывание")
    time_limit_sec: int
    status: ItemFamilyStatus
    origin: ItemOrigin
    exposure_count: int
    exposure_rate: float | None = Field(
        description="Доля сессий с компетенцией семейства, где оно было показано"
    )
    responses_count: int
    correct_rate: float | None
    calibrated_at: datetime | None
    version: int
    has_generator: bool = Field(description="Есть генератор экземпляров в коде")


class BankCompetencyRead(BaseModel):
    """Компетенция в банке: вес в специализации и размер банка."""

    code: str
    name: str
    description: str
    weight: float | None = Field(description="Вес в blueprint выбранной специализации")
    gate_skills: list[str] = Field(description="Без одного из этих навыков компетенции нет в тесте")
    verifies_skills: list[str] = Field(description="Какие навыки подтверждает компетенция")
    active_families: int
    total_families: int


class ItemBankRead(BaseModel):
    """Банк заданий: компетенции и семейства, при фильтре — одной специализации."""

    specialization: SpecializationBrief | None
    sessions_total: int | None
    competencies: list[BankCompetencyRead]
    families: list[ItemFamilyRead]


class InstancePayload(BaseModel):
    """Условие экземпляра — ровно то, что получит кандидат."""

    prompt: str
    response_format: ResponseFormat
    options: list[ItemOption] = Field(default_factory=list)
    code: str | None = None
    code_language: str | None = None
    tables: list[ItemTable] = Field(default_factory=list)
    input_hint: str | None = None
    unit: str | None = None


class InstanceAnswer(BaseModel):
    """Ключ ответа: вариант для выбора или число с допуском."""

    kind: Literal["choice", "numeric"]
    correct: str | None = Field(default=None, description="Ключ верного варианта a–d")
    text: str | None = Field(default=None, description="Текст верного варианта")
    value: float | None = None
    tolerance: float | None = None


class ItemInstanceRead(BaseModel):
    """Экземпляр семейства так, как его увидит кандидат, плюс ключ и разбор."""

    seed: int = Field(description="По seed экземпляр воспроизводится точно")
    payload: InstancePayload
    answer: InstanceAnswer
    explanation: str
    params: dict[str, Any] = Field(description="Что генератор выбрал случайно для экземпляра")


class ItemSamplesRead(BaseModel):
    """Несколько экземпляров одного семейства — видно, чем они отличаются."""

    family: ItemFamilyRead
    instances: list[ItemInstanceRead]


class FamilyStatusUpdate(BaseModel):
    """Смена статуса семейства методистом."""

    status: Literal[
        ItemFamilyStatus.ACTIVE,
        ItemFamilyStatus.PILOT,
        ItemFamilyStatus.RETIRED,
        ItemFamilyStatus.COMPROMISED,
    ]
    reason: str = Field(min_length=3, max_length=500)


class MethodistVacancyRow(BaseModel):
    """Опубликованная вакансия в списке методиста."""

    id: uuid.UUID
    title: str
    company_name: str
    specialization: SpecializationBrief
    grades: list[GradeBrief]
    skills_count: int
    published_at: datetime | None


class VacancySkillCoverage(BaseModel):
    """Навык вакансии и то, чем платформа его подтверждает."""

    skill_id: int
    slug: str
    name: str
    importance: SkillImportance
    verified_by: list[str] = Field(description="Компетенции теста, подтверждающие навык")


class GradeFocusFamily(BaseModel):
    """Семейство, которое тест на этот грейд будет показывать чаще других."""

    family: ItemFamilyRead
    information: float = Field(description="Информация Фишера около порога грейда")
    sample: ItemInstanceRead | None


class GradeFocus(BaseModel):
    """Тест на грейд вакансии: порог и самые информативные около него семейства."""

    grade: GradeBrief
    category_code: str
    theta_cut: float
    families: list[GradeFocusFamily]


class VacancyTestCompetency(BaseModel):
    """Компетенция теста для стека вакансии."""

    code: str
    name: str
    weight: float
    included: bool
    expected_items: float = Field(description="Ожидаемое число заданий при средней длине теста")
    active_families: int
    covers_skills: list[str] = Field(description="Навыки вакансии, которые подтверждает")


class MicroTaskBrief(BaseModel):
    """Активная микрозадача компании по специализации вакансии."""

    id: uuid.UUID
    kind: MicroTaskKind
    title: str
    time_limit_minutes: int


class VacancyTestRead(BaseModel):
    """Как кандидат со стеком вакансии подтверждает категорию и навыки.

    Тест единый для категории (ответ организаторов VS.5), но состав зависит от стека:
    языково-зависимые компетенции включаются по навыкам. Навыки вакансии, которых
    тест не покрывает, проверяют микрозадачи работодателя.
    """

    vacancy: MethodistVacancyRow
    min_items: int
    max_items: int
    competencies: list[VacancyTestCompetency]
    grades: list[GradeFocus]
    skills: list[VacancySkillCoverage]
    coverage: float = Field(description="Доля обязательных навыков, подтверждаемых тестом")
    microtasks: list[MicroTaskBrief]
    items_visible: bool = Field(
        default=True,
        description="Семейства и экземпляры заданий видит только методист, не работодатель",
    )


class EngineSettingsRead(BaseModel):
    """Параметры адаптивного алгоритма."""

    min_items: int
    max_items: int
    confidence_z: float
    target_se: float
    randomesque: int
    max_exposure_rate: float
    pilot_items: int


class PolicySettingsRead(BaseModel):
    """Правила пересдачи и смены грейда."""

    grade_change_cooldown_days: int
    upgrade_retry_days: int
    onboarding_retry_hours: int
    confident_upgrade_window_hours: int


class ScaleCategory(BaseModel):
    """Категория на шкале специализации."""

    category_id: int
    code: str
    grade: GradeBrief
    theta_cut: float
    default_theta_cut: float


class SpecializationScale(BaseModel):
    """Пороги грейдов одной специализации."""

    specialization: SpecializationBrief
    categories: list[ScaleCategory]


class AssessmentSettingsRead(BaseModel):
    """Настройки оценки: алгоритм, правила и пороги категорий."""

    algorithm_version: str
    interim_estimator: str
    final_estimator: str
    full: EngineSettingsRead
    express: EngineSettingsRead
    express_enabled: bool
    policy: PolicySettingsRead
    scales: list[SpecializationScale]


class ThetaCutUpdate(BaseModel):
    """Новый порог категории на шкале θ."""

    theta_cut: float = Field(ge=MIN_THETA_CUT, le=MAX_THETA_CUT)
    reason: str = Field(min_length=3, max_length=500)
