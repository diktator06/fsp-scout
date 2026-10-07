from enum import StrEnum

from app.core.exceptions import ApplicationStateError
from app.models.vacancy import ApplicationStatus


class ApplicationActor(StrEnum):
    """Кто меняет статус отклика."""

    CANDIDATE = "candidate"
    EMPLOYER = "employer"


_TRANSITIONS: dict[tuple[ApplicationStatus, ApplicationStatus], ApplicationActor] = {
    (ApplicationStatus.SUBMITTED, ApplicationStatus.VIEWED): ApplicationActor.EMPLOYER,
    (ApplicationStatus.SUBMITTED, ApplicationStatus.INTERVIEW): ApplicationActor.EMPLOYER,
    (ApplicationStatus.SUBMITTED, ApplicationStatus.REJECTED): ApplicationActor.EMPLOYER,
    (ApplicationStatus.VIEWED, ApplicationStatus.INTERVIEW): ApplicationActor.EMPLOYER,
    (ApplicationStatus.VIEWED, ApplicationStatus.REJECTED): ApplicationActor.EMPLOYER,
    (ApplicationStatus.SUBMITTED, ApplicationStatus.WITHDRAWN): ApplicationActor.CANDIDATE,
    (ApplicationStatus.VIEWED, ApplicationStatus.WITHDRAWN): ApplicationActor.CANDIDATE,
}

_FINAL_MESSAGES = {
    ApplicationStatus.INTERVIEW: "Компания уже пригласила на собеседование",
    ApplicationStatus.REJECTED: "Компания уже ответила отказом",
    ApplicationStatus.WITHDRAWN: "Кандидат отозвал отклик",
}


def ensure_transition(
    current: ApplicationStatus, target: ApplicationStatus, actor: ApplicationActor
) -> None:
    """Проверяет переход отклика.

    Работодатель отвечает на новый или просмотренный отклик, кандидат может отозвать
    его, пока ответа нет. Решение работодателя окончательное: передумать можно
    только новым откликом на другую вакансию или приглашением.
    """
    if _TRANSITIONS.get((current, target)) is actor:
        return
    raise ApplicationStateError(
        _FINAL_MESSAGES.get(current, "Действие с откликом сейчас недоступно"),
        details={"status": current.value, "target": target.value},
    )
