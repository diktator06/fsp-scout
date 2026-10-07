from app.models.employer import TrustLevel

DAILY_INVITATION_LIMITS: dict[TrustLevel, int] = {
    TrustLevel.NEW: 20,
    TrustLevel.BASIC: 50,
    TrustLevel.VERIFIED: 100,
}


def daily_limit(trust_level: TrustLevel) -> int:
    """Сколько приглашений компания может отправить за сутки.

    Квота растёт с доверием к компании. Новая компания не может разослать сотни
    одинаковых приглашений: это главный признак недобросовестного работодателя.
    """
    return DAILY_INVITATION_LIMITS[trust_level]
