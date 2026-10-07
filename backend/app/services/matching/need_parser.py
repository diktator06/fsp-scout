import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.models.dictionary import SkillKind


@dataclass(frozen=True, slots=True)
class CatalogSkill:
    """Навык справочника в форме, удобной для поиска в тексте."""

    id: int
    slug: str
    name: str
    kind: SkillKind
    aliases: tuple[str, ...]
    specialization_weights: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CatalogGrade:
    """Грейд справочника."""

    id: int
    code: str
    rank: int


@dataclass(frozen=True, slots=True)
class FoundSkill:
    """Навык, найденный в тексте потребности."""

    skill_id: int
    importance: str
    evidence: str


@dataclass
class ParsedNeed:
    """Структура, извлечённая из свободного текста.

    Каждое поле сопровождается фрагментом текста, по которому оно найдено: работодатель
    видит, откуда взялось значение, и правит его, прежде чем сохранить потребность.
    """

    title: str | None = None
    specialization_code: str | None = None
    specialization_confidence: float = 0.0
    grade_codes: list[str] = field(default_factory=list)
    experience_years_min: float | None = None
    skills: list[FoundSkill] = field(default_factory=list)
    work_formats: list[str] = field(default_factory=list)
    city: str | None = None
    salary_from: int | None = None
    salary_to: int | None = None
    salary_gross: bool | None = None
    evidence: dict[str, str] = field(default_factory=dict)


SPECIALIZATION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "backend": ("бэкенд", "бекенд", "backend", "back-end", "серверн", "микросервис"),
    "frontend": ("фронтенд", "frontend", "front-end", "вёрстк", "верстк", "интерфейс", "spa"),
    "data_analytics": (
        "аналитик данных",
        "data analyst",
        "продуктовый аналитик",
        "bi-аналитик",
        "дашборд",
        "отчётност",
        "отчетност",
    ),
    "ml": (
        "machine learning",
        "data scientist",
        "ml-инженер",
        "ml engineer",
        "машинного обучения",
        "нейросет",
        "моделей",
    ),
    "qa": ("тестировщик", "qa", "тестирован", "автотест", "quality assurance"),
    "devops": ("devops", "sre", "инфраструктур", "эксплуатац", "платформенн"),
    "mobile": ("мобильн", "mobile", "ios", "android", "приложение для смартфон"),
}

_GRADE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("intern", re.compile(r"\b(intern|стаж[её]р\w*|практикант\w*)\b", re.IGNORECASE)),
    ("junior", re.compile(r"\b(junior|джун\w*|младш\w+)\b", re.IGNORECASE)),
    ("middle", re.compile(r"\b(middle|мидл\w*)\b", re.IGNORECASE)),
    (
        "senior",
        re.compile(r"\b(senior|сеньор\w*|синьор\w*|старш\w+|ведущ\w+|lead|лид)\b", re.IGNORECASE),
    ),
)

_EXPERIENCE = re.compile(
    r"опыт\w*[^.\n]{0,40}?(?:от|не менее|более|больше|минимум)\s*"
    r"(\d+(?:[.,]\d)?)\s*\+?\s*(?:год|лет|г\.)",
    re.IGNORECASE,
)

_NICE_MARKERS = (
    "будет плюсом",
    "плюсом будет",
    "будет преимуществом",
    "преимуществом",
    "желательно",
    "приветствуется",
    "nice to have",
    "как плюс",
    "хорошо, если",
    "хорошо если",
)
_MUST_MARKERS = ("требования", "обязательно", "необходимо", "нужно", "ищем", "must", "стек")

_FORMATS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("remote", re.compile(r"удал[её]нн?\w*|удал[её]нк\w*|remote|дистанц\w*", re.IGNORECASE)),
    ("hybrid", re.compile(r"гибрид\w*|hybrid", re.IGNORECASE)),
    ("office", re.compile(r"\bофис\w*|office|on-?site", re.IGNORECASE)),
)

