import json
from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import SearchStatus
from app.models.user import User, UserRole
from tests.factories import make_bank_candidate
from tests.helpers import auth_headers

UserFactory = Callable[..., Awaitable[User]]
COMPANY = {
    "name": "Кедр Технологии",
    "inn": "7701234560",
    "website": "kedr.example",
    "description": "Платёжный шлюз для малого бизнеса",
    "size": "medium",
    "city": "Москва",
    "contact_email": "hr@kedr.example",
    "contact_telegram": "kedr_hr",
    "recruiter_full_name": "Мария Соколова",
    "recruiter_position": "HR-партнёр",
}
NEED_TEXT = (
    "Python-разработчик (Middle) в команду платежей\n"
    "Требования: Python, FastAPI, PostgreSQL, опыт от 2 лет.\n"
    "Будет плюсом: Kafka.\n"
    "Удалённо, вилка 230–320 тыс. ₽ до вычета НДФЛ."
)


async def employer_headers(client: AsyncClient, make_user: UserFactory) -> dict[str, str]:
    """Работодатель с заполненным профилем компании."""
    headers = auth_headers(await make_user(UserRole.EMPLOYER))
    response = await client.put("/api/v1/employer/company", json=COMPANY, headers=headers)
    assert response.status_code == 200, response.text
    return headers


