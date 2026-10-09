import uuid
from collections.abc import Mapping, Sequence
from random import SystemRandom

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.crud import (
    assessment_session_crud,
    category_crud,
    grade_crud,
    item_family_crud,
    microtask_crud,
    specialization_competency_crud,
    specialization_crud,
    vacancy_crud,
    vacancy_skill_crud,
)
from app.crud.vacancy import company_lookup_crud
from app.models.assessment import ItemFamily, ItemFamilyStatus
from app.models.dictionary import Grade
from app.models.matching import SkillImportance
from app.models.user import User
from app.models.vacancy import Vacancy
from app.schemas.dictionary import GradeBrief, SpecializationBrief
from app.schemas.methodist import (
    CompetencyBrief,
    GradeFocus,
    GradeFocusFamily,
    InstanceAnswer,
    InstancePayload,
    ItemFamilyRead,
    ItemInstanceRead,
    MethodistVacancyRow,
    MicroTaskBrief,
    VacancySkillCoverage,
    VacancyTestCompetency,
    VacancyTestRead,
)
from app.services.assessment.assessment_service import AssessmentService
from app.services.assessment.irt import ItemParameters, information
from app.services.assessment.item_generators import REGISTRY, FamilySpec, generate_instance
from app.services.employer.company_service import CompanyService

FOCUS_FAMILIES = 3
SEED_BITS = 53


def instance(spec: FamilySpec, seed: int) -> ItemInstanceRead:
    """Экземпляр семейства по seed — тот же путь, что у сессии теста."""
    generated = generate_instance(spec, seed)
    return ItemInstanceRead(
        seed=seed,
        payload=InstancePayload.model_validate(generated.client_payload()),
        answer=InstanceAnswer.model_validate(generated.answer),
        explanation=generated.explanation,
        params=generated.params,
    )


def family_read(family: ItemFamily, sessions: Mapping[str, int] | None) -> ItemFamilyRead:
    """Семейство в ответе.

    Доля показов — от сессий, в тест которых входила компетенция семейства; без
    этих данных (одиночное семейство вне контекста специализации) её нет.
    """
    total = sessions.get(family.competency.code, 0) if sessions is not None else 0
    return ItemFamilyRead(
        id=family.id,
        code=family.code,
        title=family.title,
        competency=CompetencyBrief(code=family.competency.code, name=family.competency.name),
        nominal_grade=GradeBrief.model_validate(family.nominal_grade),
        response_format=family.response_format,
        irt_a=family.irt_a,
        irt_b=family.irt_b,
        irt_c=family.irt_c,
        time_limit_sec=family.time_limit_sec,
        status=family.status,
        origin=family.origin,
        exposure_count=family.exposure_count,
        exposure_rate=round(min(1.0, family.exposure_count / total), 3) if total else None,
        responses_count=family.responses_count,
        correct_rate=round(family.correct_count / family.responses_count, 3)
        if family.responses_count
        else None,
        calibrated_at=family.calibrated_at,
        version=family.version,
        has_generator=family.code in REGISTRY,
    )