_OFFICE_LOCATION = re.compile(r"офис\w*\s+в\s+[А-ЯЁ]")

_CITIES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in (
        ("Москва", r"\bмоскв\w*|\bmoscow"),
        ("Санкт-Петербург", r"санкт-петербург\w*|\bпетербург\w*|\bспб\b|\bпитер\w*"),
        ("Казань", r"\bказан\w*"),
        ("Иннополис", r"\bиннополис\w*"),
        ("Новосибирск", r"\bновосибирск\w*"),
        ("Екатеринбург", r"\bекатеринбург\w*"),
        ("Нижний Новгород", r"нижн\w+ новгород\w*"),
        ("Самара", r"\bсамар\w*"),
        ("Ростов-на-Дону", r"ростов\w*"),
        ("Краснодар", r"\bкраснодар\w*"),
        ("Томск", r"\bтомск\w*"),
        ("Пермь", r"\bперм[ьи]\w*"),
        ("Воронеж", r"\bворонеж\w*"),
        ("Уфа", r"\bуф[аеы]\b"),
        ("Челябинск", r"\bчелябинск\w*"),
        ("Красноярск", r"\bкрасноярск\w*"),
        ("Владивосток", r"\bвладивосток\w*"),
        ("Калининград", r"\bкалининград\w*"),
        ("Тюмень", r"\bтюмен\w*"),
        ("Омск", r"\bомск\w*"),
    )
)

_AMOUNT = r"(\d{1,3}(?:[\s ]\d{3})+|\d+(?:[.,]\d+)?)"
_UNIT = r"(тыс\.?|т\.?\s?р\.?|k|к|млн)?"
_SALARY_RANGE = re.compile(
    rf"{_AMOUNT}\s*{_UNIT}\s*(?:₽|руб\.?|р\.)?\s*(?:-|–|—|до)\s*{_AMOUNT}\s*{_UNIT}",
    re.IGNORECASE,
)
_SALARY_FROM = re.compile(rf"\bот\s+{_AMOUNT}\s*{_UNIT}", re.IGNORECASE)
_SALARY_TO = re.compile(rf"\bдо\s+{_AMOUNT}\s*{_UNIT}", re.IGNORECASE)
_SALARY_CONTEXT = re.compile(
    r"зарплат|вилк|оклад|доход|компенсац|₽|руб|net|gross|на руки|ндфл|тыс|\d\s?[kк]\b",
    re.IGNORECASE,
)
_NET = re.compile(r"на руки|\bnet\b|нетто|чистыми|после вычета", re.IGNORECASE)
_GROSS = re.compile(
    r"\bgross\b|гросс|до вычета|до ндфл|брутто|с учётом ндфл|с учетом ндфл", re.IGNORECASE
)


def _amount(raw: str, unit: str | None) -> int:
    """Сумма в рублях: «250» с «тыс.» или без единицы → 250 000, «1,2 млн» → 1 200 000."""
    value = float(raw.replace(" ", "").replace(" ", "").replace(",", "."))
    unit = (unit or "").lower()
    if unit.startswith("млн"):
        value *= 1_000_000
    elif unit or value < 1000:
        value *= 1000
    return round(value)


def _clauses(text: str) -> list[tuple[str, str]]:
    """Разбивает текст на фразы и помечает каждую как обязательную или желательную.

    Заголовок «Будет плюсом:» переключает режим для следующих строк списка, пока не
    встретится другой заголовок. Маркер внутри фразы действует только на неё.
    """
    result = []
    section_mode = "must"
    for line in text.splitlines():
        stripped = line.strip(" \t•*-–—·")
        if not stripped:
            continue
        lowered = stripped.lower()
        is_heading = stripped.endswith(":") and len(stripped) < 60
        if is_heading:
            if any(marker in lowered for marker in _NICE_MARKERS):
                section_mode = "nice"
            elif any(marker in lowered for marker in _MUST_MARKERS):
                section_mode = "must"
        for clause in re.split(r"(?<=[.;!?])\s+", stripped):
            clause_lower = clause.lower()
            mode = "nice" if any(m in clause_lower for m in _NICE_MARKERS) else section_mode
            result.append((clause, mode))
    return result


