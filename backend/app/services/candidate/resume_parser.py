import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from app.models.dictionary import SkillKind
from app.services.matching.need_parser import (
    CatalogSkill,
    FoundSkill,
    detect_city,
    detect_specialization,
    find_skills,
    grade_mentions,
)

MAX_DESCRIPTION = 1000
HEADER_LINES = 12

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s-]*\d{2}[\s-]*\d{2}")
_TELEGRAM = re.compile(
    r"(?:t\.me/|telegram[:\s]+@?|tg[:\s]+@?|(?<![\w.])@)([A-Za-z][A-Za-z0-9_]{4,31})", re.IGNORECASE
)
_NAME_LABEL = re.compile(r"^(?:фио|имя)\s*[:—-]\s*(.+)$", re.IGNORECASE)
_NAME = re.compile(r"^([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)\s+([А-ЯЁ][а-яё]+)(?:\s+([А-ЯЁ][а-яё]+))?$")
_EXPLICIT_YEARS = re.compile(
    r"(?:опыт\w*|стаж\w*)[^.\n\d]{0,30}?(\d+(?:[.,]\d)?)\s*\+?\s*(?:год|лет|г\.)", re.IGNORECASE
)

_MONTHS = {
    "янв": 1,
    "фев": 2,
    "мар": 3,
    "апр": 4,
    "мая": 5,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "авг": 8,
    "сен": 9,
    "окт": 10,
    "ноя": 11,
    "дек": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_MONTH_WORD = (
    r"(?:янв|фев|мар|апр|ма[йя]|июн|июл|авг|сен|окт|ноя|дек"
    r"|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[а-яёa-z.]*"
)
_PRESENT = (
    r"(?:по\s+)?(?:настоящее\s+время|наст\.?\s*вр(?:емя|\.)?|н\.\s*в\.|сейчас"
    r"|текущее\s+время|present|now|current)"
)


def _date_pattern(prefix: str) -> str:
    """Шаблон даты: «мар 2021», «03.2021» или «2021» с именованными группами."""
    return (
        rf"(?:(?P<{prefix}word>{_MONTH_WORD})\s+(?P<{prefix}wyear>(?:19|20)\d{{2}})"
        rf"|(?P<{prefix}num>\d{{1,2}})[./](?P<{prefix}nyear>(?:19|20)\d{{2}})"
        rf"|(?P<{prefix}year>(?:19|20)\d{{2}}))"
    )


_RANGE = re.compile(
    _date_pattern("a") + r"\s*(?:[–—-]|по|to)\s*(?:" + _PRESENT + "|" + _date_pattern("b") + ")",
    re.IGNORECASE,
)
_SECTION = re.compile(
    r"^(?:образование|навыки|ключевые навыки|о себе|обо мне|контакты|языки|курсы|"
    r"сертификаты|проекты|education|skills|about|languages|projects)\s*:?$",
    re.IGNORECASE,
)
_ROLE_WORDS = re.compile(
    r"разработчик|программист|developer|engineer|инженер|аналитик|analyst|тестировщик|"
    r"qa|тимлид|team ?lead|техлид|tech ?lead|архитектор|architect|devops|sre|стаж[её]р|"
    r"intern|специалист|scientist|data|руководитель|lead|head",
    re.IGNORECASE,
)
_TEAM_ROLES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "team_lead",
        re.compile(r"тимлид|team ?lead|руководител\w* (?:команды|группы|отдела)", re.IGNORECASE),
    ),
    ("tech_lead", re.compile(r"техлид|tech ?lead|техническ\w+ лидер", re.IGNORECASE)),
    ("mentor", re.compile(r"ментор|наставни|mentor|онбординг\w* новичков", re.IGNORECASE)),
    ("architect", re.compile(r"архитектор|architect|проектировал\w* архитектур", re.IGNORECASE)),
    ("researcher", re.compile(r"исследовател|researcher|r&d|научн\w+ работ", re.IGNORECASE)),
    ("developer", re.compile(r"разработчик|программист|developer|engineer|инженер", re.IGNORECASE)),
)
_SEPARATORS = (" — ", " – ", " - ", " | ", " @ ", ", ", " в ")


