from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.crud import (
    assessment_item_crud,
    grade_crud,
    item_family_crud,
    skill_lookup_crud,
    specialization_crud,
)
from app.models.assessment import SessionStatus
from app.models.candidate import ContactChannel, SearchStatus, WorkFormat
from app.models.user import User, UserRole
from app.schemas.assessment import SurveyCreate
from app.schemas.candidate import (
    CandidateProfileUpdate,
    CandidateSkillInput,
    PrivacySettingsUpdate,
    WorkExperienceInput,
)
from app.services.assessment.assessment_service import AssessmentService
from app.services.candidate.profile_service import CandidateProfileService
from tests.helpers import create_user


@dataclass(frozen=True, slots=True)
class BankCandidate:
    """Созданный для теста кандидат и его ожидаемые контакты."""

    user: User
    profile_id: str
    full_name: str
    phone: str
    telegram: str


async def make_bank_candidate(
    session: AsyncSession,
    *,
    specialization: str = "backend",
    grade: str = "middle",
    skills: Sequence[str] = ("python", "fastapi", "postgresql", "sql"),
    take_test: bool = True,
    strong: bool = True,
    published: bool = True,
    search_status: SearchStatus = SearchStatus.ACTIVE,
    salary: int | None = 250_000,
    show_salary: bool = True,
    city: str = "Москва",
    work_formats: Sequence[WorkFormat] = (WorkFormat.REMOTE,),
    revealed: Sequence[ContactChannel] = (ContactChannel.EMAIL, ContactChannel.TELEGRAM),
    about: str = "Пишу бэкенд платёжных сервисов: эквайринг, биллинг, микросервисы.",
    full_name: str = "Иван Петров",
    phone: str = "+7 900 000-11-22",
    telegram: str = "ivan_bank_test",
) -> BankCandidate:
    """Кандидат банка, собранный настоящими сервисами: анкета, приватность, опрос, тест.

    Тест проходится детерминированно: «сильный» кандидат отвечает верно на всё,
    «слабый» — ни на что. Так категория и подтверждённые навыки получаются теми же
    правилами, что у живых людей.
    """
    settings = get_settings()
    user = await create_user(session, UserRole.CANDIDATE)
    profiles = CandidateProfileService(session)
    skill_ids = await skill_lookup_crud.ids_by_slugs(session, skills)
    await profiles.update(
        user,
        CandidateProfileUpdate(
            full_name=full_name,
            phone=phone,
            telegram=telegram,
            city=city,
            about=about,
            experience_years=3,
            work_formats=list(work_formats),
            salary_expectation_from=salary,
            search_status=search_status,
            skills=[CandidateSkillInput(skill_id=skill_ids[slug], self_level=4) for slug in skills],
            experiences=[
                WorkExperienceInput(
                    company_name="Секретная Компания",
                    position="Backend-разработчик",
                    started_on="2022-01-01",
                    description="Платёжный шлюз и биллинг",
                )
            ],
        ),
    )
    await profiles.update_privacy(
        user,
        PrivacySettingsUpdate(
            show_salary_expectation=show_salary,
            show_city=True,
            show_company_names=False,
            show_fsp_achievements=True,
            revealed_channels=list(revealed),
        ),
    )
    if published:
        await profiles.set_bank_publication(user, True, None)
    specialization_row = await specialization_crud.get_by_code(session, specialization)
    grade_row = await grade_crud.get_by_code(session, grade)
    assert specialization_row is not None and grade_row is not None
    assessment = AssessmentService(session, settings)
    await assessment.submit_survey(
        user,
        SurveyCreate(
            specialization_id=specialization_row.id,
            claimed_grade_id=grade_row.id,
            primary_skill_ids=list(skill_ids.values()),
            experience_years=3,
        ),
    )
    if take_test:
        view = await assessment.start_session(user, grade_row.id)
        while view.status is SessionStatus.IN_PROGRESS and view.current_item is not None:
            item = await assessment_item_crud.get(session, view.current_item.id)
            assert item is not None
            family = await item_family_crud.get(session, item.family_id)
            assert family is not None
            key = item.answer_key
            if key["kind"] == "choice":
                answer = (
                    key["correct"] if strong else next(o for o in "abcd" if o != key["correct"])
                )
            else:
                answer = str(key["value"]) if strong else "987654321"
            view = await assessment.submit_answer(user, view.id, item.id, answer)
    profile = await profiles.ensure_profile(user)
    return BankCandidate(
        user=user,
        profile_id=str(profile.id),
        full_name=full_name,
        phone=phone,
        telegram=f"@{telegram}",
    )
