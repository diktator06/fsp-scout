import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import reputation_crud
from app.crud.trust import ReputationCounts
from app.models.employer import Company
from app.schemas.trust import CompanyReputationRead


@dataclass(frozen=True, slots=True)
class Reputation:
    """Репутация компании глазами кандидата — факты вместо непрозрачного рейтинга."""

    response_rate: float | None
    acceptance_rate: float | None
    complaints_confirmed: int
    on_platform_since: datetime
    summary: str


MIN_FOR_RATE = 3


def _rate(part: int, total: int) -> float | None:
    """Доля, если данных достаточно; на двух-трёх событиях процент вводит в заблуждение."""
    return round(part / total, 2) if total >= MIN_FOR_RATE else None


def build_reputation(counts: ReputationCounts, since: datetime) -> Reputation:
    """Репутация из счётчиков: отвечает ли компания на отклики и принимают ли её приглашения.

    Кандидат видит не балл, а понятные факты: «Отвечает на отклики: 86 %», «Приглашения
    принимают: 40 %», «Подтверждённых жалоб нет». Подтверждённые модератором жалобы
    видны всегда — это главный сигнал против недобросовестного работодателя.
    """
    response = _rate(counts.applications_answered, counts.applications_received)
    acceptance = _rate(counts.invitations_accepted, counts.invitations_answered)
    parts = []
    if response is not None:
        parts.append(f"отвечает на отклики: {round(response * 100)} %")
    if acceptance is not None:
        parts.append(f"приглашения принимают: {round(acceptance * 100)} %")
    parts.append(
        f"подтверждённых жалоб: {counts.complaints_confirmed}"
        if counts.complaints_confirmed
        else "подтверждённых жалоб нет"
    )
    summary = "; ".join(parts)
    return Reputation(
        response_rate=response,
        acceptance_rate=acceptance,
        complaints_confirmed=counts.complaints_confirmed,
        on_platform_since=since,
        summary=summary[0].upper() + summary[1:],
    )


async def company_reputations(
    session: AsyncSession, companies: Sequence[Company]
) -> dict[uuid.UUID, CompanyReputationRead]:
    """Репутация пачки компаний для ответа API — одним набором запросов."""
    counts = await reputation_crud.counts(session, [company.id for company in companies])
    result = {}
    for company in companies:
        reputation = build_reputation(
            counts.get(company.id, ReputationCounts()), company.created_at
        )
        result[company.id] = CompanyReputationRead(
            response_rate=reputation.response_rate,
            acceptance_rate=reputation.acceptance_rate,
            complaints_confirmed=reputation.complaints_confirmed,
            on_platform_since=reputation.on_platform_since,
            summary=reputation.summary,
        )
    return result