async def create_need(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    """Потребность из разобранного текста — так, как это делает интерфейс."""
    draft = (
        await client.post("/api/v1/employer/needs/parse", json={"text": NEED_TEXT}, headers=headers)
    ).json()
    payload = {
        "title": draft["title"],
        "raw_text": NEED_TEXT,
        "team_description": "Эквайринг, биллинг и сверки с банками",
        "specialization_id": draft["specialization"]["id"],
        "grade_ids": [grade["id"] for grade in draft["grades"]],
        "skills": [
            {"skill_id": item["skill"]["id"], "importance": item["importance"]}
            for item in draft["skills"]
        ],
        "work_formats": draft["work_formats"],
        "salary_from": draft["salary_from"],
        "salary_to": draft["salary_to"],
        "salary_gross": True,
    }
    response = await client.post("/api/v1/employer/needs", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _keys(value: Any) -> set[str]:
    """Все ключи JSON-ответа на любой глубине."""
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


async def test_company_profile_is_required_and_saved(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Без компании подбор недоступен; профиль сохраняется с нормализацией полей."""
    headers = auth_headers(await make_user(UserRole.EMPLOYER))
    empty = (await client.get("/api/v1/employer/company", headers=headers)).json()
    assert empty == {"company": None, "recruiter": None, "quota": None}
    blocked = await client.get("/api/v1/employer/needs", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "company_required"

    saved = (await client.put("/api/v1/employer/company", json=COMPANY, headers=headers)).json()
    assert saved["company"]["website"] == "https://kedr.example"
    assert saved["company"]["contact_telegram"] == "@kedr_hr"
    assert saved["company"]["trust_level"] == "new"
    assert saved["quota"] == {"daily_limit": 20, "used_today": 0, "remaining": 20}

    bad = await client.put(
        "/api/v1/employer/company", json={**COMPANY, "inn": "123"}, headers=headers
    )
    assert bad.status_code == 422
    candidate = auth_headers(await make_user())
    assert (await client.get("/api/v1/employer/company", headers=candidate)).status_code == 403


async def test_need_parse_and_salary_rules(client: AsyncClient, make_user: UserFactory) -> None:
    """Разбор текста находит стек и вилку; вилка обязательна и не шире чем вдвое (R2)."""
    headers = await employer_headers(client, make_user)
    draft = (
        await client.post("/api/v1/employer/needs/parse", json={"text": NEED_TEXT}, headers=headers)
    ).json()
    assert draft["specialization"]["code"] == "backend"
    assert [grade["code"] for grade in draft["grades"]] == ["middle"]
    skills = {item["skill"]["slug"]: item["importance"] for item in draft["skills"]}
    assert skills == {"python": "must", "fastapi": "must", "postgresql": "must", "kafka": "nice"}
    assert (draft["salary_from"], draft["salary_to"]) == (230_000, 320_000)
    assert draft["work_formats"] == ["remote"]

    need = await create_need(client, headers)
    base = {
        "title": "Тест",
        "specialization_id": need["specialization"]["id"],
        "grade_ids": [need["grades"][0]["id"]],
    }
    for salary in (
        {"salary_from": 300_000, "salary_to": 200_000},
        {"salary_from": 100_000, "salary_to": 250_000},
    ):
        response = await client.post(
            "/api/v1/employer/needs", json={**base, **salary}, headers=headers
        )
        assert response.status_code == 422
    missing = await client.post("/api/v1/employer/needs", json=base, headers=headers)
    assert missing.status_code == 422


async def test_shortlist_ranks_explains_and_hides_contacts(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Подборка: жёсткие фильтры, ранжирование, объяснение и полное отсутствие контактов (R4)."""
    strong = await make_bank_candidate(
        db_session,
        skills=("python", "fastapi", "postgresql", "sql", "kafka"),
        full_name="Сильный Кандидат",
    )
    java = await make_bank_candidate(
        db_session,
        skills=("java", "spring", "postgresql", "sql"),
        full_name="Джава Кандидат",
        telegram="java_bank_test",
        phone="+7 900 000-33-44",
    )
    unconfirmed = await make_bank_candidate(
        db_session, take_test=False, full_name="Заявленный Кандидат", telegram="claimed_bank_test"
    )
    hidden = await make_bank_candidate(db_session, published=False, full_name="Скрытый Кандидат")
    resting = await make_bank_candidate(
        db_session, search_status=SearchStatus.NOT_LOOKING, full_name="Отдыхающий Кандидат"
    )
    frontend = await make_bank_candidate(
        db_session,
        specialization="frontend",
        skills=("javascript", "react"),
        full_name="Фронт Кандидат",
    )
    headers = await employer_headers(client, make_user)
    need = await create_need(client, headers)

    response = await client.get(f"/api/v1/employer/needs/{need['id']}/shortlist", headers=headers)
    assert response.status_code == 200, response.text
    shortlist = response.json()
    ids = [entry["card"]["candidate_id"] for entry in shortlist["entries"]]
    assert shortlist["version"] == 1
    assert ids[0] == strong.profile_id
    assert {strong.profile_id, java.profile_id, unconfirmed.profile_id} <= set(ids)
    assert not {hidden.profile_id, resting.profile_id, frontend.profile_id} & set(ids)
    assert ids.index(unconfirmed.profile_id) > ids.index(strong.profile_id)

    top = shortlist["entries"][0]
    assert top["card"]["grade_status"] == "confirmed"
    assert top["match"]["score"] > 0
    assert {item["key"] for item in top["match"]["components"]} == {
        "skills",
        "verified",
        "semantic",
        "conditions",
    }
    texts = [item["text"] for item in top["match"]["explanation"]]
    assert any(text.startswith("Закрывает 3 из 3 обязательных") for text in texts)
    assert any("Подтверждено тестом" in text for text in texts)
    unconfirmed_entry = next(
        e for e in shortlist["entries"] if e["card"]["candidate_id"] == unconfirmed.profile_id
    )
    assert "unconfirmed_grade" in unconfirmed_entry["match"]["penalties"]

    raw = response.text
    for person in (strong, java, unconfirmed):
        assert person.full_name not in raw
        assert person.phone not in raw
        assert person.telegram not in raw
        assert person.user.email not in raw
    assert "Секретная Компания" not in raw
    assert not {"full_name", "phone", "telegram"} & _keys(shortlist["entries"][0]["card"])
    assert all(entry["contacts"] is None for entry in shortlist["entries"])


async def test_small_pool_is_autofilled_with_adjacent_grades(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Точного грейда мало — подборка добирает соседний грейд с пометкой и понижением."""
    exact = await make_bank_candidate(db_session, full_name="Точный Кандидат")
    senior = await make_bank_candidate(
        db_session, grade="senior", full_name="Соседний Кандидат", telegram="senior_fill"
    )
    headers = await employer_headers(client, make_user)
    need = await create_need(client, headers)

    response = await client.get(f"/api/v1/employer/needs/{need['id']}/shortlist", headers=headers)
    assert response.status_code == 200, response.text
    shortlist = response.json()
    by_id = {entry["card"]["candidate_id"]: entry for entry in shortlist["entries"]}
    assert shortlist["stats"]["autofilled"] is True
    assert {exact.profile_id, senior.profile_id} <= set(by_id)
    assert "adjacent_grade" in by_id[senior.profile_id]["match"]["penalties"]
    assert "adjacent_grade" not in by_id[exact.profile_id]["match"]["penalties"]

    expanded = await client.post(
        f"/api/v1/employer/needs/{need['id']}/shortlists",
        json={"expand_grades": True},
        headers=headers,
    )
    assert expanded.status_code == 201, expanded.text
    assert expanded.json()["stats"]["autofilled"] is False


async def test_refinement_keeps_pinned_and_drops_hidden(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Уточнение создаёт новую версию; закреплённый остаётся, скрытый пропадает."""
    strong = await make_bank_candidate(db_session)
    unconfirmed = await make_bank_candidate(db_session, take_test=False, telegram="claimed_two")
    other = await make_bank_candidate(
        db_session, skills=("java", "spring", "postgresql"), telegram="java_two"
    )
    headers = await employer_headers(client, make_user)
    need = await create_need(client, headers)
    await client.get(f"/api/v1/employer/needs/{need['id']}/shortlist", headers=headers)

    marks = f"/api/v1/employer/needs/{need['id']}/marks"
    pin = await client.put(
        f"{marks}/{unconfirmed.profile_id}",
        json={"mark": "pinned", "note": "позвать"},
        headers=headers,
    )
    assert pin.status_code == 204
    await client.put(f"{marks}/{other.profile_id}", json={"mark": "hidden"}, headers=headers)

    refined = await client.post(
        f"/api/v1/employer/needs/{need['id']}/shortlists",
        json={"confirmed_only": True},
        headers=headers,
    )
    assert refined.status_code == 201, refined.text
    body = refined.json()
    by_id = {entry["card"]["candidate_id"]: entry for entry in body["entries"]}
    assert body["version"] == 2 and body["versions"] == [2, 1]
    assert by_id[unconfirmed.profile_id]["mark"] == "pinned"
    assert by_id[unconfirmed.profile_id]["outside_filters"] is True
    assert by_id[unconfirmed.profile_id]["note"] == "позвать"
    assert body["entries"][0]["card"]["candidate_id"] == unconfirmed.profile_id
    assert strong.profile_id in by_id and other.profile_id not in by_id

    first = await client.get(
        f"/api/v1/employer/needs/{need['id']}/shortlist?version=1", headers=headers
    )
    assert other.profile_id in {e["card"]["candidate_id"] for e in first.json()["entries"]}


async def test_categories_bank_and_card(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Рекомендованные категории, банк с фильтрами и карточка с баллом по потребности."""
    strong = await make_bank_candidate(
        db_session, about="Пишите на ivan@mail.ru или звоните +7 999 123-45-67. Делаю платежи."
    )
    junior = await make_bank_candidate(db_session, grade="junior", telegram="junior_bank_test")
    headers = await employer_headers(client, make_user)
    need = await create_need(client, headers)

    categories = (
        await client.get(f"/api/v1/employer/needs/{need['id']}/categories", headers=headers)
    ).json()
    relations = {item["category"]["code"]: item for item in categories}
    assert relations["backend-middle"]["relation"] == "target"
    assert relations["backend-middle"]["candidates"] >= 1
    assert relations["backend-junior"]["relation"] == "adjacent_grade"
    assert relations["devops-middle"]["relation"] == "adjacent_specialization"

    bank = (
        await client.get(
            "/api/v1/employer/candidates",
            params={"specialization_id": need["specialization"]["id"], "confirmed_only": "true"},
            headers=headers,
        )
    ).json()
    ids = [item["card"]["candidate_id"] for item in bank["items"]]
    assert {strong.profile_id, junior.profile_id} <= set(ids)
    assert bank["unconfirmed"] == 0 and bank["total"] == len(ids)

    card = (
        await client.get(
            f"/api/v1/employer/candidates/{strong.profile_id}",
            params={"need_id": need["id"]},
            headers=headers,
        )
    ).json()
    assert card["contacts"] is None
    assert "ivan@mail.ru" not in card["card"]["about"] and "[скрыто]" in card["card"]["about"]
    assert card["card"]["test"]["competencies"]
    assert card["card"]["fsp"]["state"] == "not_linked"
    assert card["match"]["score"] > 0
    assert card["card"]["experiences"][0]["company_name"] is None

    other_company = await employer_headers(client, make_user)
    foreign = await client.get(f"/api/v1/employer/needs/{need['id']}", headers=other_company)
    assert foreign.status_code == 404
    assert (
        json.loads(
            (
                await client.get(
                    "/api/v1/employer/candidates/00000000-0000-0000-0000-000000000000",
                    headers=headers,
                )
            ).text
        )["error"]["code"]
        == "not_found"
    )