@dataclass(frozen=True, slots=True)
class ResumeExperience:
    """Место работы из резюме — черновик, который кандидат проверит."""

    position: str
    company_name: str
    started_on: date | None
    ended_on: date | None
    description: str


@dataclass
class ParsedResume:
    """Что удалось извлечь из текста резюме. Каждое поле — с фрагментом-источником."""

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    telegram: str | None = None
    city: str | None = None
    experience_years: float | None = None
    grade_code: str | None = None
    specialization_code: str | None = None
    skills: list[FoundSkill] = field(default_factory=list)
    soft_skills: list[str] = field(default_factory=list)
    team_roles: list[str] = field(default_factory=list)
    experiences: list[ResumeExperience] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)


def _date(match: re.Match[str], prefix: str, *, end: bool) -> date | None:
    """Дата из части диапазона: «мар 2021», «03.2021» или просто «2021»."""
    groups = match.groupdict()
    if groups.get(f"{prefix}wyear"):
        word = (groups[f"{prefix}word"] or "")[:3].lower()
        return date(int(groups[f"{prefix}wyear"]), _MONTHS.get(word, 1), 1)
    if groups.get(f"{prefix}nyear"):
        month = min(12, max(1, int(groups[f"{prefix}num"])))
        return date(int(groups[f"{prefix}nyear"]), month, 1)
    if groups.get(f"{prefix}year"):
        return date(int(groups[f"{prefix}year"]), 12 if end else 1, 1)
    return None


def _months_between(start: date, end: date) -> int:
    """Число месяцев между датами, включая месяц окончания."""
    return max(0, (end.year - start.year) * 12 + end.month - start.month + 1)


def _total_years(periods: Sequence[tuple[date, date]]) -> float:
    """Стаж по объединению периодов: параллельные места работы не суммируются дважды."""
    merged: list[list[date]] = []
    for start, end in sorted(periods):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    months = sum(_months_between(start, end) for start, end in merged)
    return round(months / 12 * 2) / 2


def _grade_from_years(years: float) -> str:
    """Грейд по стажу — те же пороги, что при разборе потребности."""
    if years >= 4:
        return "senior"
    if years >= 2:
        return "middle"
    if years >= 1:
        return "junior"
    return "intern"


def _split_header(header: str) -> tuple[str, str]:
    """Делит заголовок места работы на должность и компанию.

    Должность — часть со словами вроде «разработчик» или «engineer». Если подсказки
    нет, первой считается должность: так пишут чаще всего.
    """
    for separator in _SEPARATORS:
        if separator in header:
            left, right = (part.strip(" ,.—–-|") for part in header.split(separator, 1))
            if _ROLE_WORDS.search(right) and not _ROLE_WORDS.search(left):
                return right, left
            return left, right
    return header.strip(" ,.—–-|"), ""


def _range_only(line: str) -> bool:
    """Строка состоит только из периода: заголовок места работы тогда строкой выше."""
    match = _RANGE.search(line)
    if match is None:
        return False
    return not (line[: match.start()] + line[match.end() :]).strip(" ,.—–-|()")


def _experiences(
    lines: Sequence[str], today: date
) -> tuple[list[ResumeExperience], list[tuple[date, date]]]:
    """Места работы по строкам с диапазоном дат и стаж по их периодам."""
    experiences = []
    periods = []
    for index, line in enumerate(lines):
        match = _RANGE.search(line)
        if not match:
            continue
        start = _date(match, "a", end=False)
        end = _date(match, "b", end=True)
        if start is None:
            continue
        finish = end or today
        if finish < start or start > today:
            continue
        periods.append((start, min(finish, today)))
        header = (line[: match.start()] + line[match.end() :]).strip(" ,.—–-|()")
        if not header and index > 0:
            header = lines[index - 1]
        position, company = _split_header(header)
        description_lines = []
        stop = None
        for following in lines[index + 1 :]:
            if _RANGE.search(following) or _SECTION.match(following):
                stop = following
                break
            description_lines.append(following)
        if stop is not None and description_lines and _range_only(stop):
            description_lines = description_lines[:-1]
        experiences.append(
            ResumeExperience(
                position=position[:200],
                company_name=company[:200],
                started_on=start,
                ended_on=end,
                description=" ".join(description_lines)[:MAX_DESCRIPTION],
            )
        )
    return experiences, periods


