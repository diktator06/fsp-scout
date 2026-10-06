from typing import Annotated

from fastapi import APIRouter, Body, Response

from app.api.deps import CandidateUser, ClientContextDep, ProfileServiceDep
from app.api.errors import error_responses
from app.schemas.candidate import (
    CandidateProfileRead,
    CandidateProfileUpdate,
    CandidateStatusRead,
    ConsentsRead,
    PrivacySettingsRead,
    PrivacySettingsUpdate,
)
from app.services.candidate.profile_pdf import render_profile_pdf

router = APIRouter(prefix="/candidates/me", tags=["candidate"])

_errors = error_responses(401, 403, 422)


@router.get(
    "/profile", response_model=CandidateProfileRead, responses=_errors, summary="Мой профиль"
)
async def read_profile(user: CandidateUser, service: ProfileServiceDep) -> CandidateProfileRead:
    """Профиль кандидата. При первом обращении создаётся пустой профиль с псевдонимом."""
    return await service.get_view(user)


@router.put(
    "/profile", response_model=CandidateProfileRead, responses=_errors, summary="Сохранить профиль"
)
async def update_profile(
    payload: CandidateProfileUpdate, user: CandidateUser, service: ProfileServiceDep
) -> CandidateProfileRead:
    """Сохраняет анкету целиком: поля, навыки, опыт работы и образование.

    Категория и подтверждённые тестом навыки анкетой не меняются.
    """
    return await service.update(user, payload)


@router.get(
    "/profile.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "PDF-профиль"}, **_errors},
    summary="Скачать стандартизированный PDF-профиль",
)
async def download_profile_pdf(user: CandidateUser, service: ProfileServiceDep) -> Response:
    """Профиль в едином формате платформы с отметками подтверждённых навыков."""
    profile = await service.get_view(user)
    content = await render_profile_pdf(profile)
    filename = f"scout-profile-{profile.public_alias}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/status", response_model=CandidateStatusRead, responses=_errors, summary="Статус онбординга"
)
async def read_status(user: CandidateUser, service: ProfileServiceDep) -> CandidateStatusRead:
    """Текущий шаг пути: профиль → опрос → выбор грейда → тест → категория."""
    return await service.status(user)


@router.get(
    "/privacy",
    response_model=PrivacySettingsRead,
    responses=_errors,
    summary="Настройки приватности",
)
async def read_privacy(user: CandidateUser, service: ProfileServiceDep) -> PrivacySettingsRead:
    """Что видит работодатель до раскрытия контактов."""
    return await service.get_privacy(user)


@router.put(
    "/privacy",
    response_model=PrivacySettingsRead,
    responses=_errors,
    summary="Изменить приватность",
)
async def update_privacy(
    payload: PrivacySettingsUpdate, user: CandidateUser, service: ProfileServiceDep
) -> PrivacySettingsRead:
    """Меняет видимость полей и каналы связи, которые раскрываются после согласия."""
    return await service.update_privacy(user, payload)


@router.get("/consents", response_model=ConsentsRead, responses=_errors, summary="Мои согласия")
async def read_consents(user: CandidateUser, service: ProfileServiceDep) -> ConsentsRead:
    """Действующие согласия на обработку ПДн и публикацию профиля в банке."""
    return await service.get_consents(user)


@router.put(
    "/consents/bank-publication",
    response_model=ConsentsRead,
    responses=_errors,
    summary="Согласие на публикацию в банке кандидатов",
)
async def set_bank_publication(
    granted: Annotated[
        bool, Body(embed=True, description="true — дать согласие, false — отозвать")
    ],
    user: CandidateUser,
    service: ProfileServiceDep,
    client: ClientContextDep,
) -> ConsentsRead:
    """Даёт или отзывает согласие. Без него профиль не виден работодателям в банке."""
    return await service.set_bank_publication(user, granted, client.ip_address)
