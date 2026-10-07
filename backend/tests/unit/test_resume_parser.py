from datetime import date

from app.services.candidate.resume_parser import parse_resume_text
from tests.unit.test_matching_core import CATALOG

TODAY = date(2026, 10, 7)
RESUME = """Мария Иванова
Senior Python-разработчик
Казань · +7 (912) 345-67-89 · maria.ivanova@example.com · Telegram: @maria_dev

О себе
Пишу бэкенд на Python и FastAPI, работала с PostgreSQL и Kafka. Наставник для джунов.

Опыт работы
Ведущий разработчик — ООО «Платёжный шлюз»
март 2021 — настоящее время
Проектировала архитектуру сервиса биллинга, тимлид группы из 4 человек.
Python-разработчик, Цифровые решения
06.2018 – 02.2021
Разработка API на Django, интеграции с банками.

Образование
КФУ, 2018
"""


def test_contacts_name_and_city() -> None:
    """ФИО из шапки, email, телефон в едином формате, Telegram и город."""
    parsed = parse_resume_text(RESUME, CATALOG, TODAY)
    assert parsed.full_name == "Мария Иванова"
    assert parsed.email == "maria.ivanova@example.com"
    assert parsed.phone == "+79123456789"
    assert parsed.telegram == "@maria_dev"
    assert parsed.city == "Казань"
    assert parsed.evidence["full_name"] == "Мария Иванова"


def test_experience_periods_years_and_grade() -> None:
    """Места работы с датами, стаж по объединению периодов, грейд из шапки."""
    parsed = parse_resume_text(RESUME, CATALOG, TODAY)
    first, second = parsed.experiences
    assert (first.position, first.company_name) == ("Ведущий разработчик", "ООО «Платёжный шлюз»")
    assert first.started_on == date(2021, 3, 1) and first.ended_on is None
    assert "биллинга" in first.description
    assert (second.position, second.company_name) == ("Python-разработчик", "Цифровые решения")
    assert second.ended_on == date(2021, 2, 1)
    assert parsed.experience_years == 8.5
    assert parsed.grade_code == "senior"


def test_skills_roles_and_specialization() -> None:
    """Стек из справочника, роли в команде по ключевым словам, специализация."""
    parsed = parse_resume_text(RESUME, CATALOG, TODAY)
    assert {item.skill_id for item in parsed.skills} >= {1, 2, 3, 4, 8}
    assert {"team_lead", "mentor", "architect", "developer"} <= set(parsed.team_roles)
    assert parsed.specialization_code == "backend"


def test_overlaps_explicit_years_and_soft_skills() -> None:
    """Параллельная работа не удваивает стаж; без дат берётся «опыт N лет»; софт-скиллы."""
    overlapping = parse_resume_text(
        "Иван Петров\nРазработчик, Альфа\n2020 — 2022\nРазработчик, Бета\n2021 — 2022\n",
        CATALOG,
        TODAY,
    )
    assert overlapping.experience_years == 3
    explicit = parse_resume_text(
        "Пётр Смирнов\nОпыт работы 3 года на Go. Сильная коммуникация в команде.", CATALOG, TODAY
    )
    assert explicit.experience_years == 3
    assert explicit.grade_code == "middle"
    assert explicit.soft_skills == ["Коммуникация"]
