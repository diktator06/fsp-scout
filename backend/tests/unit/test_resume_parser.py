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


def test_name_split_across_header_lines() -> None:
    """Имя, перенесённое по словам в шапке двухколоночного резюме, собирается обратно."""
    text = "СКАУТ · ПРОФИЛЬ СПЕЦИАЛИСТА\nТимур\nПриёмкин\nКазань · опыт 3 года\n#ZXF3\n"
    assert parse_resume_text(text, CATALOG, TODAY).full_name == "Тимур Приёмкин"
    single = "Резюме\nКазань\nPython\n"
    assert parse_resume_text(single, CATALOG, TODAY).full_name is None


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


HH_RESUME = """Петрова Анна Сергеевна
Женщина, 31 год, родилась 2 марта 1995
+7 (912) 3456789 — предпочитаемый способ связи • telegram: https://t.me/anna_petrova_dev
anna.petrova@example.com
Проживает: Казань
Не готова к переезду, готова к командировкам
Желаемая должность и зарплата
Middle Python-разработчик
Тип занятости: полная занятость
Формат работы: удалённо, гибрид
Опыт работы — 6 лет 3 месяца
Апрель 2022 —
настоящее время
4 года 7 месяцев
ООО «Облако Плюс»
Казань, cloud-plus.example.ru
Информационные технологии, системная интеграция, интернет
• Разработка программного обеспечения
Python-разработчик
Сервис биллинга на FastAPI и PostgreSQL.
Анна Петрова • Резюме обновлено 1 октября 2026 в 10:00
Июль 2020 —
Март 2022
1 год 9 месяцев
АО «Цифровые решения»
Москва
• Банк
Младший разработчик
Интеграции с банками на Django.
Образование
Высшее
2017
Магистр
Казанский федеральный университет
Институт ВМиИТ, Прикладная информатика
2015
Бакалавр
Казанский федеральный университет
Институт ВМиИТ, Прикладная информатика
Анна Петрова • Резюме обновлено 1 октября 2026 в 10:00
2015
Бакалавр
Казанский федеральный университет
Институт ВМиИТ, Прикладная информатика
Повышение квалификации, курсы
2024 Яндекс Практикум
Навыки
Навыки Python FastAPI PostgreSQL Docker
Дополнительная информация
Обо мне Пишу бэкенд для платёжных сервисов, наставник для двух стажёров.
Люблю понятные API и тесты.
"""

LINKEDIN_RESUME = """Ivan Smirnov
Senior Backend Engineer
Telegram: @ivan_smirnov_dev
Summary
Backend engineer focused on Python services and distributed systems.
Experience
Yandex
Senior Backend Engineer
January 2021 - Present (5 years 10 months)
Moscow, Russia
Built payment APIs in Python.
Sber
Backend Developer
March 2018 - December 2020 (2 years 10 months)
Worked on internal tools.
Education
Moscow State University
Master of Science, Computer Science · (2012 - 2018)
"""


def test_hh_export_experience_education_about_and_conditions() -> None:
    """Выгрузка hh.ru: перенос периода, шапка места работы, колонтитулы, образование, «О себе»."""
    parsed = parse_resume_text(HH_RESUME, CATALOG, TODAY)
    assert parsed.full_name == "Петрова Анна Сергеевна"
    assert parsed.telegram == "@anna_petrova_dev"
    assert [(job.position, job.company_name) for job in parsed.experiences] == [
        ("Python-разработчик", "ООО «Облако Плюс»"),
        ("Младший разработчик", "АО «Цифровые решения»"),
    ]
    first, second = parsed.experiences
    assert (first.started_on, first.ended_on) == (date(2022, 4, 1), None)
    assert (second.started_on, second.ended_on) == (date(2020, 7, 1), date(2022, 3, 1))
    assert first.description == "Сервис биллинга на FastAPI и PostgreSQL."
    assert "Резюме обновлено" not in first.description
    assert parsed.experience_years == 6.5
    assert [(item.institution, item.graduated_year) for item in parsed.educations] == [
        ("Казанский федеральный университет", 2017),
        ("Казанский федеральный университет", 2015),
    ]
    assert parsed.educations[0].degree.startswith("Магистр, Институт ВМиИТ")
    assert parsed.about is not None
    assert parsed.about.startswith("Пишу бэкенд для платёжных сервисов")
    assert parsed.about.endswith("Люблю понятные API и тесты.")
    assert parsed.work_formats == ["hybrid", "remote"]
    assert parsed.relocation_ready is False


def test_linkedin_export_header_above_period_and_years_in_parens() -> None:
    """LinkedIn: компания и должность над периодом, длительность в скобках, степень с годами."""
    parsed = parse_resume_text(LINKEDIN_RESUME, CATALOG, TODAY)
    assert [(job.position, job.company_name) for job in parsed.experiences] == [
        ("Senior Backend Engineer", "Yandex"),
        ("Backend Developer", "Sber"),
    ]
    assert parsed.experiences[0].description == "Built payment APIs in Python."
    assert parsed.experiences[1].description == "Worked on internal tools."
    assert parsed.educations[0].institution == "Moscow State University"
    assert parsed.educations[0].graduated_year == 2018
    assert parsed.about == "Backend engineer focused on Python services and distributed systems."


def test_telegram_link_and_relocation_phrases() -> None:
    """Ник Telegram — из ссылки t.me, а не слово https; переезд — да, нет или неизвестно."""
    link = parse_resume_text("Иван Иванов\ntelegram: https://t.me/ivan_dev_2026\n", CATALOG, TODAY)
    assert link.telegram == "@ivan_dev_2026"
    ready = parse_resume_text("Иван Иванов\nГотов к переезду: Казань\n", CATALOG, TODAY)
    assert ready.relocation_ready is True
    impossible = parse_resume_text("Иван Иванов\nПереезд невозможен\n", CATALOG, TODAY)
    assert impossible.relocation_ready is False
    assert parse_resume_text(RESUME, CATALOG, TODAY).relocation_ready is None
