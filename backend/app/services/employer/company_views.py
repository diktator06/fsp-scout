from app.models.employer import Company, Recruiter
from app.schemas.invitation import CompanyBrief, EmployerContacts
from app.schemas.trust import CompanyReputationRead


def company_brief(
    company: Company, reputation: CompanyReputationRead | None = None
) -> CompanyBrief:
    """Компания глазами кандидата: видна сразу, ещё до ответа на приглашение или отклика.

    Отрасль должна быть подгружена заранее: в асинхронной сессии ленивая загрузка запрещена.
    Репутация и отметка «на проверке» помогают кандидату отличить добросовестного
    работодателя.
    """
    return CompanyBrief(
        id=company.id,
        name=company.name,
        industry=company.industry.name if company.industry else None,
        city=company.city,
        website=company.website,
        size=company.size,
        description=company.description,
        trust_level=company.trust_level,
        under_review=company.restricted_at is not None,
        reputation=reputation,
    )


def employer_contacts(company: Company, recruiter: Recruiter | None) -> EmployerContacts:
    """Контакты работодателя: кандидат видит их, когда стороны договорились о разговоре."""
    return EmployerContacts(
        recruiter_name=recruiter.full_name if recruiter else None,
        recruiter_position=recruiter.position if recruiter else None,
        email=company.contact_email,
        phone=company.contact_phone,
        telegram=company.contact_telegram,
    )
