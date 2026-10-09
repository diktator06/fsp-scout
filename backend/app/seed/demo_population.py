import asyncio
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from random import Random
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import hash_password
from app.crud import (
    assessment_item_crud,
    consent_crud,
    grade_crud,
    industry_crud,
    item_family_crud,
    recruiter_crud,
    skill_lookup_crud,
    specialization_crud,
    user_crud,
)
from app.models.assessment import AssessmentMode, SessionOutcome, SessionStatus
from app.models.candidate import ContactChannel, SearchStatus, WorkFormat
from app.models.consent import ConsentType
from app.models.employer import CompanySize
from app.models.matching import SkillImportance
from app.models.user import User, UserRole
from app.schemas.assessment import SessionRead, SurveyCreate
from app.schemas.candidate import (
    CandidateProfileUpdate,
    CandidateSkillInput,
    EducationInput,
    PrivacySettingsUpdate,
    WorkExperienceInput,
)
from app.schemas.employer import CompanyUpdate
from app.schemas.matching import NeedCreate, NeedSkillInput
from app.seed.seeders import DATA_DIR
from app.services.assessment.assessment_service import AssessmentService
from app.services.candidate.profile_service import CandidateProfileService
from app.services.consents import PERSONAL_DATA_POLICY_VERSION
from app.services.employer.company_service import CompanyService
from app.services.matching.need_service import NeedService

logger = logging.getLogger(__name__)

POPULATION_SEED = 2026
DEMO_EMPLOYER_EMAIL = "employer@example.com"
UNIVERSITIES = ("КФУ", "ИТМО", "МФТИ", "НГУ", "УрФУ", "ВШЭ", "МГТУ им. Баумана", "ТГУ", "Иннополис")
TOP_BAND = 1.1
CONCURRENCY = 4
FEMALE_SHARE = 0.4

type SessionFactory = Callable[[], AsyncSession]


class SimulatedClock:
    """Часы, которые двигает генератор: у ответов правдоподобные отметки времени.

    Сервис оценки берёт время только из этих часов, поэтому синтетический кандидат
    «проходит» тест месяцы назад и отвечает со скоростью живого человека.
    """

    def __init__(self, start: datetime) -> None:
        """Ставит стрелки на момент начала теста."""
        self.now = start

    def __call__(self) -> datetime:
        """Текущее время по этим часам."""
        return self.now

    def advance(self, seconds: float) -> None:
        """Сдвигает часы вперёд."""
        self.now += timedelta(seconds=seconds)


@dataclass(frozen=True, slots=True)
class PopulationContext:
    """Справочные данные, нужные генератору."""

    data: dict[str, Any]
    specializations: dict[str, int]
    grades: dict[str, tuple[int, int, float]]
    skills: dict[str, int]
    names: dict[tuple[str, int], str]


def load_population_data() -> dict[str, Any]:
    """Читает описание популяции из YAML."""
    with (DATA_DIR / "demo_population.yaml").open(encoding="utf-8") as stream:
        data: dict[str, Any] = yaml.safe_load(stream)
    return data


def _weighted(rng: Random, pairs: list[tuple[str, float]]) -> str:
    """Случайный выбор с весами."""
    return rng.choices([value for value, _ in pairs], weights=[weight for _, weight in pairs])[0]


def assign_names(data: dict[str, Any], keys: list[tuple[str, int]]) -> dict[tuple[str, int], str]:
    """Разные ФИО для кандидатов популяции, независимо от порядка их создания.

    Кандидаты создаются параллельно, поэтому имя берётся не из генератора кандидата,
    а из заранее перемешанного пула сочетаний «имя — фамилия»: совпадения ФИО у двух
    синтетических людей путают при ручной проверке банка. Если пул исчерпан (стенд
    нагрузочного теста), имена начинают повторяться.
    """
    rng = Random(f"{POPULATION_SEED}:names")
    pools: dict[bool, list[str]] = {}
    for female in (False, True):
        firsts = data["first_names"]["female" if female else "male"]
        pools[female] = [
            f"{first} {pair[1] if female else pair[0]}"
            for first in firsts
            for pair in data["last_names"]
        ]
        rng.shuffle(pools[female])
    names = {}
    for position, key in enumerate(keys):
        female = rng.random() < FEMALE_SHARE
        pool = pools[female] or pools[not female]
        names[key] = pool.pop() if pool else _fallback_name(data, position)
    return names


def _fallback_name(data: dict[str, Any], position: int) -> str:
    """Имя сверх пула уникальных сочетаний — по кругу."""
    firsts = data["first_names"]["male"]
    pair = data["last_names"][position % len(data["last_names"])]
    return f"{firsts[position % len(firsts)]} {pair[0]}"


