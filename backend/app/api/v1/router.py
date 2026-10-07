from fastapi import APIRouter

from app.api.v1 import (
    assessment,
    auth,
    complaints,
    dictionaries,
    moderation,
    notifications,
    system,
)
from app.api.v1.candidates import fsp as candidate_fsp
from app.api.v1.candidates import invitations as candidate_invitations
from app.api.v1.candidates import profile
from app.api.v1.candidates import tasks as candidate_tasks
from app.api.v1.candidates import vacancies as candidate_vacancies
from app.api.v1.employer import candidates, company, needs
from app.api.v1.employer import invitations as employer_invitations
from app.api.v1.employer import tasks as employer_tasks
from app.api.v1.employer import vacancies as employer_vacancies

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(dictionaries.router)
api_router.include_router(profile.router)
api_router.include_router(assessment.router)
api_router.include_router(candidate_invitations.router)
api_router.include_router(candidate_fsp.router)
api_router.include_router(company.router)
api_router.include_router(needs.router)
api_router.include_router(candidates.router)
api_router.include_router(employer_invitations.router)
api_router.include_router(employer_vacancies.router)
api_router.include_router(candidate_vacancies.router)
api_router.include_router(employer_tasks.router)
api_router.include_router(candidate_tasks.router)
api_router.include_router(complaints.router)
api_router.include_router(moderation.router)
api_router.include_router(notifications.router)
