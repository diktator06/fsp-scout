import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from random import Random
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import hash_password
from app.crud import (
    consent_crud,
    fsp_achievement_crud,
    fsp_link_crud,
    grade_crud,
    skill_lookup_crud,
    specialization_crud,
    user_crud,
)
from app.models.candidate import ContactChannel, SearchStatus, WorkFormat
from app.models.consent import ConsentType
from app.models.fsp import FspEventLevel, FspParticipationFormat, FspResultStatus
from app.models.user import UserRole
from app.schemas.assessment import SurveyCreate
from app.schemas.candidate import (
    CandidateProfileUpdate,
    CandidateSkillInput,
    PrivacySettingsUpdate,
    WorkExperienceInput,
)
from app.seed.demo_population import TOP_BAND, load_population_data, take_test, true_theta
from app.services.assessment.assessment_service import AssessmentService
from app.services.candidate.profile_service import CandidateProfileService
from app.services.consents import PERSONAL_DATA_POLICY_VERSION
from evaluation.relevance import CandidateTruth, to_gross

EVALUATION_SEED = 2027
CONCURRENCY = 4
PUBLISHED_SHARE = 0.95
NOT_LOOKING_SHARE = 0.06
TESTED_SHARE = 0.9
FSP_SHARE = 0.35
OMISSION_RATE = 0.08
INFLATION_SHARE = 0.35
OVERCLAIM_SHARE = 0.25
UNDERCLAIM_SHARE = 0.1
DISCIPLINES = (
    "алгоритмическое программирование",
    "продуктовое программирование",
    "программирование систем информационной безопасности",
)

type SessionFactory = Callable[[], AsyncSession]


@dataclass(frozen=True, slots=True)
class Directory:
    """Справочники, нужные генератору: коды, идентификаторы и полосы грейдов."""

    data: dict[str, Any]
    specializations: dict[str, int]
    grades: dict[str, tuple[int, int, float]]
    skills: dict[str, int]


async def load_directory(session: AsyncSession) -> Directory:
    """Читает справочники через CRUD и описание популяции из YAML."""
    data = load_population_data()
    specializations = {item.code: item.id for item in await specialization_crud.list_all(session)}
    grades = {
        grade.code: (grade.id, grade.rank, grade.default_theta_cut)
        for grade in await grade_crud.list_all(session)
    }
    slugs = {
        slug
        for stacks in data["stacks"].values()
        for stack in stacks
        for slug in (*stack["core"], *stack["optional"])
    }
    skills = await skill_lookup_crud.ids_by_slugs(session, slugs)
    return Directory(data=data, specializations=specializations, grades=grades, skills=skills)


def band_position(theta: float, grade: str, grades: dict[str, tuple[int, int, float]]) -> float:
    """Положение истинной способности внутри полосы грейда: 0 — у порога, 1 — у следующего."""
    _, rank, cut = grades[grade]
    higher = sorted(value[2] for value in grades.values() if value[1] == rank + 1)
    upper = higher[0] if higher else cut + TOP_BAND
    return max(0.0, min(1.0, (theta - cut) / (upper - cut)))


def _weighted(rng: Random, pairs: list[tuple[Any, float]]) -> Any:
    """Случайный выбор с весами."""
    return rng.choices([value for value, _ in pairs], weights=[weight for _, weight in pairs])[0]


def _declared_skills(rng: Random, true_skills: list[str], vocabulary: list[str]) -> list[str]:
    """Навыки, которые кандидат пишет о себе, — с шумом, как в живых резюме.

    Часть настоящих навыков не упоминается (скромность, забывчивость), а примерно
    треть кандидатов дописывает модные навыки, которыми не владеет. Именно этот шум
    обманывает поиск по ключевым словам; тест его не видит, потому что проверяет
    ответы, а не список.
    """
    declared = [slug for slug in true_skills if rng.random() >= OMISSION_RATE]
    if rng.random() < INFLATION_SHARE:
        extra = [slug for slug in vocabulary if slug not in true_skills]
        declared += rng.sample(extra, k=min(len(extra), rng.randint(2, 4)))
    return list(dict.fromkeys(declared or true_skills[:1]))


def _claimed_grade(rng: Random, rank: int, ranks: dict[int, str]) -> str:
    """Заявленный грейд: каждый четвёртый завышает, каждый десятый занижает."""
    roll = rng.random()
    if roll < OVERCLAIM_SHARE and rank + 1 in ranks:
        return ranks[rank + 1]
    if roll < OVERCLAIM_SHARE + UNDERCLAIM_SHARE and rank - 1 in ranks:
        return ranks[rank - 1]
    return ranks[rank]


