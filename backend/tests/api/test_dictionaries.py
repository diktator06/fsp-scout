from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from app.models.user import User, UserRole
from tests.helpers import auth_headers

BASE_URL = "/api/v1/dictionaries"

UserFactory = Callable[..., Awaitable[User]]


async def test_reference_lists_are_seeded_and_ordered(client: AsyncClient) -> None:
    """Справочники наполнены из сида и отдаются в порядке показа."""
    specializations = (await client.get(f"{BASE_URL}/specializations")).json()
    grades = (await client.get(f"{BASE_URL}/grades")).json()
    industries = (await client.get(f"{BASE_URL}/industries")).json()

    assert [item["code"] for item in specializations][:3] == ["backend", "frontend", "mobile"]
    assert len(specializations) == 7
    assert [item["code"] for item in grades] == ["intern", "junior", "middle", "senior"]
    assert [item["default_theta_cut"] for item in grades] == sorted(
        item["default_theta_cut"] for item in grades
    )
    assert len(industries) >= 10


async def test_every_specialization_has_category_for_every_grade(client: AsyncClient) -> None:
    """Категория есть для каждой пары «специализация × грейд»."""
    categories = (await client.get(f"{BASE_URL}/categories")).json()
    assert len(categories) == 7 * 4
    backend_middle = next(item for item in categories if item["code"] == "backend-middle")
    assert backend_middle["title"] == "Backend-разработка · Middle"
    assert backend_middle["specialization"]["code"] == "backend"
    assert backend_middle["grade"]["rank"] == 3

    only_backend = (
        await client.get(
            f"{BASE_URL}/categories",
            params={"specialization_id": backend_middle["specialization"]["id"]},
        )
    ).json()
    assert [item["grade"]["code"] for item in only_backend] == [
        "intern",
        "junior",
        "middle",
        "senior",
    ]


@pytest.mark.parametrize(("query", "expected_slug"), [("питон", "python"), ("k8s", "kubernetes")])
async def test_skill_search_matches_aliases(
    client: AsyncClient, query: str, expected_slug: str
) -> None:
    """Поиск навыков находит их по русским и сокращённым алиасам."""
    page = (await client.get(f"{BASE_URL}/skills", params={"query": query})).json()
    assert expected_slug in {item["slug"] for item in page["items"]}


async def test_skill_search_filters_and_paginates(client: AsyncClient) -> None:
    """Фильтр по типу и специализации сужает выдачу, а пагинация возвращает общее количество."""
    specializations = (await client.get(f"{BASE_URL}/specializations")).json()
    devops_id = next(item["id"] for item in specializations if item["code"] == "devops")

    page = (
        await client.get(
            f"{BASE_URL}/skills",
            params={"kind": "tool", "specialization_id": devops_id, "limit": 5, "offset": 0},
        )
    ).json()
    assert page["limit"] == 5
    assert len(page["items"]) == 5
    assert page["total"] > 5
    assert {item["kind"] for item in page["items"]} == {"tool"}


async def test_dictionary_changes_require_methodist(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Менять справочники может только методист: аноним получает 401, кандидат — 403."""
    payload = {"code": "gamedev", "name": "Разработка игр"}
    anonymous = await client.post(f"{BASE_URL}/specializations", json=payload)
    candidate = await client.post(
        f"{BASE_URL}/specializations", json=payload, headers=auth_headers(await make_user())
    )

    assert anonymous.status_code == 401
    assert candidate.status_code == 403
    assert candidate.json()["error"]["code"] == "permission_denied"


async def test_methodist_creates_specialization_with_categories(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Новая специализация сразу получает категории для всех грейдов.

    При переименовании специализации обновляются и названия её категорий.
    """
    headers = auth_headers(await make_user(UserRole.METHODIST))
    created = await client.post(
        f"{BASE_URL}/specializations",
        json={"code": "gamedev", "name": "Разработка игр", "sort_order": 80},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    spec_id = created.json()["id"]

    categories = (
        await client.get(f"{BASE_URL}/categories", params={"specialization_id": spec_id})
    ).json()
    assert [item["code"] for item in categories] == [
        "gamedev-intern",
        "gamedev-junior",
        "gamedev-middle",
        "gamedev-senior",
    ]

    renamed = await client.patch(
        f"{BASE_URL}/specializations/{spec_id}", json={"name": "Геймдев"}, headers=headers
    )
    assert renamed.status_code == 200
    categories = (
        await client.get(f"{BASE_URL}/categories", params={"specialization_id": spec_id})
    ).json()
    assert categories[0]["title"] == "Геймдев · Intern"

    duplicate = await client.post(
        f"{BASE_URL}/specializations", json={"code": "gamedev", "name": "Ещё раз"}, headers=headers
    )
    assert duplicate.status_code == 409

    deleted = await client.delete(f"{BASE_URL}/specializations/{spec_id}", headers=headers)
    assert deleted.status_code == 204
    assert (
        await client.get(f"{BASE_URL}/categories", params={"specialization_id": spec_id})
    ).json() == []


async def test_methodist_manages_skills(client: AsyncClient, make_user: UserFactory) -> None:
    """Методист добавляет, меняет и удаляет навык.

    Дубль slug и ссылка на несуществующую специализацию отклоняются.
    """
    headers = auth_headers(await make_user(UserRole.METHODIST))
    created = await client.post(
        f"{BASE_URL}/skills",
        json={"slug": "unity", "name": "Unity", "kind": "framework", "aliases": ["юнити"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    skill_id = created.json()["id"]

    found = (await client.get(f"{BASE_URL}/skills", params={"query": "юнити"})).json()
    assert [item["slug"] for item in found["items"]] == ["unity"]

    updated = await client.patch(
        f"{BASE_URL}/skills/{skill_id}", json={"aliases": ["юнити", "unity3d"]}, headers=headers
    )
    assert updated.json()["aliases"] == ["юнити", "unity3d"]
    assert updated.json()["name"] == "Unity"

    duplicate = await client.post(
        f"{BASE_URL}/skills", json={"slug": "unity", "name": "U", "kind": "tool"}, headers=headers
    )
    assert duplicate.status_code == 409

    bad_link = await client.post(
        f"{BASE_URL}/skills",
        json={"slug": "godot", "name": "Godot", "kind": "framework", "specialization_ids": [9999]},
        headers=headers,
    )
    assert bad_link.status_code == 422
    assert bad_link.json()["error"]["details"] == {"specialization_ids": [9999]}

    assert (
        await client.delete(f"{BASE_URL}/skills/{skill_id}", headers=headers)
    ).status_code == 204
    missing = await client.delete(f"{BASE_URL}/skills/{skill_id}", headers=headers)
    assert missing.status_code == 404