def _skill_patterns(skill: CatalogSkill) -> list[tuple[re.Pattern[str], str]]:
    """Шаблоны поиска навыка: название, slug и алиасы.

    Однобуквенные имена (C, R) пропускаются: в обычном тексте они дают ложные
    совпадения. Двухбуквенные (Go, JS, TS) ищутся только с заглавной буквы, чтобы
    «go» в английской фразе не превратилось в язык Go.
    """
    variants = {skill.name, skill.slug, *skill.aliases}
    patterns = []
    for variant in sorted(variants, key=len, reverse=True):
        cleaned = variant.strip()
        if len(cleaned) < 2:
            continue
        body = re.escape(cleaned).replace(r"\ ", r"[\s-]")
        boundary = rf"(?<![\w+#.]){body}(?![\w+#])"
        if len(cleaned) == 2:
            for form in {cleaned.upper(), cleaned.capitalize()}:
                patterns.append((re.compile(rf"(?<![\w+#.]){re.escape(form)}(?![\w+#])"), form))
        else:
            patterns.append((re.compile(boundary, re.IGNORECASE), cleaned))
    return patterns


def _find_skills(
    clauses: Sequence[tuple[str, str]], catalog: Sequence[CatalogSkill]
) -> list[FoundSkill]:
    """Навыки из текста. Совпавший фрагмент маскируется, чтобы «React Native» не дал ещё и React.

    Если навык упомянут и как обязательный, и как желательный, побеждает обязательный.
    """
    compiled = [(skill, _skill_patterns(skill)) for skill in catalog]
    compiled.sort(key=lambda item: max((len(form) for _, form in item[1]), default=0), reverse=True)
    found: dict[int, FoundSkill] = {}
    for clause, mode in clauses:
        masked = clause
        for skill, patterns in compiled:
            for pattern, _form in patterns:
                match = pattern.search(masked)
                if not match:
                    continue
                masked = (
                    masked[: match.start()]
                    + " " * (match.end() - match.start())
                    + masked[match.end() :]
                )
                importance = "nice" if skill.kind is SkillKind.SOFT else mode
                previous = found.get(skill.id)
                if previous is None or (previous.importance == "nice" and importance == "must"):
                    found[skill.id] = FoundSkill(
                        skill_id=skill.id, importance=importance, evidence=clause.strip()[:160]
                    )
                break
    return list(found.values())


def _detect_specialization(
    text: str, skills: Sequence[FoundSkill], catalog: Sequence[CatalogSkill]
) -> tuple[str | None, float, str | None]:
    """Специализация по ключевым словам и найденному стеку.

    Ключевое слово весит 2, каждый найденный навык добавляет свой вес типичности для
    специализации. Уверенность — доля лучшей специализации в сумме баллов.
    """
    lowered = text.lower()
    scores: dict[str, float] = {}
    evidence: dict[str, str] = {}
    for code, keywords in SPECIALIZATION_KEYWORDS.items():
        for keyword in keywords:
            if re.search(rf"(?<![\w-]){re.escape(keyword)}", lowered):
                scores[code] = scores.get(code, 0.0) + 2.0
                evidence.setdefault(code, keyword)
    by_id = {skill.id: skill for skill in catalog}
    for found in skills:
        weight_factor = 1.0 if found.importance == "must" else 0.5
        for code, weight in by_id[found.skill_id].specialization_weights.items():
            scores[code] = scores.get(code, 0.0) + weight * weight_factor
    if not scores:
        return None, 0.0, None
    best = max(scores, key=lambda code: scores[code])
    total = sum(scores.values())
    return best, round(scores[best] / total, 2), evidence.get(best)