def _fsp_rows(rng: Random, theta: float, index: int) -> list[dict[str, Any]]:
    """История ФСП, коррелирующая со способностью: сильные чаще участвуют и побеждают."""
    events = max(1, min(8, round(rng.expovariate(1.0) * 2 + max(0.0, theta + 1.0))))
    rows = []
    for event in range(events):
        strength = theta + rng.gauss(0.0, 0.8)
        if strength > 1.4:
            status, place = FspResultStatus.WINNER, 1
        elif strength > 0.8:
            status, place = FspResultStatus.PRIZE, rng.randint(2, 3)
        elif strength > 0.2:
            status, place = FspResultStatus.FINALIST, rng.randint(4, 20)
        else:
            status, place = FspResultStatus.PARTICIPANT, None
        team = rng.random() < 0.5
        rows.append(
            {
                "external_event_id": f"EVAL-{index}-{event}",
                "event_name": f"Кубок по программированию, этап {event + 1}",
                "event_level": rng.choice(list(FspEventLevel)),
                "discipline": rng.choice(DISCIPLINES),
                "event_date": date.today() - timedelta(days=rng.randint(30, 900)),
                "participation_format": (
                    FspParticipationFormat.TEAM if team else FspParticipationFormat.INDIVIDUAL
                ),
                "team_name": "Сборная" if team else None,
                "team_role": "участник" if team else None,
                "place": place,
                "participants_total": rng.randint(30, 300) if place else None,
                "result_status": status,
                "is_online": rng.random() < 0.4,
                "rating_points": None,
                "protocol_url": None,
            }
        )
    return rows