def _email(specialization: str, index: int) -> str:
    """Адрес синтетического кандидата в зарезервированном домене example.com."""
    return f"demo.{specialization.replace('_', '-')}.{index:02d}@example.com"


def true_theta(rng: Random, grade: str, grades: dict[str, tuple[int, int, float]]) -> float:
    """«Истинная» способность внутри полосы грейда на шкале θ."""
    _, rank, cut = grades[grade]
    higher = sorted(value[2] for value in grades.values() if value[1] == rank + 1)
    upper = higher[0] if higher else cut + TOP_BAND
    return rng.uniform(cut + 0.05, upper - 0.05)


def _profile_payload(
    rng: Random, context: PopulationContext, specialization: str, grade: str, index: int
) -> tuple[CandidateProfileUpdate, list[int]]:
    """Анкета синтетического кандидата и навыки основного стека для опроса."""
    data = context.data
    full_name = context.names[(specialization, index)]
    low_years, high_years = data["experience_years"][grade]
    years = round(rng.uniform(low_years, high_years) * 2) / 2
    stacks = data["stacks"][specialization]
    stack = rng.choices(stacks, weights=[item.get("weight", 1) for item in stacks])[0]
    optional = rng.sample(stack["optional"], k=rng.randint(1, min(4, len(stack["optional"]))))
    slugs = list(dict.fromkeys([*stack["core"], *optional]))
    unknown = [slug for slug in slugs if slug not in context.skills]
    if unknown:
        raise ValueError(f"demo_population.yaml: неизвестные навыки {unknown}")
    level_base = {"intern": 2, "junior": 3, "middle": 3, "senior": 4}[grade]
    skills = [
        CandidateSkillInput(
            skill_id=context.skills[slug], self_level=min(5, level_base + rng.randint(0, 1))
        )
        for slug in slugs
    ]
    domain = rng.choice(data["domains"])
    stack_names = ", ".join(slug.replace("-", " ").title() for slug in stack["core"][:4])
    about = rng.choice(data["about_templates"]).format(
        domain=domain["text"], words=domain["words"], stack=stack_names
    )
    jobs = {
        "intern": rng.randint(0, 1),
        "junior": 1,
        "middle": rng.randint(1, 2),
        "senior": rng.randint(2, 3),
    }[grade]
    experiences = []
    end = date.today() - timedelta(days=rng.randint(0, 60))
    for job in range(jobs):
        months = max(4, round(years * 12 / max(1, jobs)))
        start = end - timedelta(days=30 * months)
        job_domain = domain if job == 0 else rng.choice(data["domains"])
        experiences.append(
            WorkExperienceInput(
                company_name=rng.choice(data["companies"]),
                position=rng.choice(data["positions"][specialization]),
                started_on=start,
                ended_on=None if job == 0 else end,
                description=f"Разработка {job_domain['text']}: {job_domain['words']}.",
            )
        )
        end = start - timedelta(days=rng.randint(10, 90))
    educations = []
    if rng.random() < 0.75:
        educations.append(
            EducationInput(
                institution=rng.choice(UNIVERSITIES),
                degree=rng.choice(["Бакалавр", "Магистр", "Специалист"]),
                graduated_year=date.today().year - max(0, int(years)) - rng.randint(0, 2),
            )
        )
    low_salary, high_salary = data["salary_bands"][grade]
    premium = data["salary_premium"].get(specialization, 1.0)
    gross = rng.random() < 0.7
    salary = rng.uniform(low_salary, high_salary) * premium * 1000 * (1.0 if gross else 0.87)
    formats = [fmt for fmt in WorkFormat if rng.random() < 0.55] or [WorkFormat.REMOTE]
    roles = (
        ["developer"] if specialization not in {"qa", "data_analytics", "ml"} else ["researcher"]
    )
    if grade == "senior":
        roles.append(rng.choice(["mentor", "team_lead", "tech_lead", "architect"]))
    payload = CandidateProfileUpdate(
        full_name=full_name,
        phone=f"+7 900 000-{index // 100 % 100:02d}-{index % 100:02d}",
        telegram=f"scout_demo_{specialization[:4]}{index:03d}",
        city=_weighted(rng, [(name, weight) for name, weight in data["cities"]]),
        about=about,
        experience_years=years,
        team_roles=roles,
        soft_skills=rng.sample(
            ["Коммуникация", "Наставничество", "Самоорганизация", "Ответственность"], k=2
        ),
        work_formats=formats,
        relocation_ready=rng.random() < 0.25,
        salary_expectation_from=int(round(salary / 5000) * 5000),
        salary_expectation_gross=gross,
        search_status=_weighted(
            rng,
            [(SearchStatus.ACTIVE, 0.4), (SearchStatus.OPEN, 0.5), (SearchStatus.NOT_LOOKING, 0.1)],
        ),
        skills=skills,
        experiences=experiences,
        educations=educations,
    )
    return payload, [context.skills[slug] for slug in stack["core"]]


