import logging

from app.core.config import Settings
from app.crud import (
    candidate_profile_crud,
    grade_crud,
    hiring_need_crud,
    need_skill_crud,
    recruiter_crud,
    skill_lookup_crud,
    specialization_crud,
    user_crud,
    vacancy_crud,
)
from app.models.candidate import WorkFormat
from app.models.matching import SkillImportance
from app.models.vacancy import ApplicationStatus, RejectReason
from app.schemas.matching import NeedSkillInput
from app.schemas.vacancy import ApplicationCreate, ApplicationDecision, VacancyCreate
from app.seed.demo_population import DEMO_EMPLOYER_EMAIL, SessionFactory, load_population_data
from app.services.vacancies.board_service import VacancyBoardService
from app.services.vacancies.vacancy_service import VacancyService

logger = logging.getLogger(__name__)

COVER_LETTERS = (
    "Пишу бэкенд и аналитику для платёжных сервисов — готов обсудить задачи команды.",
    "Интересна ваша предметная область, есть похожий опыт. Расскажу подробнее на созвоне.",
    "Подхожу по стеку, хочу расти в продуктовой команде.",
)


async def seed_demo_vacancies(session_factory: SessionFactory, settings: Settings) -> str:
    """Публикует вакансии демо-компании и откликается на них синтетическими кандидатами.

    Вакансии собираются из потребностей компании и списка в сиде, отклики проходят
    через настоящие сервисы: раскрытие контактов, уведомления и журнал статусов
    получаются такими же, как у живых людей. Повторный запуск ничего не меняет.
    """
    data = load_population_data()["demo_company"]
    async with session_factory() as session:
        employer = await user_crud.get_by_email(session, DEMO_EMPLOYER_EMAIL)
        recruiter = await recruiter_crud.get_by_user_id(session, employer.id) if employer else None
        if employer is None or recruiter is None:
            return "демо-компании нет — вакансии пропущены"
        if await vacancy_crud.list_for_company(session, recruiter.company_id):
            return "вакансии демо-компании уже есть"
        specializations = {
            item.code: item.id for item in await specialization_crud.list_all(session)
        }
        grades = {grade.code: grade.id for grade in await grade_crud.list_all(session)}
        service = VacancyService(session)
        vacancy_ids = []
        for need in await hiring_need_crud.list_for_company(session, recruiter.company_id):
            skills = await need_skill_crud.list_with_skills(session, [need.id])
            vacancy = await service.create(
                employer,
                VacancyCreate(
                    title=need.title,
                    description=f"{need.team_description}\n\n{need.raw_text}".strip(),
                    specialization_id=need.specialization_id,
                    grade_ids=need.grade_ids,
                    skills=[
                        NeedSkillInput(skill_id=item.skill_id, importance=item.importance)
                        for item, _ in skills
                    ],
                    work_formats=[WorkFormat(item) for item in need.work_formats],
                    city=need.city,
                    salary_from=need.salary_from,
                    salary_to=need.salary_to,
                    salary_gross=need.salary_gross,
                    need_id=need.id,
                ),
                publish=True,
            )
            vacancy_ids.append(vacancy.id)
        for item in data.get("vacancies", []):
            slugs = [*item["skills"]["must"], *item["skills"]["nice"]]
            skill_ids = await skill_lookup_crud.ids_by_slugs(session, slugs)
            vacancy = await service.create(
                employer,
                VacancyCreate(
                    title=item["title"],
                    description=item["description"],
                    specialization_id=specializations[item["specialization"]],
                    grade_ids=[grades[code] for code in item["grades"]],
                    skills=[
                        NeedSkillInput(skill_id=skill_ids[slug], importance=SkillImportance(kind))
                        for kind in ("must", "nice")
                        for slug in item["skills"][kind]
                        if slug in skill_ids
                    ],
                    work_formats=[WorkFormat(value) for value in item["work_formats"]],
                    city=item["city"],
                    salary_from=item["salary"][0],
                    salary_to=item["salary"][1],
                ),
                publish=True,
            )
            vacancy_ids.append(vacancy.id)

        board = VacancyBoardService(session, settings)
        applied = 0
        for plan in data.get("applications", []):
            vacancy_id = vacancy_ids[plan["vacancy"]]
            candidates = await candidate_profile_crud.list_with_theta_by_email_prefix(
                session, f"demo.{plan['specialization'].replace('_', '-')}."
            )
            tested = [item for item in candidates if item[2] is not None]
            tested.sort(key=lambda item: item[2] or 0.0, reverse=True)
            for index, ((_, user, _), status) in enumerate(
                zip(tested[: plan["count"]], plan["statuses"], strict=False)
            ):
                application = await board.apply(
                    user,
                    vacancy_id,
                    ApplicationCreate(
                        cover_letter=COVER_LETTERS[index % len(COVER_LETTERS)],
                        share_contacts=True,
                    ),
                )
                applied += 1
                target = ApplicationStatus(status)
                if target is ApplicationStatus.VIEWED:
                    await service.open_application(employer, application.id)
                elif target in (ApplicationStatus.INTERVIEW, ApplicationStatus.REJECTED):
                    await service.decide(
                        employer,
                        application.id,
                        ApplicationDecision(
                            status=target,
                            reject_reason=RejectReason.SALARY
                            if target is ApplicationStatus.REJECTED
                            else None,
                            message="Напишите в Telegram, договоримся о времени"
                            if target is ApplicationStatus.INTERVIEW
                            else "Ожидания выше нашей вилки, вернёмся при пересмотре бюджета",
                        ),
                    )
    return f"вакансий +{len(vacancy_ids)}, откликов +{applied}"
