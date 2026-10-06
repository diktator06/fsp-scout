import re
from typing import Any

_NUMBER = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")
_SPACES = re.compile(r"[\s   ]+")
_TRAILING_UNIT = re.compile(r"[^\d]+$")
_MAX_ANSWER_LENGTH = 64


def parse_number(raw: str) -> float | None:
    """Разбирает числовой ответ так, как его пишут люди.

    Принимаются «12,5» и «12.5», пробелы между разрядами («1 200») и единица
    измерения в конце («80 %», «43,2 мин»). Выражения и несколько чисел не
    принимаются: ответ должен быть одним числом.
    """
    text = _TRAILING_UNIT.sub("", _SPACES.sub("", raw.strip())[:_MAX_ANSWER_LENGTH])
    if not _NUMBER.match(text):
        return None
    return float(text.replace(",", "."))


def score_answer(answer_key: dict[str, Any], raw: str) -> float:
    """Оценивает ответ: 1 — верно, 0 — неверно или не разобран.

    Для выбора сравнивается ключ варианта, для числа — попадание в допуск. Допуск
    задаёт генератор: для процентов это 0,1 п. п., для целых — точное совпадение.
    """
    if answer_key.get("kind") == "choice":
        return 1.0 if raw.strip().lower() == str(answer_key["correct"]) else 0.0
    value = parse_number(raw)
    if value is None:
        return 0.0
    expected = float(answer_key["value"])
    tolerance = float(answer_key.get("tolerance", 0.0))
    return 1.0 if abs(value - expected) <= tolerance + 1e-9 else 0.0
