import asyncio
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.schemas.candidate import CandidateProfileRead

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "pdf"
FONTS_DIR = TEMPLATES_DIR / "fonts"

_TEAM_ROLES = {
    "developer": "разработчик",
    "team_lead": "тимлид",
    "tech_lead": "техлид",
    "mentor": "ментор",
    "architect": "архитектор",
    "researcher": "исследователь",
}
_WORK_FORMATS = {"office": "офис", "hybrid": "гибрид", "remote": "удалённо"}
_MONTHS = ("янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")


@lru_cache
def _environment() -> Environment:
    """Окружение Jinja2 для шаблона PDF с автоэкранированием пользовательского текста."""
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
    )


def _month(value: date) -> str:
    """Месяц и год: «сен 2024»."""
    return f"{_MONTHS[value.month - 1]} {value.year}"


def _period(started_on: date, ended_on: date | None) -> str:
    """Период работы: «сен 2022 — мар 2024» или «… — по настоящее время»."""
    end = _month(ended_on) if ended_on else "по настоящее время"
    return f"{_month(started_on)} — {end}"


def _years(value: float) -> str:
    """Стаж словами: «3 года», «1,5 года», «5 лет»."""
    if value != int(value):
        return f"{str(value).replace('.', ',')} года"
    whole = int(value)
    if 11 <= whole % 100 <= 14:
        return f"{whole} лет"
    return f"{whole} " + {1: "год", 2: "года", 3: "года", 4: "года"}.get(whole % 10, "лет")


def build_context(profile: CandidateProfileRead) -> dict[str, Any]:
    """Данные для шаблона: даты, роли и форматы уже переведены в человекочитаемый вид.

    Подтверждённые навыки идут первыми: это главное, что отличает профиль на
    платформе от обычного резюме.
    """
    skills = sorted(profile.skills, key=lambda item: (not item.is_verified, item.skill.name))
    category = None
    if profile.category is not None:
        assigned = profile.grade_assigned_at
        category = {
            "specialization": profile.category.specialization.name,
            "grade": profile.category.grade.name,
            "assigned_at": assigned.strftime("%d.%m.%Y") if assigned else "",
        }
    return {
        "fonts_url": FONTS_DIR.as_uri(),
        "alias": profile.public_alias,
        "generated_at": datetime.now(UTC).strftime("%d.%m.%Y"),
        "full_name": profile.full_name,
        "email": profile.email,
        "phone": profile.phone,
        "telegram": profile.telegram,
        "city": profile.city,
        "about": profile.about.strip(),
        "experience_years": _years(profile.experience_years)
        if profile.experience_years is not None
        else None,
        "work_formats": ", ".join(_WORK_FORMATS.get(item, item) for item in profile.work_formats),
        "team_roles": ", ".join(_TEAM_ROLES.get(item, item) for item in profile.team_roles),
        "soft_skills": ", ".join(profile.soft_skills),
        "salary": f"{profile.salary_expectation_from:,}".replace(",", " ")
        if profile.salary_expectation_from
        else None,
        "salary_basis": "до вычета НДФЛ" if profile.salary_expectation_gross else "на руки",
        "relocation_ready": profile.relocation_ready,
        "category": category,
        "skills": [
            {"name": item.skill.name, "verified": item.is_verified, "level": item.self_level}
            for item in skills
        ],
        "experiences": [
            {
                "position": job.position,
                "company_name": job.company_name,
                "description": job.description,
                "period": _period(job.started_on, job.ended_on),
            }
            for job in profile.experiences
        ],
        "educations": [
            {
                "institution": item.institution,
                "degree": item.degree,
                "graduated_year": item.graduated_year,
            }
            for item in profile.educations
        ],
    }


def _render_blocking(html: str) -> bytes:
    """Рендер HTML в PDF. WeasyPrint импортируется лениво: ему нужны системные библиотеки pango."""
    from weasyprint import HTML

    return bytes(HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf())


async def render_profile_pdf(profile: CandidateProfileRead) -> bytes:
    """Стандартизированный PDF-профиль кандидата.

    Рендер занимает сотни миллисекунд процессорного времени, поэтому выполняется в
    отдельном потоке и не блокирует обработку других запросов.
    """
    html = _environment().get_template("candidate_profile.html").render(**build_context(profile))
    return await asyncio.to_thread(_render_blocking, html)
