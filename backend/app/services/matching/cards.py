import re
from collections.abc import Sequence

from app.crud.candidate_search import CompetencyOutcome
from app.schemas.cards import (
    CandidateAnonymousCard,
    CardCompetency,
    CardExperience,
    CardSkill,
    CardTest,
    FspSummary,
    ScoreComponentRead,
    VerifiedScoreRead,
)
from app.schemas.dictionary import CategoryRead
from app.services.matching.candidate_pool import PoolMember
from app.services.matching.verified_score import VerifiedScore

_MASK = "[скрыто]"
_PII_PATTERNS = (
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"(?:https?://|www\.|t\.me/)\S+", re.IGNORECASE),
    re.compile(r"(?<![\w@])@[A-Za-z0-9_]{4,}"),
    re.compile(r"(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s-]*\d{2}[\s-]*\d{2}"),
    re.compile(r"\b\d[\d\s\-()]{9,}\d\b"),
)

FSP_NOT_LINKED = "Профиль ФСП не привязан — оценка основана на тесте и профиле"


def mask_pii(text: str) -> str:
    """Скрывает контакты, которые кандидат мог оставить в свободном тексте.

    Обезличенная карточка теряет смысл, если в «о себе» написано «звоните +7 999…».
    Поэтому email, телефоны, ники и ссылки заменяются меткой до раскрытия контактов.
    """
    masked = text
    for pattern in _PII_PATTERNS:
        masked = pattern.sub(_MASK, masked)
    return masked


def verified_score_read(score: VerifiedScore) -> VerifiedScoreRead:
    """Индекс подтверждённого профиля для ответа API: вклад каждого фактора в баллах."""
    return VerifiedScoreRead(
        total=score.total,
        components=[
            ScoreComponentRead(
                key=component.key,
                label=component.label,
                value=component.value,
                weight=component.weight,
                contribution=round(100 * component.value * component.weight, 1),
            )
            for component in score.components
        ],
        test_percentile=round(score.test_percentile * 100)
        if score.test_percentile is not None
        else None,
    )


def build_card(
    member: PoolMember, outcomes: Sequence[CompetencyOutcome] | None = None
) -> CandidateAnonymousCard:
    """Обезличенная карточка: подтверждённые данные и только разрешённые кандидатом поля."""
    profile = member.row.profile
    privacy = member.privacy
    facts = member.facts
    show_companies = bool(privacy and privacy.show_company_names)
    skills = sorted(
        (
            CardSkill(
                id=skill.id,
                name=skill.name,
                kind=skill.kind,
                verified=candidate_skill.is_verified,
                self_level=candidate_skill.self_level,
            )
            for candidate_skill, skill in member.skills
        ),
        key=lambda item: (not item.verified, item.name.lower()),
    )
    test = None
    if facts.confirmed and member.session is not None and member.session.finished_at:
        test = CardTest(
            finished_at=member.session.finished_at,
            mode=member.session.mode,
            items=member.session.items_scored,
            percentile=round(member.score.test_percentile * 100)
            if member.score.test_percentile is not None
            else None,
            competencies=[
                CardCompetency(
                    code=item.code, name=item.name, answered=item.answered, correct=item.correct
                )
                for item in outcomes or []
            ],
        )
    return CandidateAnonymousCard(
        candidate_id=profile.id,
        alias=profile.public_alias,
        category=CategoryRead.model_validate(member.category),
        grade_status="confirmed" if facts.confirmed else "unconfirmed",
        verified_score=verified_score_read(member.score),
        skills=skills,
        experience_years=profile.experience_years,
        work_formats=list(profile.work_formats),
        relocation_ready=profile.relocation_ready,
        city=profile.city if facts.city_visible else None,
        salary_expectation=profile.salary_expectation_from if facts.salary_visible else None,
        salary_gross=profile.salary_expectation_gross,
        search_status=profile.search_status,
        about=mask_pii(profile.about),
        experiences=[
            CardExperience(
                position=job.position,
                company_name=job.company_name if show_companies else None,
                started_on=job.started_on,
                ended_on=job.ended_on,
                description=mask_pii(job.description),
            )
            for job in member.experiences
        ],
        test=test,
        fsp=FspSummary(linked=False, message=FSP_NOT_LINKED),
        updated_at=profile.updated_at,
    )
