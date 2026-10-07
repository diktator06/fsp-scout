from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from weasyprint import HTML

from app.models.user import UserRole
from tests.api.test_employer_matching import UserFactory
from tests.factories import make_bank_candidate
from tests.helpers import auth_headers

PARSE = "/api/v1/candidates/me/resume/parse"
RESUME_HTML = """
<html><body>
<h1>Алексей Смирнов</h1>
<p>Middle Frontend-разработчик · Новосибирск</p>
<p>alexey.smirnov@example.com · +7 913 555-12-34 · t.me/alexey_front</p>
<h2>Опыт работы</h2>
<p>Frontend-разработчик — Студия «Пиксель»</p>
<p>сен 2022 — по настоящее время</p>
<p>Личный кабинет на React и TypeScript, дизайн-система, Jest. Наставник стажёров.</p>
<h2>Навыки</h2>
<p>React, TypeScript, CSS, Redux, работа в команде</p>
</body></html>
"""


def pdf(html: str) -> bytes:
    """PDF из HTML тем же движком, что собирает профиль кандидата."""
    return HTML(string=html).write_pdf()


async def test_parse_generated_resume(client: AsyncClient, make_user: UserFactory) -> None:
    """Из PDF извлекаются контакты, стек, роли, стаж и подсказки по категории."""
    headers = auth_headers(await make_user(UserRole.CANDIDATE))
    response = await client.post(
        PARSE, files={"file": ("cv.pdf", pdf(RESUME_HTML), "application/pdf")}, headers=headers
    )
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["full_name"] == "Алексей Смирнов"
    assert draft["email"] == "alexey.smirnov@example.com"
    assert draft["phone"] == "+79135551234"
    assert draft["telegram"] == "@alexey_front"
    assert draft["city"] == "Новосибирск"
    assert {"React", "TypeScript", "CSS", "Redux"} <= {
        item["skill"]["name"] for item in draft["skills"]
    }
    assert "Командная работа" in draft["soft_skills"]
    assert "mentor" in draft["team_roles"]
    assert draft["specialization"]["code"] == "frontend"
    assert draft["grade"]["code"] == "middle"
    assert draft["experiences"][0]["company_name"] == "Студия «Пиксель»"
    assert draft["warnings"]
    profile = (await client.get("/api/v1/candidates/me/profile", headers=headers)).json()
    assert profile["full_name"] is None


async def test_own_profile_pdf_round_trip(client: AsyncClient, db_session: AsyncSession) -> None:
    """PDF-профиль «Скаута» распознаётся обратно: имя, навыки и место работы."""
    candidate = await make_bank_candidate(db_session)
    headers = auth_headers(candidate.user)
    exported = await client.get("/api/v1/candidates/me/profile.pdf", headers=headers)
    assert exported.status_code == 200
    draft = (
        await client.post(
            PARSE,
            files={"file": ("profile.pdf", exported.content, "application/pdf")},
            headers=headers,
        )
    ).json()
    assert draft["full_name"] == candidate.full_name
    assert {"Python", "FastAPI", "PostgreSQL"} <= {
        item["skill"]["name"] for item in draft["skills"]
    }
    assert draft["experiences"][0]["company_name"] == "Секретная Компания"


async def test_rejects_non_pdf_and_scans(client: AsyncClient, make_user: UserFactory) -> None:
    """Не PDF и PDF без текстового слоя дают понятную ошибку, а не пустой черновик."""
    headers = auth_headers(await make_user(UserRole.CANDIDATE))
    text = await client.post(
        PARSE, files={"file": ("cv.txt", b"plain text", "text/plain")}, headers=headers
    )
    assert text.status_code == 422
    blank = await client.post(
        PARSE,
        files={"file": ("scan.pdf", pdf("<html><body></body></html>"), "application/pdf")},
        headers=headers,
    )
    assert blank.status_code == 422
    assert "скан" in blank.json()["error"]["message"]
    employer = auth_headers(await make_user(UserRole.EMPLOYER))
    assert (
        await client.post(
            PARSE, files={"file": ("cv.pdf", pdf(RESUME_HTML), "application/pdf")}, headers=employer
        )
    ).status_code == 403