def _answer(answer_key: dict[str, Any], correct: bool, rng: Random) -> str:
    """Ответ на экземпляр: верный из ключа или заведомо неверный."""
    if answer_key["kind"] == "choice":
        if correct:
            return str(answer_key["correct"])
        return rng.choice([option for option in "abcd" if option != answer_key["correct"]])
    value = float(answer_key["value"])
    return str(value) if correct else str(round(value * 2 + 7))


async def take_test(
    session: AsyncSession,
    settings: Settings,
    user: User,
    rng: Random,
    theta: float,
    grade_id: int,
) -> SessionRead:
    """Проходит адаптивный тест настоящим сервисом оценки.

    Верность ответа разыгрывается по модели IRT с параметрами семейства из банка, время
    ответа — от четверти до трёх четвертей лимита задания.
    """
    clock = SimulatedClock(datetime.now(UTC) - timedelta(days=rng.uniform(5, 330)))
    assessment = AssessmentService(session, settings, clock=clock)
    mode = AssessmentMode.EXPRESS if rng.random() < 0.1 else AssessmentMode.FULL
    view = await assessment.start_session(user, grade_id, mode)
    while view.status is SessionStatus.IN_PROGRESS and view.current_item is not None:
        item = await assessment_item_crud.get(session, view.current_item.id)
        family = await item_family_crud.get(session, item.family_id) if item else None
        if item is None or family is None:
            break
        logistic = 1.0 / (1.0 + math.exp(-family.irt_a * (theta - family.irt_b)))
        probability = family.irt_c + (1.0 - family.irt_c) * logistic
        clock.advance(rng.uniform(0.25, 0.75) * family.time_limit_sec)
        view = await assessment.submit_answer(
            user, view.id, item.id, _answer(item.answer_key, rng.random() < probability, rng)
        )
    result = view.result
    if (
        result is not None
        and result.outcome is SessionOutcome.FAILED
        and result.can_accept_suggested
        and rng.random() < 0.7
    ):
        view = await assessment.accept_suggested_grade(user, view.id)
    return view


async def _create_candidate(
    session: AsyncSession,
    settings: Settings,
    context: PopulationContext,
    password_hash: str,
    specialization: str,
    index: int,
) -> bool:
    """Создаёт одного синтетического кандидата: аккаунт, анкета, опрос и, как правило, тест."""
    email = _email(specialization, index)
    if await user_crud.get_by_email(session, email):
        return False
    rng = Random(f"{POPULATION_SEED}:{specialization}:{index}")
    data = context.data
    grade = _weighted(rng, list(data["grade_shares"].items()))
    theta = true_theta(rng, grade, context.grades)
    user = await user_crud.create_local(
        session,
        email=email,
        password_hash=password_hash,
        role=UserRole.CANDIDATE,
        is_email_verified=True,
        verified_at=datetime.now(UTC),
    )
    await consent_crud.grant(
        session,
        user_id=user.id,
        consent_type=ConsentType.PERSONAL_DATA_PROCESSING,
        document_version=PERSONAL_DATA_POLICY_VERSION,
        ip_address=None,
    )
    await session.commit()

    profiles = CandidateProfileService(session)
    payload, core_skill_ids = _profile_payload(rng, context, specialization, grade, index)
    await profiles.update(user, payload)
    channels = [ContactChannel.EMAIL, ContactChannel.TELEGRAM]
    if rng.random() < 0.3:
        channels.append(ContactChannel.PHONE)
    await profiles.update_privacy(
        user,
        PrivacySettingsUpdate(
            show_salary_expectation=rng.random() < 0.8,
            show_city=rng.random() < 0.85,
            show_company_names=rng.random() < 0.45,
            show_fsp_achievements=True,
            revealed_channels=channels,
        ),
    )
    if rng.random() < 0.92:
        await profiles.set_bank_publication(user, True, None)

    grade_ids = {code: value[0] for code, value in context.grades.items()}
    ranks = {code: value[1] for code, value in context.grades.items()}
    by_rank = {rank: code for code, rank in ranks.items()}
    roll = rng.random()
    claimed = grade
    if roll < 0.2 and ranks[grade] + 1 in by_rank:
        claimed = by_rank[ranks[grade] + 1]
    elif roll < 0.3 and ranks[grade] - 1 in by_rank:
        claimed = by_rank[ranks[grade] - 1]
    assessment = AssessmentService(session, settings)
    await assessment.submit_survey(
        user,
        SurveyCreate(
            specialization_id=context.specializations[specialization],
            claimed_grade_id=grade_ids[claimed],
            primary_skill_ids=core_skill_ids[:12],
            experience_years=payload.experience_years or 0,
        ),
    )
    if rng.random() < 0.88:
        await take_test(session, settings, user, rng, theta, grade_ids[claimed])
    return True