class VacancyTestService:
    """Как кандидат со стеком вакансии подтверждает категорию и навыки.

    Общий расчёт для кабинета методиста (с семействами и экземплярами заданий) и
    для работодателя (состав теста, покрытие навыков и микрозадачи — без заданий).
    """

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        """Получает сессию БД и настройки оценки."""
        self._session = session
        self._assessment = AssessmentService(session, settings)
        self._random = SystemRandom()

    async def for_methodist(self, vacancy_id: uuid.UUID) -> VacancyTestRead:
        """Опубликованная вакансия любой компании — с заданиями у порога грейда."""
        vacancy = await vacancy_crud.get_published(self._session, vacancy_id)
        if vacancy is None:
            raise NotFoundError("Вакансия не найдена или не опубликована")
        return await self.build(vacancy, with_items=True)

    async def for_employer(self, user: User, vacancy_id: uuid.UUID) -> VacancyTestRead:
        """Своя вакансия в любом статусе — без семейств и экземпляров заданий."""
        recruiter = await CompanyService(self._session).require_recruiter(user)
        vacancy = await vacancy_crud.get_for_company(
            self._session, vacancy_id, recruiter.company_id
        )
        if vacancy is None:
            raise NotFoundError("Вакансия не найдена")
        return await self.build(vacancy, with_items=False)

    async def build(self, vacancy: Vacancy, *, with_items: bool) -> VacancyTestRead:
        """Вакансия → категория → состав теста → задания у порога и микрозадачи.

        Состав считается тем же методом, что показывает кандидату опрос: стек
        вакансии подставляется вместо стека кандидата. Семейства и экземпляры
        заданий (`with_items`) видит только методист: работодатель — участник рынка,
        и знание шаблонов дало бы его кандидатам преимущество на тесте.
        """
        row = (await self.rows([vacancy]))[0]
        skills = (await vacancy_skill_crud.list_with_skills(self._session, [vacancy.id])).get(
            vacancy.id, []
        )
        blueprint = await self._assessment.preview_blueprint(
            vacancy.specialization_id, [skill.id for _, skill in skills]
        )
        links = await specialization_competency_crud.list_for_specialization(
            self._session, vacancy.specialization_id
        )
        by_code = {competency.code: competency for _, competency in links}
        included = {item.code for item in blueprint.competencies if item.included}
        coverage_rows = [
            VacancySkillCoverage(
                skill_id=skill.id,
                slug=skill.slug,
                name=skill.name,
                importance=link.importance,
                verified_by=[
                    by_code[code].name
                    for code in sorted(included)
                    if skill.slug in by_code[code].verifies_skill_slugs
                ],
            )
            for link, skill in skills
        ]
        must = [row for row in coverage_rows if row.importance is SkillImportance.MUST]
        families = [
            family
            for family in await item_family_crud.list_bank(
                self._session, [by_code[code].id for code in included]
            )
            if family.status is ItemFamilyStatus.ACTIVE and family.code in REGISTRY
        ]
        sessions = await assessment_session_crud.count_by_competency(self._session, included)
        average_length = (blueprint.min_items + blueprint.max_items) / 2
        tasks = await microtask_crud.active_for_company(
            self._session, vacancy.company_id, vacancy.specialization_id
        )
        return VacancyTestRead(
            vacancy=row,
            min_items=blueprint.min_items,
            max_items=blueprint.max_items,
            competencies=[
                VacancyTestCompetency(
                    code=item.code,
                    name=item.name,
                    weight=item.weight,
                    included=item.included,
                    expected_items=round(item.weight * average_length, 1),
                    active_families=item.bank_size,
                    covers_skills=[
                        row.name
                        for row in coverage_rows
                        if item.included and row.slug in by_code[item.code].verifies_skill_slugs
                    ],
                )
                for item in blueprint.competencies
            ],
            grades=await self._grade_focus(vacancy, families, sessions, with_items=with_items),
            items_visible=with_items,
            skills=coverage_rows,
            coverage=round(sum(1 for row in must if row.verified_by) / len(must), 3)
            if must
            else 0.0,
            microtasks=[
                MicroTaskBrief(
                    id=task.id,
                    kind=task.kind,
                    title=task.title,
                    time_limit_minutes=task.time_limit_minutes,
                )
                for task in tasks
            ],
        )

    async def _grade_focus(
        self,
        vacancy: Vacancy,
        families: Sequence[ItemFamily],
        sessions: Mapping[str, int],
        *,
        with_items: bool,
    ) -> list[GradeFocus]:
        """Для каждого грейда вакансии — семейства, информативные около его порога.

        Алгоритм выбирает задания с максимумом информации около порога заявленного
        грейда, поэтому тест на Senior состоит из других заданий, чем тест на Junior.
        """
        categories = await category_crud.list_filtered(
            self._session, specialization_id=vacancy.specialization_id
        )
        result = []
        for category in categories:
            if category.grade_id not in vacancy.grade_ids:
                continue
            ranked = sorted(
                families,
                key=lambda family: information(
                    category.theta_cut,
                    ItemParameters(a=family.irt_a, b=family.irt_b, c=family.irt_c),
                ),
                reverse=True,
            )[: FOCUS_FAMILIES if with_items else 0]
            result.append(
                GradeFocus(
                    grade=GradeBrief.model_validate(category.grade),
                    category_code=category.code,
                    theta_cut=category.theta_cut,
                    families=[
                        GradeFocusFamily(
                            family=family_read(family, sessions),
                            information=round(
                                information(
                                    category.theta_cut,
                                    ItemParameters(a=family.irt_a, b=family.irt_b, c=family.irt_c),
                                ),
                                3,
                            ),
                            sample=instance(
                                REGISTRY[family.code], self._random.getrandbits(SEED_BITS)
                            ),
                        )
                        for family in ranked
                    ],
                )
            )
        return result

    async def rows(self, vacancies: Sequence[Vacancy]) -> list[MethodistVacancyRow]:
        """Строки вакансий с компанией, специализацией и грейдами."""
        companies = await company_lookup_crud.with_industry(
            self._session, [vacancy.company_id for vacancy in vacancies]
        )
        skills = await vacancy_skill_crud.list_with_skills(
            self._session, [vacancy.id for vacancy in vacancies]
        )
        specializations = {
            item.id: item
            for item in await specialization_crud.get_many(
                self._session, [vacancy.specialization_id for vacancy in vacancies]
            )
        }
        grades: dict[int, Grade] = {
            grade.id: grade for grade in await grade_crud.list_all(self._session)
        }
        return [
            MethodistVacancyRow(
                id=vacancy.id,
                title=vacancy.title,
                company_name=companies[vacancy.company_id].name,
                specialization=SpecializationBrief.model_validate(
                    specializations[vacancy.specialization_id]
                ),
                grades=sorted(
                    (
                        GradeBrief.model_validate(grades[grade_id])
                        for grade_id in vacancy.grade_ids
                        if grade_id in grades
                    ),
                    key=lambda grade: grade.rank,
                ),
                skills_count=len(skills.get(vacancy.id, [])),
                published_at=vacancy.published_at,
            )
            for vacancy in vacancies
        ]
