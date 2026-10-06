import hashlib
import hmac
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from random import Random
from typing import Any

from app.models.assessment import ItemFamilyStatus, ResponseFormat

OPTION_KEYS = ("a", "b", "c", "d")
NOMINAL_DIFFICULTY = {"intern": -1.6, "junior": -0.7, "middle": 0.3, "senior": 1.2}
CHOICE_GUESSING = 0.2


class GeneratorError(RuntimeError):
    """Генератор не смог собрать корректный экземпляр (например, не хватило вариантов ответа)."""


@dataclass(frozen=True, slots=True)
class DataTable:
    """Таблица в условии задания: строки SQL-таблицы, выборка, DataFrame."""

    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]

    def as_payload(self) -> dict[str, Any]:
        """Представление для клиента."""
        return {
            "title": self.title,
            "columns": list(self.columns),
            "rows": [list(r) for r in self.rows],
        }


@dataclass(frozen=True, slots=True)
class PythonCheck:
    """Проверка для тестов: код печатает ровно правильный вариант ответа."""

    code: str


@dataclass(frozen=True, slots=True)
class SqliteCheck:
    """Проверка для тестов: запрос в SQLite возвращает правильное число."""

    setup: tuple[str, ...]
    query: str


@dataclass(frozen=True, slots=True)
class NodeCheck:
    """Проверка для тестов: JavaScript-код в Node.js печатает правильный вариант."""

    code: str


type CheckSpec = PythonCheck | SqliteCheck | NodeCheck


@dataclass(frozen=True, slots=True)
class GeneratedItem:
    """Готовый экземпляр задания до раскладки вариантов по ключам a–d."""

    prompt: str
    response_format: ResponseFormat
    answer: dict[str, Any]
    options: tuple[str, ...] = ()
    code: str | None = None
    code_language: str | None = None
    tables: tuple[DataTable, ...] = ()
    input_hint: str | None = None
    unit: str | None = None
    explanation: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    check: CheckSpec | None = None

    def client_payload(self) -> dict[str, Any]:
        """Часть экземпляра, которую видит кандидат. Ключа ответа здесь нет."""
        payload: dict[str, Any] = {
            "prompt": self.prompt,
            "response_format": self.response_format.value,
            "code": self.code,
            "code_language": self.code_language,
            "tables": [table.as_payload() for table in self.tables],
            "input_hint": self.input_hint,
            "unit": self.unit,
        }
        if self.response_format is ResponseFormat.SINGLE_CHOICE:
            payload["options"] = [
                {"key": key, "text": text}
                for key, text in zip(OPTION_KEYS, self.options, strict=True)
            ]
        return payload


type Generator = Callable[[Random], GeneratedItem]


@dataclass(frozen=True, slots=True)
class FamilySpec:
    """Описание семейства: метаданные для банка заданий и функция-генератор."""

    code: str
    title: str
    competency: str
    nominal_grade: str
    response_format: ResponseFormat
    time_limit_sec: int
    discrimination: float
    difficulty_offset: float
    status: ItemFamilyStatus
    generate: Generator

    @property
    def prior_difficulty(self) -> float:
        """Начальная сложность b: номинальный грейд эксперта плюс поправка семейства."""
        return NOMINAL_DIFFICULTY[self.nominal_grade] + self.difficulty_offset

    @property
    def guessing(self) -> float:
        """Вероятность угадать: для выбора из четырёх вариантов около 0,2, для числа — ноль."""
        return CHOICE_GUESSING if self.response_format is ResponseFormat.SINGLE_CHOICE else 0.0


REGISTRY: dict[str, FamilySpec] = {}