async def _seed_demo_company(session: AsyncSession, context: PopulationContext) -> bool:
    """Компания демо-работодателя и две потребности, если их ещё нет."""
    employer = await user_crud.get_by_email(session, DEMO_EMPLOYER_EMAIL)
    if employer is None or await recruiter_crud.get_by_user_id(session, employer.id):
        return False
    data = context.data["demo_company"]
    industry = await industry_crud.get_by_code(session, data["industry"])
    await CompanyService(session).save_profile(
        employer,
        CompanyUpdate(
            name=data["name"],
            website=data["website"],
            industry_id=industry.id if industry else None,
            description=data["description"],
            size=CompanySize(data["size"]),
            city=data["city"],
            contact_email=data["contact_email"],
            contact_telegram=data["contact_telegram"],
            recruiter_full_name=data["recruiter"]["full_name"],
            recruiter_position=data["recruiter"]["position"],
        ),
    )
    needs = NeedService(session)
    grade_ids = {code: value[0] for code, value in context.grades.items()}
    for need in data["needs"]:
        await needs.create(
            employer,
            NeedCreate(
                title=need["title"],
                raw_text=need["raw_text"],
                team_description=need["team_description"],
                specialization_id=context.specializations[need["specialization"]],
                grade_ids=[grade_ids[code] for code in need["grades"]],
                skills=[
                    NeedSkillInput(skill_id=context.skills[slug], importance=SkillImportance(kind))
                    for kind in ("must", "nice")
                    for slug in need["skills"][kind]
                ],
                work_formats=[WorkFormat(item) for item in need["work_formats"]],
                city=need["city"],
                salary_from=need["salary"][0],
                salary_to=need["salary"][1],
                salary_gross=True,
            ),
        )
    return True


async def seed_demo_population(session_factory: SessionFactory, settings: Settings) -> str:
    """Наполняет стенд демо-компанией и синтетическими кандидатами.

    Повторный запуск ничего не дублирует: существующие аккаунты пропускаются. Кандидаты
    создаются параллельно, каждый в своей сессии: сервисы фиксируют изменения сами,
    а параллельность сокращает первый старт стенда в несколько раз.
    """
    data = load_population_data()
    async with session_factory() as session:
        specializations = {
            item.code: item.id for item in await specialization_crud.list_all(session)
        }
        grades = {
            grade.code: (grade.id, grade.rank, grade.default_theta_cut)
            for grade in await grade_crud.list_all(session)
        }
        all_slugs = {
            slug
            for stacks in data["stacks"].values()
            for stack in stacks
            for slug in (*stack["core"], *stack["optional"])
        }
        all_slugs |= {
            slug
            for need in data["demo_company"]["needs"]
            for kind in ("must", "nice")
            for slug in need["skills"][kind]
        }
        skills = await skill_lookup_crud.ids_by_slugs(session, all_slugs)
        shares = data.get("population_shares", {})
        keys = [
            (specialization, index)
            for specialization in data["stacks"]
            for index in range(
                1,
                max(
                    1,
                    round(
                        settings.demo_population_per_specialization
                        * shares.get(specialization, 1.0)
                    ),
                )
                + 1,
            )
        ]
        context = PopulationContext(
            data=data,
            specializations=specializations,
            grades=grades,
            skills=skills,
            names=assign_names(data, keys),
        )
        company = await _seed_demo_company(session, context)
    password_hash = hash_password(settings.demo_password)
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def create(specialization: str, index: int) -> bool:
        """Создаёт кандидата в отдельной сессии, не больше CONCURRENCY одновременно."""
        async with semaphore, session_factory() as candidate_session:
            return await _create_candidate(
                candidate_session, settings, context, password_hash, specialization, index
            )

    results = await asyncio.gather(
        *(create(specialization, index) for specialization, index in keys)
    )
    created = sum(results)
    return f"кандидатов +{created}, демо-компания {'создана' if company else 'уже есть'}"
