from enum import StrEnum

from app.core.exceptions import InvitationStateError
from app.models.invitation import InvitationStatus


class Actor(StrEnum):
    """Кто меняет статус приглашения."""

    CANDIDATE = "candidate"
    EMPLOYER = "employer"
    SYSTEM = "system"


_TRANSITIONS: dict[tuple[InvitationStatus, InvitationStatus], Actor] = {
    (InvitationStatus.SENT, InvitationStatus.VIEWED): Actor.CANDIDATE,
    (InvitationStatus.VIEWED, InvitationStatus.ACCEPTED): Actor.CANDIDATE,
    (InvitationStatus.VIEWED, InvitationStatus.DECLINED): Actor.CANDIDATE,
    (InvitationStatus.SENT, InvitationStatus.WITHDRAWN): Actor.EMPLOYER,
    (InvitationStatus.VIEWED, InvitationStatus.WITHDRAWN): Actor.EMPLOYER,
    (InvitationStatus.SENT, InvitationStatus.EXPIRED): Actor.SYSTEM,
    (InvitationStatus.VIEWED, InvitationStatus.EXPIRED): Actor.SYSTEM,
}

_FINAL_MESSAGES = {
    InvitationStatus.ACCEPTED: "Приглашение уже принято",
    InvitationStatus.DECLINED: "Приглашение уже отклонено",
    InvitationStatus.WITHDRAWN: "Компания отозвала приглашение",
    InvitationStatus.EXPIRED: "Срок ответа на приглашение истёк",
}


def can_transition(current: InvitationStatus, target: InvitationStatus, actor: Actor) -> bool:
    """Разрешён ли переход и именно этому участнику."""
    return _TRANSITIONS.get((current, target)) is actor


def ensure_transition(current: InvitationStatus, target: InvitationStatus, actor: Actor) -> None:
    """Проверяет переход по автомату (docs/MATCHING.md, раздел 8).

    Принять или отклонить можно только просмотренное приглашение, отозвать —
    только активное. Сообщение объясняет, почему действие уже невозможно.
    """
    if can_transition(current, target, actor):
        return
    raise InvitationStateError(
        _FINAL_MESSAGES.get(current, "Действие с приглашением сейчас недоступно"),
        details={"status": current.value, "target": target.value},
    )


def is_active(status: InvitationStatus) -> bool:
    """Ждёт ли приглашение ответа кандидата."""
    return status in (InvitationStatus.SENT, InvitationStatus.VIEWED)