def family(
    code: str,
    *,
    title: str,
    competency: str,
    grade: str,
    response_format: ResponseFormat,
    time_limit: int = 90,
    discrimination: float = 1.2,
    difficulty_offset: float = 0.0,
    status: ItemFamilyStatus = ItemFamilyStatus.ACTIVE,
) -> Callable[[Generator], Generator]:
    """Регистрирует генератор как семейство заданий банка."""
    if grade not in NOMINAL_DIFFICULTY:
        raise ValueError(f"Неизвестный номинальный грейд {grade!r} у семейства {code}")

    def register(generator: Generator) -> Generator:
        """Добавляет семейство в реестр; повторный код — ошибка разработчика."""
        if code in REGISTRY:
            raise ValueError(f"Семейство {code} зарегистрировано дважды")
        REGISTRY[code] = FamilySpec(
            code=code,
            title=title,
            competency=competency,
            nominal_grade=grade,
            response_format=response_format,
            time_limit_sec=time_limit,
            discrimination=discrimination,
            difficulty_offset=difficulty_offset,
            status=status,
            generate=generator,
        )
        return generator

    return register


def single_choice(
    rng: Random,
    *,
    prompt: str,
    correct: str,
    distractors: Iterable[str],
    code: str | None = None,
    code_language: str | None = None,
    tables: Sequence[DataTable] = (),
    explanation: str = "",
    params: dict[str, Any] | None = None,
    check: CheckSpec | None = None,
) -> GeneratedItem:
    """Собирает задание с выбором одного варианта из четырёх.

    Дистракторы приходят от генератора, построенные из типичных ошибок. Совпадающие
    с правильным ответом и дубли отбрасываются, из оставшихся берутся первые три.
    Порядок вариантов перемешивается тем же генератором случайных чисел, поэтому
    экземпляр полностью определяется seed.
    """
    unique: list[str] = []
    for option in distractors:
        if option != correct and option not in unique:
            unique.append(option)
    if len(unique) < len(OPTION_KEYS) - 1:
        raise GeneratorError(f"Недостаточно различимых дистракторов для «{correct}»: {unique}")

    options = [correct, *unique[: len(OPTION_KEYS) - 1]]
    rng.shuffle(options)
    correct_key = OPTION_KEYS[options.index(correct)]
    return GeneratedItem(
        prompt=prompt,
        response_format=ResponseFormat.SINGLE_CHOICE,
        answer={"kind": "choice", "correct": correct_key, "text": correct},
        options=tuple(options),
        code=code,
        code_language=code_language,
        tables=tuple(tables),
        explanation=explanation,
        params=params or {},
        check=check,
    )


def numeric(
    *,
    prompt: str,
    value: float,
    tolerance: float = 0.0,
    input_hint: str = "Целое число",
    unit: str | None = None,
    code: str | None = None,
    code_language: str | None = None,
    tables: Sequence[DataTable] = (),
    explanation: str = "",
    params: dict[str, Any] | None = None,
    check: CheckSpec | None = None,
) -> GeneratedItem:
    """Собирает задание с числовым ответом.

    Числовой ответ почти не угадывается: у таких заданий параметр c равен нулю, и
    они хорошо разделяют кандидатов вокруг своей сложности.
    """
    return GeneratedItem(
        prompt=prompt,
        response_format=ResponseFormat.NUMERIC,
        answer={"kind": "numeric", "value": float(value), "tolerance": float(tolerance)},
        code=code,
        code_language=code_language,
        tables=tuple(tables),
        input_hint=input_hint,
        unit=unit,
        explanation=explanation,
        params=params or {},
        check=check,
    )


def instance_seed(secret: str, session_salt: str, position: int, family_code: str) -> int:
    """Seed экземпляра: HMAC от секрета сервера, соли сессии, позиции и семейства.

    Без секрета seed не предсказать, поэтому заранее подготовить ответы под
    конкретную сессию нельзя. Зная секрет, экземпляр можно воспроизвести при
    разборе апелляции.
    """
    message = f"{session_salt}:{position}:{family_code}".encode()
    digest = hmac.new(secret.encode(), message, hashlib.sha256).digest()
    return int.from_bytes(digest[:7], "big")


def generate_instance(spec: FamilySpec, seed: int) -> GeneratedItem:
    """Генерирует экземпляр семейства по seed (детерминированно)."""
    return spec.generate(Random(seed))


def format_number(value: float, digits: int = 2) -> str:
    """Число в русской записи без лишних нулей: 12,5 вместо 12.50."""
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")
