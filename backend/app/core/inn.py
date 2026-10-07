_WEIGHTS_10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_WEIGHTS_11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_WEIGHTS_12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _control(digits: list[int], weights: tuple[int, ...]) -> int:
    """Контрольная цифра ИНН: взвешенная сумма по модулю 11, затем по модулю 10."""
    return sum(digit * weight for digit, weight in zip(digits, weights, strict=False)) % 11 % 10


def is_valid_inn(inn: str) -> bool:
    """Проверка ИНН по контрольным цифрам (алгоритм ФНС).

    Десять цифр — организация, одна контрольная; двенадцать — ИП, две контрольные.
    Опечатку или выдуманный номер это ловит до любых внешних проверок: первый,
    самый дешёвый фильтр против фиктивных работодателей.
    """
    if not inn.isdigit() or len(inn) not in (10, 12):
        return False
    digits = [int(char) for char in inn]
    if len(digits) == 10:
        return _control(digits, _WEIGHTS_10) == digits[9]
    return (
        _control(digits, _WEIGHTS_11) == digits[10] and _control(digits, _WEIGHTS_12) == digits[11]
    )
