import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import MethodistServiceDep, MethodistUser
from app.api.errors import error_responses
from app.schemas.methodist import (
    MAX_SAMPLES,
    AssessmentSettingsRead,
    FamilyStatusUpdate,
    ItemBankRead,
    ItemFamilyRead,
    ItemSamplesRead,
    MethodistVacancyRow,
    SpecializationScale,
    ThetaCutUpdate,
    VacancyTestRead,
)

router = APIRouter(prefix="/methodist", tags=["methodist"])

_errors = error_responses(401, 403, 404, 409, 422)


@router.get(
    "/item-bank",
    response_model=ItemBankRead,
    responses=_errors,
    summary="Банк заданий",
)
async def item_bank(
    user: MethodistUser,
    service: MethodistServiceDep,
    specialization_id: Annotated[int | None, Query()] = None,
) -> ItemBankRead:
    """Семейства заданий с параметрами модели, статусом и статистикой показов."""
    return await service.item_bank(specialization_id)


@router.get(
    "/item-bank/{family_id}/samples",
    response_model=ItemSamplesRead,
    responses=_errors,
    summary="Экземпляры семейства",
)
async def samples(
    family_id: int,
    user: MethodistUser,
    service: MethodistServiceDep,
    count: Annotated[int, Query(ge=1, le=MAX_SAMPLES)] = 3,
    seed: Annotated[list[int] | None, Query(description="Воспроизвести экземпляры")] = None,
) -> ItemSamplesRead:
    """Свежие экземпляры тем же генератором, что в тесте, — с ключом и разбором."""
    return await service.samples(family_id, count, seed or ())


@router.put(
    "/item-bank/{family_id}/status",
    response_model=ItemFamilyRead,
    responses=_errors,
    summary="Статус семейства",
)
async def family_status(
    family_id: int,
    payload: FamilyStatusUpdate,
    user: MethodistUser,
    service: MethodistServiceDep,
) -> ItemFamilyRead:
    """Включить в оценку, перевести в пилот или вывести из ротации; пишется в аудит."""
    return await service.set_family_status(user, family_id, payload)


@router.get(
    "/vacancies",
    response_model=list[MethodistVacancyRow],
    responses=_errors,
    summary="Опубликованные вакансии",
)
async def vacancies(user: MethodistUser, service: MethodistServiceDep) -> list[MethodistVacancyRow]:
    """Вакансии, для которых можно посмотреть тест."""
    return await service.vacancies()


@router.get(
    "/vacancies/{vacancy_id}/test",
    response_model=VacancyTestRead,
    responses=_errors,
    summary="Вакансия → тест",
)
async def vacancy_test(
    vacancy_id: uuid.UUID, user: MethodistUser, service: MethodistServiceDep
) -> VacancyTestRead:
    """Категория вакансии, состав теста под её стек, экземпляры и микрозадачи."""
    return await service.vacancy_test(vacancy_id)


@router.get(
    "/assessment-settings",
    response_model=AssessmentSettingsRead,
    responses=_errors,
    summary="Настройки оценки",
)
async def assessment_settings(
    user: MethodistUser, service: MethodistServiceDep
) -> AssessmentSettingsRead:
    """Параметры алгоритма, правила пересдачи и пороги категорий."""
    return await service.settings()


@router.put(
    "/categories/{category_id}/theta-cut",
    response_model=SpecializationScale,
    responses=_errors,
    summary="Порог категории",
)
async def theta_cut(
    category_id: int,
    payload: ThetaCutUpdate,
    user: MethodistUser,
    service: MethodistServiceDep,
) -> SpecializationScale:
    """Новый порог действует для тестов, завершённых после изменения."""
    return await service.update_theta_cut(user, category_id, payload)
