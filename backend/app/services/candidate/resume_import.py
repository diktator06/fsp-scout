from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import specialization_crud
from app.models.candidate import WorkFormat
from app.models.user import User
from app.schemas.candidate import (
    ResumeDraftRead,
    ResumeEducationDraft,
    ResumeExperienceDraft,
    ResumeSkillDraft,
)
from app.schemas.dictionary import GradeBrief, SkillRead, SpecializationBrief
from app.services.candidate.profile_service import CandidateProfileService
from app.services.candidate.resume_parser import parse_resume_text
from app.services.candidate.resume_text import extract_pdf_text
from app.services.matching.engine import MatchingEngine

GRADE_WARNING = (
    "Грейд из резюме — только подсказка для выбора уровня теста: категорию присваивает тест"
)


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


class ResumeImportService:
    """Автораспознавание резюме из PDF: черновик полей профиля для проверки кандидатом.

    Разбор не сохраняет ни файл, ни текст и ничего не меняет в профиле: кандидат
    видит, что и откуда найдено, и сам переносит нужное в анкету.
    """

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = _now) -> None:
        """Получает сессию БД и источник времени (от него считается «по настоящее время»)."""
        self._session = session
        self._clock = clock
        self._profiles = CandidateProfileService(session)
        self._engine = MatchingEngine(session)

    async def parse(self, user: User, data: bytes) -> ResumeDraftRead:
        """Разбирает PDF и возвращает черновик полей профиля."""
        await self._profiles.ensure_profile(user)
        text = extract_pdf_text(data)
        catalog = await self._engine.catalog()
        parsed = parse_resume_text(text, catalog.skills, self._clock().date())
        skills_by_id = {skill.id: skill for skill in catalog.skills}
        grades = {grade.code: grade for grade in catalog.grades}
        specialization = (
            await specialization_crud.get_by_code(self._session, parsed.specialization_code)
            if parsed.specialization_code
            else None
        )
        warnings = []
        if parsed.grade_code:
            warnings.append(GRADE_WARNING)
        if not parsed.experiences:
            warnings.append("Места работы с датами не найдены — добавьте их в анкете вручную")
        return ResumeDraftRead(
            full_name=parsed.full_name,
            email=parsed.email,
            phone=parsed.phone,
            telegram=parsed.telegram,
            city=parsed.city,
            experience_years=parsed.experience_years,
            grade=GradeBrief.model_validate(grades[parsed.grade_code])
            if parsed.grade_code in grades
            else None,
            specialization=SpecializationBrief.model_validate(specialization)
            if specialization
            else None,
            skills=[
                ResumeSkillDraft(
                    skill=SkillRead(
                        id=item.skill_id,
                        slug=skills_by_id[item.skill_id].slug,
                        name=skills_by_id[item.skill_id].name,
                        kind=skills_by_id[item.skill_id].kind,
                        aliases=list(skills_by_id[item.skill_id].aliases),
                    ),
                    evidence=item.evidence,
                )
                for item in parsed.skills
            ],
            soft_skills=parsed.soft_skills,
            team_roles=parsed.team_roles,
            experiences=[
                ResumeExperienceDraft(
                    position=item.position,
                    company_name=item.company_name,
                    started_on=item.started_on,
                    ended_on=item.ended_on,
                    description=item.description,
                )
                for item in parsed.experiences
            ],
            about=parsed.about,
            educations=[
                ResumeEducationDraft(
                    institution=item.institution,
                    degree=item.degree,
                    graduated_year=item.graduated_year,
                )
                for item in parsed.educations
            ],
            work_formats=[WorkFormat(code) for code in parsed.work_formats],
            relocation_ready=parsed.relocation_ready,
            evidence=parsed.evidence,
            warnings=warnings,
        )
