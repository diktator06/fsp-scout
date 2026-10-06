from random import Random

from app.models.assessment import ResponseFormat
from app.services.assessment.item_generators.base import (
    GeneratedItem,
    PythonCheck,
    family,
    numeric,
    single_choice,
)

_PROMPT_OUTPUT = "Что выведет программа?"
_CHOICE = ResponseFormat.SINGLE_CHOICE
_NUMERIC = ResponseFormat.NUMERIC


@family(
    "py.list_slicing",
    title="Срезы списков с шагом",
    competency="python_core",
    grade="intern",
    response_format=_CHOICE,
    time_limit=75,
    discrimination=1.1,
)
def list_slicing(rng: Random) -> GeneratedItem:
    """Срез с шагом: проверяет, что граница stop не включается и шаг считается от start."""
    size = rng.randint(8, 10)
    values = rng.sample(range(10, 99), size)
    start = rng.randint(1, 3)
    stop = rng.randint(size - 3, size - 1)
    step = rng.choice([2, 3])
    code = f"items = {values}\nprint(items[{start}:{stop}:{step}])"
    return single_choice(
        rng,
        prompt=_PROMPT_OUTPUT,
        code=code,
        code_language="python",
        correct=str(values[start:stop:step]),
        distractors=[
            str(values[start : stop + 1 : step]),
            str(values[start - 1 : stop : step]),
            str(values[start:stop]),
            str(values[start + 1 : stop : step]),
            str(values[start - 1 : stop + 1 : step]),
        ],
        params={"start": start, "stop": stop, "step": step},
        check=PythonCheck(code),
    )


@family(
    "py.floor_division",
    title="Целочисленное деление отрицательных чисел",
    competency="python_core",
    grade="intern",
    response_format=_CHOICE,
    time_limit=75,
    discrimination=1.3,
    difficulty_offset=0.3,
)
def floor_division(rng: Random) -> GeneratedItem:
    """`//` и `%` в Python округляют вниз, а не к нулю, как в C или Java.

    Делимое или делитель всегда отрицательны и не делятся нацело: иначе «округление
    к нулю» случайно дало бы верный ответ.
    """
    while True:
        dividend = rng.randint(7, 47)
        divisor = rng.randint(3, 9)
        if dividend % divisor:
            break
    if rng.random() < 0.5:
        dividend = -dividend
    else:
        divisor = -divisor
    code = f"a, b = {dividend}, {divisor}\nprint(a // b, a % b)"
    truncated = int(dividend / divisor)
    truncated_rest = dividend - divisor * truncated
    return single_choice(
        rng,
        prompt=_PROMPT_OUTPUT,
        code=code,
        code_language="python",
        correct=f"{dividend // divisor} {dividend % divisor}",
        distractors=[
            f"{truncated} {truncated_rest}",
            f"{dividend // divisor} {truncated_rest}",
            f"{truncated} {dividend % divisor}",
            f"{-(abs(dividend) // abs(divisor))} {abs(dividend) % abs(divisor)}",
        ],
        params={"a": dividend, "b": divisor},
        check=PythonCheck(code),
    )


@family(
    "py.dict_comprehension",
    title="Совпадающие ключи в dict comprehension",
    competency="python_core",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=100,
)
def dict_comprehension(rng: Random) -> GeneratedItem:
    """При повторе ключа в dict comprehension остаётся последнее значение."""
    modulo = rng.randint(3, 5)
    values = rng.sample(range(1, 60), rng.randint(6, 8))
    code = (
        f"values = {values}\n"
        f"by_rest = {{x % {modulo}: x for x in values}}\n"
        "print(sum(by_rest.values()))"
    )
    by_rest = {x % modulo: x for x in values}
    return numeric(
        prompt=_PROMPT_OUTPUT,
        value=sum(by_rest.values()),
        code=code,
        code_language="python",
        params={"modulo": modulo},
        check=PythonCheck(code),
    )


@family(
    "py.mutable_default",
    title="Изменяемое значение по умолчанию",
    competency="python_core",
    grade="junior",
    response_format=_CHOICE,
    time_limit=90,
    discrimination=1.4,
)
def mutable_default(rng: Random) -> GeneratedItem:
    """Список по умолчанию создаётся один раз при определении функции и копит значения."""
    name = rng.choice(["collect", "remember", "track", "register"])
    calls = rng.randint(3, 4)
    values = rng.sample(range(1, 40), calls)
    lines = [f"def {name}(value, bucket=[]):", "    bucket.append(value)", "    return bucket", ""]
    lines += [f"{name}({value})" for value in values[:-1]]
    lines.append(f"print({name}({values[-1]}))")
    code = "\n".join(lines)
    return single_choice(
        rng,
        prompt=_PROMPT_OUTPUT,
        code=code,
        code_language="python",
        correct=str(values),
        distractors=[
            str([values[-1]]),
            str(values[:-1]),
            str(values[-2:]),
            str(list(reversed(values))),
        ],
        check=PythonCheck(code),
    )


@family(
    "py.generator_exhaustion",
    title="Повторный проход по генератору",
    competency="python_core",
    grade="middle",
    response_format=_CHOICE,
    time_limit=90,
    discrimination=1.3,
    difficulty_offset=-0.2,
)
def generator_exhaustion(rng: Random) -> GeneratedItem:
    """Генераторное выражение одноразовое: второй проход ничего не вернёт."""
    count = rng.randint(3, 6)
    expressions = {
        "x * x": lambda x: x * x,
        "x * 2": lambda x: x * 2,
        "x + 1": lambda x: x + 1,
        "x * 3": lambda x: x * 3,
    }
    expression = rng.choice(sorted(expressions))
    total = sum(expressions[expression](x) for x in range(count))
    code = (
        f"numbers = ({expression} for x in range({count}))\n"
        "first = sum(numbers)\n"
        "second = sum(numbers)\n"
        "print(first, second)"
    )
    return single_choice(
        rng,
        prompt=_PROMPT_OUTPUT,
        code=code,
        code_language="python",
        correct=f"{total} 0",
        distractors=[f"{total} {total}", f"0 {total}", f"{total} {total * 2}", "0 0"],
        check=PythonCheck(code),
    )


