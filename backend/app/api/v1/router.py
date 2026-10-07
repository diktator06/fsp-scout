from fastapi import APIRouter

from app.api.v1 import assessment, auth, dictionaries, notifications, system
from app.api.v1.candidates import invitations as candidate_invitations
from app.api.v1.candidates import profile
from app.api.v1.employer import candidates, company, needs
from app.api.v1.employer import invitations as employer_invitations

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(dictionaries.router)
api_router.include_router(profile.router)
api_router.include_router(assessment.router)
api_router.include_router(candidate_invitations.router)
api_router.include_router(company.router)
api_router.include_router(needs.router)
api_router.include_router(candidates.router)
api_router.include_router(employer_invitations.router)
api_router.include_router(notifications.router)
