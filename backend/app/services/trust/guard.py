from app.core.exceptions import CompanyRestrictedError
from app.models.employer import Company


def ensure_company_active(company: Company) -> None:
    """Ограниченная компания не может приглашать, публиковать вакансии и выдавать задачи.

    Ограничение ставится автоматически после жалоб разных кандидатов или модератором
    и снимается только модератором (docs/TRUST_AND_ATS.md).
    """
    if company.restricted_at is not None:
        raise CompanyRestrictedError(details={"reason": company.restriction_reason})
