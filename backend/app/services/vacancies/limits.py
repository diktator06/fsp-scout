from app.models.employer import TrustLevel

PUBLISHED_VACANCY_LIMITS = {
    TrustLevel.NEW: 5,
    TrustLevel.BASIC: 20,
    TrustLevel.VERIFIED: 100,
}


def published_vacancy_limit(trust_level: TrustLevel) -> int:
    """Сколько вакансий компания может держать опубликованными одновременно.

    Новая компания не может завалить ленту десятками однотипных вакансий: это один из
    признаков фиктивного работодателя (docs/TRUST_AND_ATS.md).
    """
    return PUBLISHED_VACANCY_LIMITS[trust_level]
