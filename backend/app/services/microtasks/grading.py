from typing import Any

from app.core.exceptions import DomainValidationError

ANSWER_NUMBER = "number"
ANSWER_CHOICE = "choice"


def _parse_number(raw: str) -> float:
    """Число из ответа: допускаются запятая, пробелы-разделители и знак минуса «−»."""
    cleaned = raw.strip().replace(" ", "").replace(" ", "").replace(",", ".")
    cleaned = cleaned.replace("−", "-")
    try:
        return float(cleaned)
    except ValueError as error:
        raise DomainValidationError(
            "Ответ должен быть числом", details={"field": "answer"}
        ) from error


def auto_grade(answer_key: dict[str, Any], answer: str) -> float:
    """Проверка задачи «решить» по эталону: 1 — верно, 0 — неверно.

    Для числа учитывается допуск, заданный работодателем. Для выбора ответом
    служит номер варианта, начиная с нуля. Эталон кандидату не показывается.
    """
    kind = answer_key.get("kind")
    if kind == ANSWER_NUMBER:
        value = _parse_number(answer)
        expected = float(answer_key["value"])
        tolerance = float(answer_key.get("tolerance", 0.0))
        return 1.0 if abs(value - expected) <= tolerance + 1e-9 else 0.0
    if kind == ANSWER_CHOICE:
        try:
            chosen = int(answer.strip())
        except ValueError as error:
            raise DomainValidationError(
                "Выберите один из вариантов", details={"field": "answer"}
            ) from error
        return 1.0 if chosen == int(answer_key["correct"]) else 0.0
    raise DomainValidationError("У задачи нет эталона для автопроверки")


def rating_to_score(rating: int) -> float:
    """Оценка работодателя 1–5 в балл 0..1: 1 → 0, 3 → 0,5, 5 → 1."""
    return (rating - 1) / 4
