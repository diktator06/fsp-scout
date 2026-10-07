from collections.abc import Mapping, Sequence
from typing import Any

from app.models.dictionary import Grade, Skill, Specialization
from app.models.vacancy import ApplicationEvent, Vacancy, VacancySkill
from app.schemas.dictionary import GradeBrief, SkillRead, SpecializationBrief
from app.schemas.matching import NeedSkillRead
from app.schemas.vacancy import ApplicationActor, ApplicationEventRead

CANDIDATE_PHRASES = {
    "Ожидания укладываются в вашу вилку": "Ваши ожидания укладываются в вилку вакансии",
    "Ожидания немного выше верхней границы вилки": "Ваши ожидания немного выше вилки вакансии",
    "Ожидания выше вилки больше чем на 30 %": "Ваши ожидания выше вилки больше чем на 30 %",
    "Предпочитает другой формат работы": "Формат работы отличается от удобного вам",
    "Живёт в другом городе, готов к переезду": "Офис в другом городе — вы готовы к переезду",
    "Живёт в другом городе и не готов к переезду": "Офис в другом городе, а переезд вы не отметили",
    "Опыт перекликается с задачами": "Ваш опыт перекликается с задачами",
    "Нет в профиле": "Не хватает в профиле",
    "Зарплатные ожидания не указаны или скрыты": (
        "Ваши ожидания не указаны или скрыты — сравнить с вилкой нельзя"
    ),
    "Формат работы не указан": "Вы не указали удобный формат работы",
    "Город не указан или скрыт": "Ваш город не указан или скрыт",
}


def for_candidate(text: str) -> str:
    """Переформулирует причину из «Почему в подборке» от лица кандидата.

    Объяснение строится теми же правилами, что и для работодателя, меняется только
    адресат: «в вашу вилку» превращается в «в вилку вакансии».
    """
    for source, target in CANDIDATE_PHRASES.items():
        if text.startswith(source):
            return target + text[len(source) :]
    return text


def vacancy_fields(
    vacancy: Vacancy,
    skills: Sequence[tuple[VacancySkill, Skill]],
    specializations: Mapping[int, Specialization],
    grades: Mapping[int, Grade],
) -> dict[str, Any]:
    """Поля вакансии, общие для ответов работодателю и кандидату."""
    return {
        "id": vacancy.id,
        "title": vacancy.title,
        "description": vacancy.description,
        "specialization": SpecializationBrief.model_validate(
            specializations[vacancy.specialization_id]
        ),
        "grades": [
            GradeBrief.model_validate(grades[grade_id])
            for grade_id in sorted(vacancy.grade_ids, key=lambda gid: grades[gid].rank)
            if grade_id in grades
        ],
        "skills": [
            NeedSkillRead(skill=SkillRead.model_validate(skill), importance=item.importance)
            for item, skill in skills
        ],
        "work_formats": vacancy.work_formats,
        "city": vacancy.city,
        "salary_from": vacancy.salary_from,
        "salary_to": vacancy.salary_to,
        "salary_gross": vacancy.salary_gross,
        "published_at": vacancy.published_at,
    }


def application_events(
    events: Sequence[ApplicationEvent], candidate_user_id: object
) -> list[ApplicationEventRead]:
    """Таймлайн отклика: кто и когда менял статус."""
    actor: ApplicationActor
    result = []
    for event in events:
        actor = "candidate" if event.actor_user_id == candidate_user_id else "employer"
        result.append(
            ApplicationEventRead(status=event.to_status, at=event.created_at, actor=actor)
        )
    return result