def _detect_grades(text: str) -> tuple[list[str], str | None, float | None]:
    """Грейды из явных слов (Middle/Senior) или из требуемого стажа."""
    codes = []
    evidence = None
    for code, pattern in _GRADE_PATTERNS:
        match = pattern.search(text)
        if match:
            codes.append(code)
            evidence = evidence or match.group(0)
    years = None
    experience = _EXPERIENCE.search(text)
    if experience:
        years = float(experience.group(1).replace(",", "."))
        if not codes:
            evidence = experience.group(0)
            if years >= 4:
                codes = ["senior"]
            elif years >= 2:
                codes = ["middle"]
            elif years >= 1:
                codes = ["junior"]
            else:
                codes = ["intern"]
    return codes, evidence, years


def _detect_salary(text: str) -> tuple[int | None, int | None, str | None]:
    """Вилка «от–до» в рублях. Числа без денежного контекста рядом не считаются вилкой."""
    for line in text.splitlines():
        if not _SALARY_CONTEXT.search(line):
            continue
        ranged = _SALARY_RANGE.search(line)
        if ranged:
            left_unit = ranged.group(2) or ranged.group(4)
            low = _amount(ranged.group(1), left_unit)
            high = _amount(ranged.group(3), ranged.group(4))
            if 10_000 <= low <= high <= 10_000_000:
                return low, high, ranged.group(0).strip()
        low_match = _SALARY_FROM.search(line)
        high_match = _SALARY_TO.search(line)
        only_low = _amount(low_match.group(1), low_match.group(2)) if low_match else None
        only_high = _amount(high_match.group(1), high_match.group(2)) if high_match else None
        if only_low or only_high:
            fragment = " ".join(m.group(0) for m in (low_match, high_match) if m)
            return only_low, only_high, fragment.strip()
    return None, None, None


def _title(text: str) -> str | None:
    """Первая строка как название, если она похожа на заголовок."""
    for line in text.splitlines():
        stripped = line.strip(" \t•*-–—#")
        if stripped:
            return stripped[:120] if len(stripped) <= 120 and not stripped.endswith(":") else None
    return None


def parse_need_text(
    text: str,
    catalog: Sequence[CatalogSkill],
    grades: Sequence[CatalogGrade],
) -> ParsedNeed:
    """Разбирает свободное описание потребности в структуру.

    Разбор работает на правилах и справочнике навыков, без внешних моделей: результат
    воспроизводим и объясним. Это черновик для работодателя, а не окончательное
    решение, — он проверяет и правит поля перед сохранением. «Гибрид, офис в Казани»
    — это гибрид с офисом в Казани, а не два формата сразу.
    """
    parsed = ParsedNeed(title=_title(text))
    clauses = _clauses(text)
    parsed.skills = _find_skills(clauses, catalog)

    code, confidence, spec_evidence = _detect_specialization(text, parsed.skills, catalog)
    parsed.specialization_code = code
    parsed.specialization_confidence = confidence
    if spec_evidence:
        parsed.evidence["specialization"] = spec_evidence

    known_grades = {grade.code for grade in grades}
    grade_codes, grade_evidence, years = _detect_grades(text)
    parsed.grade_codes = [code for code in grade_codes if code in known_grades]
    parsed.experience_years_min = years
    if grade_evidence:
        parsed.evidence["grades"] = grade_evidence

    for code_format, pattern in _FORMATS:
        match = pattern.search(text)
        if match:
            parsed.work_formats.append(code_format)
            parsed.evidence.setdefault("work_formats", match.group(0))
    if "hybrid" in parsed.work_formats and _OFFICE_LOCATION.search(text):
        parsed.work_formats.remove("office")

    for city, pattern in _CITIES:
        match = pattern.search(text)
        if match:
            parsed.city = city
            parsed.evidence["city"] = match.group(0)
            break

    low, high, salary_evidence = _detect_salary(text)
    parsed.salary_from, parsed.salary_to = low, high
    if salary_evidence:
        parsed.evidence["salary"] = salary_evidence
    if _NET.search(text):
        parsed.salary_gross = False
    elif _GROSS.search(text):
        parsed.salary_gross = True
    return parsed