def _full_name(lines: Sequence[str]) -> tuple[str | None, str | None]:
    """ФИО: строка «ФИО: …» или первая строка шапки из двух-трёх слов с заглавной."""
    for line in lines[:HEADER_LINES]:
        labelled = _NAME_LABEL.match(line)
        candidate = labelled.group(1).strip() if labelled else line.strip()
        if _NAME.match(candidate) and not _ROLE_WORDS.search(candidate):
            return candidate, line.strip()
    return None, None


def parse_resume_text(text: str, catalog: Sequence[CatalogSkill], today: date) -> ParsedResume:
    """Разбирает текст резюме в черновик профиля.

    Разбор работает на правилах и справочнике навыков, без внешних моделей: результат
    воспроизводим и работает офлайн. Это черновик, а не категория: кандидат проверяет
    поля перед сохранением, а категорию по-прежнему определяют опрос и тест (ТЗ §2).
    """
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    flat = "\n".join(lines)
    parsed = ParsedResume()

    parsed.full_name, name_evidence = _full_name(lines)
    if name_evidence:
        parsed.evidence["full_name"] = name_evidence
    email = _EMAIL.search(flat)
    if email:
        parsed.email = email.group(0)
        parsed.evidence["email"] = email.group(0)
    phone = _PHONE.search(flat)
    if phone:
        digits = re.sub(r"\D", "", phone.group(0))
        parsed.phone = "+7" + digits[-10:]
        parsed.evidence["phone"] = phone.group(0)
    for telegram in _TELEGRAM.finditer(flat):
        handle = telegram.group(1)
        if parsed.email and handle.lower() in parsed.email.lower():
            continue
        parsed.telegram = f"@{handle}"
        parsed.evidence["telegram"] = telegram.group(0)
        break
    parsed.city, city_evidence = detect_city(flat)
    if city_evidence:
        parsed.evidence["city"] = city_evidence

    found = find_skills(flat, catalog)
    kinds = {skill.id: skill for skill in catalog}
    parsed.skills = [item for item in found if kinds[item.skill_id].kind is not SkillKind.SOFT]
    parsed.soft_skills = [
        kinds[item.skill_id].name for item in found if kinds[item.skill_id].kind is SkillKind.SOFT
    ]
    for role, pattern in _TEAM_ROLES:
        match = pattern.search(flat)
        if match:
            parsed.team_roles.append(role)
            parsed.evidence.setdefault("team_roles", match.group(0))

    parsed.experiences, periods = _experiences(lines, today)
    if periods:
        parsed.experience_years = _total_years(periods)
        parsed.evidence["experience_years"] = f"мест работы с датами: {len(periods)}"
    else:
        explicit = _EXPLICIT_YEARS.search(flat)
        if explicit:
            parsed.experience_years = float(explicit.group(1).replace(",", "."))
            parsed.evidence["experience_years"] = explicit.group(0)

    header = "\n".join(lines[:HEADER_LINES])
    mentions = grade_mentions(header)
    if mentions:
        parsed.grade_code, grade_evidence = mentions[-1]
        parsed.evidence["grade"] = grade_evidence
    elif parsed.experience_years is not None:
        parsed.grade_code = _grade_from_years(parsed.experience_years)
        parsed.evidence["grade"] = f"по стажу {parsed.experience_years:g} г."
    spec_code, _, spec_evidence = detect_specialization(flat, parsed.skills, catalog)
    parsed.specialization_code = spec_code
    if spec_evidence:
        parsed.evidence["specialization"] = spec_evidence
    return parsed
