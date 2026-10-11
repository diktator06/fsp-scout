from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import (
    DictionaryServiceDep,
    MethodistUser,
    PaginationDep,
    SessionDep,
)
from app.api.errors import error_responses
from app.crud import category_crud, grade_crud, industry_crud, skill_crud, specialization_crud
from app.models.dictionary import SkillKind
from app.schemas.common import Page
from app.schemas.dictionary import (
    CategoryRead,
    GradeRead,
    IndustryRead,
    SkillCreate,
    SkillRead,
    SkillUpdate,
    SpecializationCreate,
    SpecializationRead,
    SpecializationUpdate,
)

router = APIRouter(prefix="/dictionaries", tags=["dictionaries"])

_methodist_errors = error_responses(401, 403, 404, 409, 422)


@router.get(
    "/specializations",
    response_model=list[SpecializationRead],
    responses=error_responses(),
    summary="Специализации",
)
async def list_specializations(session: SessionDep) -> list[SpecializationRead]:
    """Все специализации в порядке показа в интерфейсе."""
    items = await specialization_crud.list_all(session)
    return [SpecializationRead.model_validate(item) for item in items]


@router.get(
    "/grades",
    response_model=list[GradeRead],
    responses=error_responses(),
    summary="Грейды",
)
async def list_grades(session: SessionDep) -> list[GradeRead]:
    """Грейды по возрастанию уровня вместе с порогами по шкале способностей."""
    items = await grade_crud.list_all(session)
    return [GradeRead.model_validate(item) for item in items]


@router.get(
    "/categories",
    response_model=list[CategoryRead],
    responses=error_responses(422),
    summary="Категории кандидатов",
)
async def list_categories(
    session: SessionDep,
    specialization_id: Annotated[int | None, Query(description="Фильтр по специализации")] = None,
    grade_id: Annotated[int | None, Query(description="Фильтр по грейду")] = None,
) -> list[CategoryRead]:
    """Категории (специализация × грейд), по которым распределяются кандидаты."""
    items = await category_crud.list_filtered(
        session, specialization_id=specialization_id, grade_id=grade_id
    )
    return [CategoryRead.model_validate(item) for item in items]


@router.get(
    "/industries",
    response_model=list[IndustryRead],
    responses=error_responses(),
    summary="Отрасли",
)
async def list_industries(session: SessionDep) -> list[IndustryRead]:
    """Отрасли для опроса кандидата и профиля компании."""
    items = await industry_crud.list_all(session)
    return [IndustryRead.model_validate(item) for item in items]


@router.get(
    "/skills",
    response_model=Page[SkillRead],
    responses=error_responses(422),
    summary="Поиск навыков",
)
async def search_skills(
    session: SessionDep,
    pagination: PaginationDep,
    query: Annotated[
        str | None,
        Query(max_length=64, description="Подстрока названия, slug или алиаса, например «питон»"),
    ] = None,
    kind: Annotated[SkillKind | None, Query(description="Тип навыка")] = None,
    specialization_id: Annotated[
        int | None, Query(description="Только навыки, типичные для специализации")
    ] = None,
) -> Page[SkillRead]:
    """Поиск по справочнику навыков: используется в опросе, профиле и описании потребности."""
    items, total = await skill_crud.search(
        session,
        query=query,
        kind=kind,
        specialization_id=specialization_id,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return Page[SkillRead](
        items=[SkillRead.model_validate(item) for item in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "/specializations",
    status_code=status.HTTP_201_CREATED,
    response_model=SpecializationRead,
    responses=_methodist_errors,
    summary="Создать специализацию (методист)",
)
async def create_specialization(
    payload: SpecializationCreate, _: MethodistUser, service: DictionaryServiceDep
) -> SpecializationRead:
    """Создаёт специализацию и категории для всех грейдов."""
    specialization = await service.create_specialization(payload)
    return SpecializationRead.model_validate(specialization)


@router.patch(
    "/specializations/{specialization_id}",
    response_model=SpecializationRead,
    responses=_methodist_errors,
    summary="Изменить специализацию (методист)",
)
async def update_specialization(
    specialization_id: int,
    payload: SpecializationUpdate,
    _: MethodistUser,
    service: DictionaryServiceDep,
) -> SpecializationRead:
    """Меняет название, описание или порядок показа специализации."""
    specialization = await service.update_specialization(specialization_id, payload)
    return SpecializationRead.model_validate(specialization)


@router.delete(
    "/specializations/{specialization_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_methodist_errors,
    summary="Удалить специализацию (методист)",
)
async def delete_specialization(
    specialization_id: int, _: MethodistUser, service: DictionaryServiceDep
) -> Response:
    """Удаляет специализацию с её категориями, если они ещё нигде не используются."""
    await service.delete_specialization(specialization_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/skills",
    status_code=status.HTTP_201_CREATED,
    response_model=SkillRead,
    responses=_methodist_errors,
    summary="Добавить навык (методист)",
)
async def create_skill(
    payload: SkillCreate, _: MethodistUser, service: DictionaryServiceDep
) -> SkillRead:
    """Добавляет навык в справочник."""
    skill = await service.create_skill(payload)
    return SkillRead.model_validate(skill)


@router.patch(
    "/skills/{skill_id}",
    response_model=SkillRead,
    responses=_methodist_errors,
    summary="Изменить навык (методист)",
)
async def update_skill(
    skill_id: int, payload: SkillUpdate, _: MethodistUser, service: DictionaryServiceDep
) -> SkillRead:
    """Меняет название, тип или алиасы навыка."""
    skill = await service.update_skill(skill_id, payload)
    return SkillRead.model_validate(skill)


@router.delete(
    "/skills/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_methodist_errors,
    summary="Удалить навык (методист)",
)
async def delete_skill(skill_id: int, _: MethodistUser, service: DictionaryServiceDep) -> Response:
    """Удаляет навык из справочника."""
    await service.delete_skill(skill_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
