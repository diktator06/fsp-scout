from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.user import UserRole
from tests.api.test_employer_matching import UserFactory, employer_headers
from tests.api.test_microtasks import create_tasks
from tests.api.test_vacancies import publish_vacancy
from tests.factories import make_bank_candidate
from tests.helpers import auth_headers

METHODIST = "/api/v1/methodist"


async def test_item_bank_lists_families_and_generates_unique_instances(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Банк специализации: веса компетенций, семейства и разные экземпляры одного семейства."""
    headers = auth_headers(await make_user(UserRole.METHODIST))
    specs = (await client.get("/api/v1/dictionaries/specializations", headers=headers)).json()
    backend = next(item["id"] for item in specs if item["code"] == "backend")

    bank = await client.get(
        f"{METHODIST}/item-bank", params={"specialization_id": backend}, headers=headers
    )
    assert bank.status_code == 200, bank.text
    body = bank.json()
    assert body["specialization"]["code"] == "backend"
    assert sum(item["weight"] for item in body["competencies"]) > 0.99
    assert body["families"] and all(family["has_generator"] for family in body["families"])
    family = next(item for item in body["families"] if item["status"] == "active")

    samples = await client.get(
        f"{METHODIST}/item-bank/{family['id']}/samples", params={"count": 3}, headers=headers
    )
    assert samples.status_code == 200, samples.text
    instances = samples.json()["instances"]
    assert len(instances) == 3
    assert len({item["seed"] for item in instances}) == 3
    assert all(item["payload"]["prompt"] and item["answer"]["kind"] for item in instances)

    replay = await client.get(
        f"{METHODIST}/item-bank/{family['id']}/samples",
        params={"seed": [instances[0]["seed"]]},
        headers=headers,
    )
    assert replay.json()["instances"][0]["payload"] == instances[0]["payload"]

    candidate = auth_headers(await make_user(UserRole.CANDIDATE))
    assert (await client.get(f"{METHODIST}/item-bank", headers=candidate)).status_code == 403


async def test_exposure_rate_counts_sessions_with_the_competency(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Доля показов — от сессий, где компетенция входила в тест, поэтому не больше 100 %.

    Алгоритмы общие для Backend и Frontend: при знаменателе «сессии одной
    специализации» семейство, показанное обоим кандидатам, получило бы 200 %.
    """
    await make_bank_candidate(db_session)
    await make_bank_candidate(
        db_session, specialization="frontend", skills=("javascript", "react"), telegram="front"
    )
    headers = auth_headers(await make_user(UserRole.METHODIST))
    families = (await client.get(f"{METHODIST}/item-bank", headers=headers)).json()["families"]
    shown = [family for family in families if family["exposure_count"] > 0]
    assert shown
    assert all(0 < family["exposure_rate"] <= 1 for family in shown)
    shared = [family for family in shown if family["competency"]["code"] == "algorithms"]
    assert shared and all(family["exposure_rate"] <= 1 for family in shared)


async def test_family_status_change_is_audited_and_guarded(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Семейство переводится в пилот с записью в аудит; последнее активное не выключить."""
    headers = auth_headers(await make_user(UserRole.METHODIST))
    families = (await client.get(f"{METHODIST}/item-bank", headers=headers)).json()["families"]
    by_competency: dict[str, list[dict[str, object]]] = {}
    for family in families:
        if family["status"] == "active":
            by_competency.setdefault(family["competency"]["code"], []).append(family)
    pair = next(items for items in by_competency.values() if len(items) >= 2)

    first = await client.put(
        f"{METHODIST}/item-bank/{pair[0]['id']}/status",
        json={"status": "pilot", "reason": "Низкая корреляция с итогом"},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "pilot"
    audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "item_family_status_changed")
    )
    assert audit is not None and audit.meta["to"] == "pilot"

    remaining = pair[1:]
    for family in remaining[:-1]:
        response = await client.put(
            f"{METHODIST}/item-bank/{family['id']}/status",
            json={"status": "retired", "reason": "Ревизия"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
    last = await client.put(
        f"{METHODIST}/item-bank/{remaining[-1]['id']}/status",
        json={"status": "retired", "reason": "Ревизия"},
        headers=headers,
    )
    assert last.status_code == 409


async def test_vacancy_test_shows_blueprint_coverage_and_microtasks(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Вакансия → категория → состав теста под стек → экземпляры около порога → микрозадачи."""
    employer = await employer_headers(client, make_user)
    vacancy = await publish_vacancy(client, employer)
    await create_tasks(client, employer)
    headers = auth_headers(await make_user(UserRole.METHODIST))

    rows = (await client.get(f"{METHODIST}/vacancies", headers=headers)).json()
    assert any(row["id"] == vacancy["id"] for row in rows)

    response = await client.get(f"{METHODIST}/vacancies/{vacancy['id']}/test", headers=headers)
    assert response.status_code == 200, response.text
    test = response.json()
    assert test["vacancy"]["specialization"]["code"] == "backend"
    assert [grade["grade"]["code"] for grade in test["grades"]] == ["middle"]
    focus = test["grades"][0]["families"]
    assert len(focus) == 3 and all(item["sample"]["payload"]["prompt"] for item in focus)
    included = [item for item in test["competencies"] if item["included"]]
    assert included and abs(sum(item["weight"] for item in included) - 1) < 0.01
    python = next(item for item in test["skills"] if item["slug"] == "python")
    assert python["verified_by"]
    assert 0 < test["coverage"] <= 1
    assert {task["kind"] for task in test["microtasks"]} == {"solve", "approach"}
    assert test["items_visible"] is True


async def test_employer_sees_own_vacancy_test_without_items(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Работодатель видит состав теста и покрытие своей вакансии, но не задания; чужая — 404."""
    employer = await employer_headers(client, make_user)
    vacancy = await publish_vacancy(client, employer)
    url = f"/api/v1/employer/vacancies/{vacancy['id']}/test"

    response = await client.get(url, headers=employer)
    assert response.status_code == 200, response.text
    test = response.json()
    assert test["items_visible"] is False
    assert [grade["grade"]["code"] for grade in test["grades"]] == ["middle"]
    assert all(grade["families"] == [] for grade in test["grades"])
    assert "sample" not in response.text and "answer" not in response.text
    assert any(item["included"] for item in test["competencies"])
    assert 0 < test["coverage"] <= 1

    stranger = await employer_headers(client, make_user)
    assert (await client.get(url, headers=stranger)).status_code == 404
    candidate = auth_headers(await make_user(UserRole.CANDIDATE))
    assert (await client.get(url, headers=candidate)).status_code == 403


async def test_theta_cut_keeps_grade_order_and_is_audited(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Порог меняется в пределах соседних грейдов; нарушение порядка — 422."""
    headers = auth_headers(await make_user(UserRole.METHODIST))
    settings = await client.get(f"{METHODIST}/assessment-settings", headers=headers)
    assert settings.status_code == 200, settings.text
    body = settings.json()
    assert body["final_estimator"].startswith("WLE")
    assert body["full"]["min_items"] < body["full"]["max_items"]
    scale = next(item for item in body["scales"] if item["specialization"]["code"] == "backend")
    cuts = {item["grade"]["code"]: item for item in scale["categories"]}
    middle = cuts["middle"]

    moved = await client.put(
        f"{METHODIST}/categories/{middle['category_id']}/theta-cut",
        json={"theta_cut": middle["theta_cut"] + 0.1, "reason": "Калибровка на пилоте"},
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    updated = {item["grade"]["code"]: item for item in moved.json()["categories"]}
    assert updated["middle"]["theta_cut"] == round(middle["theta_cut"] + 0.1, 2)
    audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "category_theta_cut_changed")
    )
    assert audit is not None

    crossing = await client.put(
        f"{METHODIST}/categories/{middle['category_id']}/theta-cut",
        json={"theta_cut": cuts["senior"]["theta_cut"], "reason": "Ошибка"},
        headers=headers,
    )
    assert crossing.status_code == 422
