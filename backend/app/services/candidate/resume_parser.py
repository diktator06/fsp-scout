import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

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
MAX_ABOUT = 3000
HEADER_LINES = 12

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s-]*\d{2}[\s-]*\d{2}")
_TELEGRAM = re.compile(
    r"(?:t\.me/|telegram[:\s]+@?|tg[:\s]+@?|(?<![\w.])@)(?!https?\b|www\b)"
    r"([A-Za-z][A-Za-z0-9_]{4,31})",
    re.IGNORECASE,
)
_NAME_LABEL = re.compile(r"^(?:фио|имя)\s*[:—-]\s*(.+)$", re.IGNORECASE)
_NAME = re.compile(r"^([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)\s+([А-ЯЁ][а-яё]+)(?:\s+([А-ЯЁ][а-яё]+))?$")
_HEADER_WORDS = re.compile(
    r"^(?:резюме|профиль|контакты|опыт|навыки|образование|о себе)$", re.IGNORECASE
)
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
_SECTION_NAMES = (
    "образование",
    "навыки",
    "ключевые навыки",
    "о себе",
    "обо мне",
    "контакты",
    "языки",
    "знание языков",
    "курсы",
    "повышение квалификации, курсы",
    "повышение квалификации",
    "сертификаты",
    "электронные сертификаты",
    "тесты, экзамены",
    "проекты",
    "портфолио",
    "рекомендации",
    "дополнительная информация",
    "опыт вождения",
    "опыт работы",
    "желаемая должность и зарплата",
    "education",
    "skills",
    "about",
    "about me",
    "summary",
    "languages",
    "projects",
    "certifications",
    "licenses & certifications",
    "experience",
    "work experience",
    "courses",
)
_SECTION = re.compile(
    r"^(?:" + "|".join(re.escape(name) for name in _SECTION_NAMES) + r")(?:\s*[:—–-].*)?$",
    re.IGNORECASE,
)
_NON_WORK_SECTION = re.compile(
    r"^(?:образование|education|курсы|courses|повышение квалификации.*|сертификаты"
    r"|электронные сертификаты|certifications|licenses & certifications|тесты, экзамены)"
    r"(?:\s*[:—–-].*)?$",
    re.IGNORECASE,
)
_FOOTER = re.compile(
    r"резюме обновлено\s+\d|^(?:стр(?:аница)?\.?|page)\s*\d+\s*(?:из|of|/)\s*\d+$", re.IGNORECASE
)
_DATE_START = re.compile(
    r"^(?:" + _PRESENT + "|" + _MONTH_WORD + r"\s+(?:19|20)\d{2}|\d{1,2}[./](?:19|20)\d{2}"
    r"|(?:19|20)\d{2})",
    re.IGNORECASE,
)
_ANY_DATE = re.compile(
    _MONTH_WORD + r"\s+(?:19|20)\d{2}|\d{1,2}[./](?:19|20)\d{2}|(?:19|20)\d{2}", re.IGNORECASE
)
_DANGLING = re.compile(r"(?:[–—-]|\bпо|\bto)$", re.IGNORECASE)
_DURATION = re.compile(
    r"\(?\s*\d+\s*(?:год\w*|лет|years?|yrs?|мес\w*|months?|mos?)\b"
    r"(?:\s*(?:и|and)?\s*\d+\s*(?:мес\w*|months?|mos?)\b)?\s*\)?",
    re.IGNORECASE,
)
_BULLET = re.compile(r"^[•·▪◦‣●]\s*")
_SITE = re.compile(r"^(?:https?://|www\.)\S+$|^[\w-]+(?:\.[\w-]+)+(?:/\S*)?$", re.IGNORECASE)
_ABOUT = re.compile(
    r"^(?:о себе|обо мне|about me|about|summary)(?:\s*[:—–-]\s*|\s+|$)(.*)$", re.IGNORECASE
)
_DEGREE = re.compile(
    r"^(?:высшее(?:\s*\(.*\))?|неоконченное высшее|среднее(?:\s+(?:специальное|профессиональное))?"
    r"|бакалавр\w*|магистр\w*|специалист(?:итет)?|аспирант\w*|кандидат наук|доктор наук"
    r"|bachelor.*|master.*|ph\.?\s?d\.?|mba)$",
    re.IGNORECASE,
)
_YEAR_LINE = re.compile(r"^((?:19|20)\d{2})(?:\s+(.+))?$")
_INLINE_EDUCATION = re.compile(r"^(.{2,200}?),?\s+((?:19|20)\d{2})$")
_UNFINISHED = re.compile(r"(?:\b[А-ЯЁA-Z]\.|\bим\.|\bимени|\b(?:и|of|and|the))$")
_YEARS_IN_PARENS = re.compile(r"\((?:(?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2})\)")
_FORMAT_LINE = re.compile(
    r"^(?:формат работы|график работы|work (?:format|mode)|workplace)\s*:?\s*(.+)$", re.IGNORECASE
)
_FORMATS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("office", re.compile(r"на месте работодателя|офис|office|on-?site", re.IGNORECASE)),
    ("hybrid", re.compile(r"гибрид|hybrid", re.IGNORECASE)),
    ("remote", re.compile(r"удал[её]нн|remote", re.IGNORECASE)),
)
_RELOCATION = re.compile(
    r"(не\s+)?готов(?:а)?\s+к\s+переезду|переезд\s+(невозможен|возможен)"
    r"|(not\s+)?(?:open|willing)\s+to\s+relocat",
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


@dataclass(frozen=True, slots=True)
class ResumeEducation:
    """Учебное заведение из резюме — черновик для анкеты."""

    institution: str
    degree: str
    graduated_year: int | None


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
    about: str | None = None
    educations: list[ResumeEducation] = field(default_factory=list)
    work_formats: list[str] = field(default_factory=list)
    relocation_ready: bool | None = None
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


def _normalize_lines(text: str) -> list[str]:
    """Строки резюме без колонтитулов и с периодами, собранными в одну строку.

    Выгрузки hh.ru и других сервисов переносят период на две строки («Сентябрь
    2023 —» и «настоящее время») и повторяют на каждой странице «Резюме обновлено…».
    Без этой подготовки места работы не находятся, а колонтитул попадает в описание.
    """
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    merged: list[str] = []
    for line in lines:
        if not line or _FOOTER.search(line):
            continue
        previous = merged[-1] if merged else ""
        if (
            previous
            and _DANGLING.search(previous)
            and _ANY_DATE.search(previous)
            and _DATE_START.match(line)
        ):
            merged[-1] = f"{previous} {line}"
        else:
            merged.append(line)
    return merged


def _without_duration(text: str) -> str:
    """Строка без длительности вроде «3 года 2 месяца» или «(2 yrs 3 mos)»."""
    return _DURATION.sub(" ", text).strip(" ,.—–-|()·")


def _is_city(line: str) -> bool:
    """Строка — только город (иногда со станцией метро), как в шапке места работы."""
    city, evidence = detect_city(line)
    return bool(city) and len(line) <= 40 and evidence is not None


def _short_title(line: str) -> bool:
    """Строка похожа на заголовок — должность или компанию, а не на описание."""
    return (
        len(line) <= 80
        and not line.endswith((".", ";", ":"))
        and not _BULLET.match(line)
        and not _SECTION.match(line)
        and not _RANGE.search(line)
    )


def _block_header(lines: Sequence[str], body: Sequence[int]) -> tuple[str, str, list[int]]:
    """Должность и компания из строк после длительности — порядок hh.ru или SuperJob.

    hh.ru: компания, город, сайт, отрасль строками с «•», затем должность. SuperJob и
    похожие: сначала должность, потом компания — их различаем по словам вроде
    «разработчик» или «инженер».
    """
    if not body:
        return "", "", []
    first = lines[body[0]]
    second = lines[body[1]] if len(body) > 1 else ""
    if _ROLE_WORDS.search(first) and second and not _ROLE_WORDS.search(second):
        return first, second, list(body[:2])
    used = [body[0]]
    window = list(body[1:9])
    bullets = [index for index in window if _BULLET.match(lines[index])]
    position_index = None
    if bullets:
        used.extend(index for index in body if body[0] < index <= bullets[-1])
        position_index = next((index for index in body if index > bullets[-1]), None)
    else:
        for index in body[1:4]:
            if _is_city(lines[index]) or _SITE.match(lines[index]):
                used.append(index)
                continue
            position_index = index
            break
    position = ""
    if position_index is not None and _short_title(lines[position_index]):
        position = lines[position_index]
        used.append(position_index)
    return position, first, used


def _non_work_rows(lines: Sequence[str]) -> set[int]:
    """Строки разделов, где периоды — не работа: образование, курсы, сертификаты."""
    rows: set[int] = set()
    for index, line in enumerate(lines):
        if _NON_WORK_SECTION.match(line):
            rows.update(range(index, _section_end(lines, index + 1)))
    return rows


def _experiences(
    lines: Sequence[str], today: date
) -> tuple[list[ResumeExperience], list[tuple[date, date]]]:
    """Места работы по строкам с периодом и стаж по объединению периодов.

    Заголовок места работы ищется в трёх местах: в строке периода («Разработчик,
    Компания, 2019–2021»), в строках над ней (LinkedIn, Habr Career, свободный текст)
    или под ней после длительности (hh.ru, SuperJob). Строки заголовков не попадают в
    описание соседнего места работы.
    """
    outside = _non_work_rows(lines)
    starts = [
        (index, match)
        for index, line in enumerate(lines)
        if index not in outside and (match := _RANGE.search(line))
    ]
    consumed: set[int] = set()
    drafts = []
    for number, (index, match) in enumerate(starts):
        start = _date(match, "a", end=False)
        end = _date(match, "b", end=True)
        next_start = starts[number + 1][0] if number + 1 < len(starts) else len(lines)
        stop = next(
            (row for row in range(index + 1, next_start) if _SECTION.match(lines[row])),
            next_start,
        )
        body = list(range(index + 1, stop))
        line = lines[index]
        rest = _without_duration(line[: match.start()] + " " + line[match.end() :])
        position = company = ""
        if rest:
            position, company = _split_header(rest)
        elif body and not _without_duration(lines[body[0]]):
            consumed.add(body[0])
            position, company, used = _block_header(lines, body[1:])
            consumed.update(used)
        else:
            previous_stop = starts[number - 1][0] if number else -1
            above = [
                row
                for row in (index - 1, index - 2)
                if row > previous_stop and row not in consumed and _short_title(lines[row])
            ]
            if above and not _SECTION.match(lines[above[0]]):
                position, company = _split_header(lines[above[0]])
                consumed.add(above[0])
                if not company and len(above) > 1:
                    other = lines[above[1]]
                    if _ROLE_WORDS.search(other) and not _ROLE_WORDS.search(position):
                        position, company = other, position
                    else:
                        company = other
                    consumed.add(above[1])
        while body and (_is_city(lines[body[0]]) or not _without_duration(lines[body[0]])):
            consumed.add(body.pop(0))
        drafts.append((start, end, position, company, body))

    experiences = []
    periods = []
    for start, end, position, company, body in drafts:
        if start is None:
            continue
        finish = end or today
        if finish < start or start > today:
            continue
        periods.append((start, min(finish, today)))
        description = " ".join(lines[row] for row in body if row not in consumed)
        experiences.append(
            ResumeExperience(
                position=position[:200],
                company_name=company[:200],
                started_on=start,
                ended_on=end,
                description=description[:MAX_DESCRIPTION],
            )
        )
    return experiences, periods


def _section_end(lines: Sequence[str], start: int) -> int:
    """Индекс строки, где начинается следующий раздел резюме."""
    return next((row for row in range(start, len(lines)) if _SECTION.match(lines[row])), len(lines))


def _about(lines: Sequence[str]) -> tuple[str | None, str | None]:
    """Текст раздела «О себе». В hh.ru он начинается в той же строке, что и заголовок."""
    for index, line in enumerate(lines):
        match = _ABOUT.match(line)
        if match is None:
            continue
        parts = [match.group(1)] if match.group(1) else []
        parts.extend(lines[index + 1 : _section_end(lines, index + 1)])
        text = " ".join(part for part in parts if part).strip()
        if len(text) >= 20:
            return text[:MAX_ABOUT], line
    return None, None


def _educations(lines: Sequence[str]) -> list[ResumeEducation]:
    """Учебные заведения из раздела «Образование».

    Понимает три записи: hh.ru (год, уровень, вуз, факультет — каждое с новой
    строки), LinkedIn (вуз, затем «Степень · (2012 - 2016)») и короткую «КФУ, 2018».
    Повторы после разрыва страницы отбрасываются.
    """
    header = next(
        (
            index
            for index, line in enumerate(lines)
            if re.match(r"^(?:образование|education)(?:\s*[:—–-].*)?$", line, re.IGNORECASE)
        ),
        None,
    )
    if header is None:
        return []
    body = lines[header + 1 : _section_end(lines, header + 1)]
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for position, line in enumerate(body):
        year = _YEAR_LINE.match(line)
        if year and (year.group(2) is None or _DEGREE.match(year.group(2))):
            # Год и степень из соседних колонок PDF иногда приходят одной строкой.
            current = {"year": int(year.group(1)), "degree": year.group(2) or "", "lines": []}
            entries.append(current)
            continue
        parens = _YEARS_IN_PARENS.search(line)
        if parens and position > 0:
            degree = _YEARS_IN_PARENS.sub("", line).strip(" ·,")
            entries.append(
                {"year": int(parens.group(1)), "degree": degree, "lines": [body[position - 1]]}
            )
            current = None
            continue
        if current is None:
            inline = _INLINE_EDUCATION.match(line)
            if inline and not _DEGREE.match(line):
                entries.append(
                    {"year": int(inline.group(2)), "degree": "", "lines": [inline.group(1)]}
                )
            continue
        if _DEGREE.match(line) and not current["degree"] and not current["lines"]:
            current["degree"] = line
        else:
            current["lines"].append(line)
    result = []
    seen = set()
    for entry in entries:
        if not entry["lines"]:
            continue
        rows = list(entry["lines"])
        # Длинное название вуза переносится: «…им. Н.Э.» / «Баумана». Склеиваем, только
        # если первая строка явно оборвана (инициалы, «им.», союз) или вторая начинается
        # со строчной буквы — иначе вторая строка это специальность.
        while len(rows) > 1 and (_UNFINISHED.search(rows[0]) or rows[1][:1].islower()):
            rows[0:2] = [f"{rows[0]} {rows[1]}"]
        institution = rows[0].strip(" ,")[:300]
        details = ", ".join([entry["degree"], *rows[1:]]).strip(" ,")
        key = (institution.lower(), entry["year"])
        if len(institution) < 2 or key in seen:
            continue
        seen.add(key)
        result.append(ResumeEducation(institution, details[:200], entry["year"]))
    return result


def _work_formats(lines: Sequence[str]) -> tuple[list[str], str | None]:
    """Форматы работы из строки «Формат работы: …» или «График работы: …»."""
    for line in lines:
        match = _FORMAT_LINE.match(line)
        if match is None:
            continue
        formats = [code for code, pattern in _FORMATS if pattern.search(match.group(1))]
        if formats:
            return formats, line
    return [], None


def _relocation(flat: str) -> tuple[bool | None, str | None]:
    """Готовность к переезду: «Готов к переезду», «Не готов к переезду», «Переезд невозможен»."""
    match = _RELOCATION.search(flat)
    if match is None:
        return None, None
    negative = bool(match.group(1)) or (match.group(2) or "").lower() == "невозможен"
    negative = negative or bool(match.group(3))
    return not negative, match.group(0)


def _full_name(lines: Sequence[str]) -> tuple[str | None, str | None]:
    """ФИО: строка «ФИО: …» или первая строка шапки из двух-трёх слов с заглавной.

    В двухколоночных резюме крупное имя часто переносится по словам, и текст PDF
    приходит строками «Мария» и «Иванова». Поэтому строку шапки из одного слова
    пробуем склеить со следующей (и ещё одной — для отчества).
    """
    header = [line.strip() for line in lines[:HEADER_LINES]]
    for index, line in enumerate(header):
        labelled = _NAME_LABEL.match(line)
        candidate = labelled.group(1).strip() if labelled else line
        if _NAME.match(candidate) and not _ROLE_WORDS.search(candidate):
            return candidate, line
        if " " in line:
            continue
        for size in (2, 3):
            words = header[index : index + size]
            joined = " ".join(words)
            if (
                len(words) == size
                and _NAME.match(joined)
                and not _ROLE_WORDS.search(joined)
                and not any(_HEADER_WORDS.match(word) or detect_city(word)[0] for word in words)
            ):
                return joined, joined
    return None, None


def parse_resume_text(text: str, catalog: Sequence[CatalogSkill], today: date) -> ParsedResume:
    """Разбирает текст резюме в черновик профиля.

    Разбор работает на правилах и справочнике навыков, без внешних моделей: результат
    воспроизводим и работает офлайн. Это черновик, а не категория: кандидат проверяет
    поля перед сохранением, а категорию по-прежнему определяют опрос и тест (ТЗ §2).
    """
    lines = _normalize_lines(text)
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

    parsed.about, about_evidence = _about(lines)
    if about_evidence:
        parsed.evidence["about"] = about_evidence[:120]
    parsed.educations = _educations(lines)
    parsed.work_formats, formats_evidence = _work_formats(lines)
    if formats_evidence:
        parsed.evidence["work_formats"] = formats_evidence
    parsed.relocation_ready, relocation_evidence = _relocation(flat)
    if relocation_evidence:
        parsed.evidence["relocation_ready"] = relocation_evidence
    return parsed
