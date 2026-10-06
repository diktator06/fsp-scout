from fastapi import APIRouter

from app.api.v1 import assessment, auth, dictionaries, system
from app.api.v1.candidates import profile

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(dictionaries.router)
api_router.include_router(profile.router)
api_router.include_router(assessment.router)