async def _create_candidate(
    session: AsyncSession,
    settings: Settings,
    directory: Directory,
    password_hash: str,
    specialization: str,
    index: int,
    seed: int,
) -> CandidateTruth:
    """Один кандидат с записанной «истиной»: аккаунт, анкета с шумом, опрос и тест."""
    rng = Random(f"{seed}:{specialization}:{index}")
    data = directory.data
    grade = _weighted(rng, list(data["grade_shares"].items()))
    _, rank, _ = directory.grades[grade]
    theta = true_theta(rng, grade, directory.grades)
    stacks = data["stacks"][specialization]
    stack = rng.choices(stacks, weights=[item.get("weight", 1) for item in stacks])[0]
    optional = rng.sample(stack["optional"], k=rng.randint(1, min(4, len(stack["optional"]))))
    true_skills = list(dict.fromkeys([*stack["core"], *optional]))
    vocabulary = sorted({slug for item in stacks for slug in (*item["core"], *item["optional"])})
    declared = _declared_skills(rng, true_skills, vocabulary)

    user = await user_crud.create_local(
        session,
        email=f"eval.{specialization.replace('_', '-')}.{index:03d}@example.com",
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

    low_years, high_years = data["experience_years"][grade]
    years = round(rng.uniform(low_years, high_years) * 2) / 2
    low_salary, high_salary = data["salary_bands"][grade]
    gross = rng.random() < 0.7
    salary_gross = (
        rng.uniform(low_salary, high_salary)
        * data["salary_premium"].get(specialization, 1.0)
        * 1000
    )
    stated = salary_gross if gross else salary_gross * 0.87
    formats = [fmt for fmt in WorkFormat if rng.random() < 0.55] or [WorkFormat.REMOTE]
    city = _weighted(rng, [(name, weight) for name, weight in data["cities"]])
    relocation = rng.random() < 0.25
    domain = rng.choice(data["domains"])
    stack_names = ", ".join(slug.replace("-", " ").title() for slug in declared[:6])
    about = rng.choice(data["about_templates"]).format(
        domain=domain["text"], words=domain["words"], stack=stack_names
    )
    started = date.today() - timedelta(days=round(max(0.5, years) * 365))
    profiles = CandidateProfileService(session)
    await profiles.update(
        user,
        CandidateProfileUpdate(
            full_name=f"Кандидат {specialization} {index}",
            city=city,
            about=about,
            experience_years=years,
            work_formats=formats,
            relocation_ready=relocation,
            salary_expectation_from=int(round(stated / 5000) * 5000),
            salary_expectation_gross=gross,
            search_status=(
                SearchStatus.NOT_LOOKING
                if rng.random() < NOT_LOOKING_SHARE
                else _weighted(rng, [(SearchStatus.ACTIVE, 0.45), (SearchStatus.OPEN, 0.55)])
            ),
            skills=[
                CandidateSkillInput(skill_id=directory.skills[slug], self_level=rng.randint(3, 5))
                for slug in declared
            ],
            experiences=[
                WorkExperienceInput(
                    company_name=rng.choice(data["companies"]),
                    position=rng.choice(data["positions"][specialization]),
                    started_on=started,
                    ended_on=None,
                    description=f"Разработка {domain['text']}: {domain['words']}.",
                )
            ],
        ),
    )
    await profiles.update_privacy(
        user,
        PrivacySettingsUpdate(
            show_salary_expectation=rng.random() < 0.8,
            show_city=rng.random() < 0.85,
            show_company_names=True,
            show_fsp_achievements=True,
            revealed_channels=[ContactChannel.EMAIL],
        ),
    )
    if rng.random() < PUBLISHED_SHARE:
        await profiles.set_bank_publication(user, True, None)

    ranks = {value[1]: code for code, value in directory.grades.items()}
    claimed = _claimed_grade(rng, rank, ranks)
    assessment = AssessmentService(session, settings)
    await assessment.submit_survey(
        user,
        SurveyCreate(
            specialization_id=directory.specializations[specialization],
            claimed_grade_id=directory.grades[claimed][0],
            primary_skill_ids=[directory.skills[slug] for slug in declared[:12]],
            experience_years=years,
        ),
    )
    if rng.random() < TESTED_SHARE:
        await take_test(session, settings, user, rng, theta, directory.grades[claimed][0])
    profile = await profiles.ensure_profile(user)
    if rng.random() < FSP_SHARE:
        now = datetime.now(UTC)
        await fsp_link_crud.create(
            session,
            {
                "candidate_id": profile.id,
                "participant_id": f"eval-{seed}-{specialization}-{index}",
                "synced_at": now,
            },
        )
        await fsp_achievement_crud.replace_for_candidate(
            session, profile.id, _fsp_rows(rng, theta, index), now
        )
        await session.commit()
    return CandidateTruth(
        candidate_id=profile.id,
        specialization=specialization,
        grade_rank=rank,
        skills=frozenset(true_skills),
        salary_gross=to_gross(stated, gross),
        work_formats=frozenset(item.value for item in formats),
        city=city,
        relocation_ready=relocation,
        band_position=band_position(theta, grade, directory.grades),
    )


async def generate_population(
    session_factory: SessionFactory,
    settings: Settings,
    per_specialization: int,
    seed: int = EVALUATION_SEED,
) -> list[CandidateTruth]:
    """Создаёт популяцию через настоящие сервисы и возвращает «истину» о каждом кандидате.

    Кандидаты создаются параллельно, каждый в своей сессии, как в демо-сиде.
    """
    async with session_factory() as session:
        directory = await load_directory(session)
    password_hash = hash_password(settings.demo_password)
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def build(specialization: str, index: int) -> CandidateTruth:
        """Один кандидат в собственной сессии."""
        async with semaphore, session_factory() as session:
            return await _create_candidate(
                session, settings, directory, password_hash, specialization, index, seed
            )

    tasks = [
        build(specialization, index)
        for specialization in directory.data["stacks"]
        for index in range(1, per_specialization + 1)
    ]
    return list(await asyncio.gather(*tasks))


def describe(truths: list[CandidateTruth], seeds: list[int]) -> dict[str, Any]:
    """Сводка популяции для отчёта."""
    by_specialization: dict[str, int] = {}
    for truth in truths:
        by_specialization[truth.specialization] = by_specialization.get(truth.specialization, 0) + 1
    return {
        "candidates": len(truths),
        "by_specialization": by_specialization,
        "seeds": seeds,
        "noise": {
            "omitted_true_skill_rate": OMISSION_RATE,
            "inflated_skill_list_share": INFLATION_SHARE,
            "overclaimed_grade_share": OVERCLAIM_SHARE,
            "underclaimed_grade_share": UNDERCLAIM_SHARE,
            "tested_share": TESTED_SHARE,
            "fsp_linked_share": FSP_SHARE,
            "published_share": PUBLISHED_SHARE,
            "not_looking_share": NOT_LOOKING_SHARE,
        },
    }