@family(
    "py.shallow_copy_aliasing",
    title="Умножение списка списков",
    competency="python_core",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=100,
    discrimination=1.5,
)
def shallow_copy_aliasing(rng: Random) -> GeneratedItem:
    """`[[0] * m] * n` создаёт n ссылок на один и тот же внутренний список."""
    rows = rng.randint(2, 4)
    cols = rng.randint(2, 4)
    row = rng.randrange(rows)
    col = rng.randrange(cols)
    value = rng.randint(2, 9)
    code = (
        f"grid = [[0] * {cols}] * {rows}\ngrid[{row}][{col}] = {value}\nprint(sum(map(sum, grid)))"
    )
    return numeric(
        prompt=_PROMPT_OUTPUT,
        value=value * rows,
        code=code,
        code_language="python",
        params={"rows": rows, "cols": cols},
        check=PythonCheck(code),
    )


@family(
    "py.closure_late_binding",
    title="Позднее связывание в замыканиях",
    competency="python_core",
    grade="middle",
    response_format=_CHOICE,
    time_limit=100,
    discrimination=1.6,
    difficulty_offset=0.2,
)
def closure_late_binding(rng: Random) -> GeneratedItem:
    """Лямбды в цикле видят переменную цикла по ссылке: все вернут её последнее значение."""
    count = rng.randint(3, 5)
    constant = rng.randint(2, 9)
    operator = rng.choice(["+", "*"])

    def apply(i: int) -> int:
        """Значение выражения лямбды для заданного i."""
        return i + constant if operator == "+" else i * constant

    code = (
        f"funcs = [lambda: i {operator} {constant} for i in range({count})]\n"
        "print([f() for f in funcs])"
    )
    return single_choice(
        rng,
        prompt=_PROMPT_OUTPUT,
        code=code,
        code_language="python",
        correct=str([apply(count - 1)] * count),
        distractors=[
            str([apply(i) for i in range(count)]),
            str([apply(count)] * count),
            str([apply(0)] * count),
            str([apply(i) for i in range(1, count + 1)]),
        ],
        check=PythonCheck(code),
    )


@family(
    "py.finally_mutation",
    title="return и finally с изменяемым объектом",
    competency="python_core",
    grade="middle",
    response_format=_CHOICE,
    time_limit=100,
    discrimination=1.3,
    difficulty_offset=0.4,
)
def finally_mutation(rng: Random) -> GeneratedItem:
    """`finally` выполняется после вычисления return, но меняет уже возвращаемый список."""
    first, second = rng.sample(range(1, 50), 2)
    name = rng.choice(["build", "prepare", "load"])
    code = (
        f"def {name}():\n"
        "    items = []\n"
        "    try:\n"
        f"        items.append({first})\n"
        "        return items\n"
        "    finally:\n"
        f"        items.append({second})\n"
        "\n"
        f"print({name}())"
    )
    return single_choice(
        rng,
        prompt=_PROMPT_OUTPUT,
        code=code,
        code_language="python",
        correct=str([first, second]),
        distractors=[str([first]), str([second]), str([second, first]), "None"],
        check=PythonCheck(code),
    )


@family(
    "py.mro_super",
    title="Порядок разрешения методов (MRO) и super()",
    competency="python_core",
    grade="senior",
    response_format=_CHOICE,
    time_limit=150,
    discrimination=1.5,
)
def mro_super(rng: Random) -> GeneratedItem:
    """Ромбовидное наследование: super() идёт по C3-линеаризации, а не в глубину."""
    base, left, right, child = rng.sample(list("ABCDEFGKMNPRST"), 4)
    first_parent, second_parent = (left, right) if rng.random() < 0.5 else (right, left)
    prepend = rng.random() < 0.5

    def body(name: str) -> str:
        """Тело метода path для класса-наследника."""
        if prepend:
            return f'        return ["{name}"] + super().path()'
        return f'        return super().path() + ["{name}"]'

    code = "\n".join(
        [
            f"class {base}:",
            "    def path(self):",
            f'        return ["{base}"]',
            "",
            f"class {left}({base}):",
            "    def path(self):",
            body(left),
            "",
            f"class {right}({base}):",
            "    def path(self):",
            body(right),
            "",
            f"class {child}({first_parent}, {second_parent}):",
            "    def path(self):",
            body(child),
            "",
            f'print("".join({child}().path()))',
        ]
    )
    linearization = [child, first_parent, second_parent, base]
    depth_first = [child, first_parent, base, second_parent]
    swapped = [child, second_parent, first_parent, base]

    def render(order: list[str]) -> str:
        """Вывод программы для заданного порядка обхода."""
        return "".join(order if prepend else list(reversed(order)))

    return single_choice(
        rng,
        prompt=_PROMPT_OUTPUT,
        code=code,
        code_language="python",
        correct=render(linearization),
        distractors=[
            render(depth_first),
            render(swapped),
            "".join(reversed(render(linearization))),
            render([child, first_parent, base]),
        ],
        check=PythonCheck(code),
    )
