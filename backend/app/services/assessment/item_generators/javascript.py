from random import Random

from app.models.assessment import ResponseFormat
from app.services.assessment.item_generators.base import (
    GeneratedItem,
    NodeCheck,
    family,
    numeric,
    single_choice,
)

_CHOICE = ResponseFormat.SINGLE_CHOICE
_NUMERIC = ResponseFormat.NUMERIC
_PROMPT_OUTPUT = "Что выведет код?"
_PROMPT_ORDER = "В каком порядке будут выведены метки?"


@family(
    "js.array_pipeline",
    title="filter, map и reduce",
    competency="js_core",
    grade="intern",
    response_format=_NUMERIC,
    time_limit=90,
    discrimination=1.0,
)
def array_pipeline(rng: Random) -> GeneratedItem:
    """Цепочка методов массива: сначала фильтр, потом преобразование, потом свёртка."""
    values = rng.sample(range(1, 30), rng.randint(6, 8))
    divisor = rng.choice([2, 3])
    factor = rng.randint(2, 5)
    code = (
        f"const values = [{', '.join(map(str, values))}];\n"
        "const result = values\n"
        f"  .filter((x) => x % {divisor} === 0)\n"
        f"  .map((x) => x * {factor})\n"
        "  .reduce((sum, x) => sum + x, 0);\n"
        "console.log(result);"
    )
    return numeric(
        prompt=_PROMPT_OUTPUT,
        value=sum(x * factor for x in values if x % divisor == 0),
        code=code,
        code_language="javascript",
        check=NodeCheck(code),
    )


def _coercion_case(rng: Random) -> tuple[str, str, list[str]]:
    """Выражение с неявным приведением типов, правильный ответ и дистракторы."""
    a = rng.randint(2, 9)
    b = rng.randint(2, 9)
    kind = rng.choice(
        ["plus_string", "minus_string", "times_strings", "bool_plus", "null_plus", "array_plus"]
    )
    if kind == "plus_string":
        return f"'{a}' + {b}", f'"{a}{b}"', [str(a + b), "NaN", f'"{a} {b}"']
    if kind == "minus_string":
        return f"'{a + b}' - {b}", str(a), [f'"{a + b}{b}"', "NaN", f'"{a}"']
    if kind == "times_strings":
        return f"'{a}' * '{b}'", str(a * b), [f'"{a}{b}"', "NaN", f'"{a * b}"']
    if kind == "bool_plus":
        return f"{a} + true", str(a + 1), [f'"{a}true"', "NaN", str(a)]
    if kind == "null_plus":
        return f"null + {a}", str(a), ["NaN", f'"null{a}"', "0"]
    return f"[] + {a}", f'"{a}"', [str(a), "NaN", f"[{a}]"]


@family(
    "js.type_coercion",
    title="Неявное приведение типов",
    competency="js_core",
    grade="junior",
    response_format=_CHOICE,
    time_limit=60,
    discrimination=1.2,
)
def type_coercion(rng: Random) -> GeneratedItem:
    """`+` со строкой склеивает, остальные арифметические операторы приводят к числу."""
    expression, correct, distractors = _coercion_case(rng)
    code = f"const value = {expression};"
    check_code = code + "\nconsole.log(Number.isNaN(value) ? 'NaN' : JSON.stringify(value));"
    return single_choice(
        rng,
        prompt="Каким будет значение value? Строки показаны в двойных кавычках.",
        code=code,
        code_language="javascript",
        correct=correct,
        distractors=distractors,
        check=NodeCheck(check_code),
    )


@family(
    "js.var_let_timeout",
    title="var и let в цикле с setTimeout",
    competency="js_core",
    grade="junior",
    response_format=_CHOICE,
    time_limit=90,
    discrimination=1.4,
    difficulty_offset=0.2,
)
def var_let_timeout(rng: Random) -> GeneratedItem:
    """У var одна переменная на весь цикл, у let — своя на каждую итерацию."""
    count = rng.randint(3, 4)
    keyword = rng.choice(["var", "let"])
    code = f"for ({keyword} i = 0; i < {count}; i++) {{\n  setTimeout(() => console.log(i), 0);\n}}"
    shared = ", ".join([str(count)] * count)
    separate = ", ".join(str(i) for i in range(count))
    correct = shared if keyword == "var" else separate
    return single_choice(
        rng,
        prompt="Что будет выведено в консоль (значения перечислены через запятую)?",
        code=code,
        code_language="javascript",
        correct=correct,
        distractors=[
            separate if keyword == "var" else shared,
            ", ".join([str(count - 1)] * count),
            ", ".join(str(i) for i in range(1, count + 1)),
            ", ".join(["0"] * count),
        ],
        check=NodeCheck(
            "const out = [];\n"
            + code.replace("console.log(i)", "out.push(i)")
            + "\nsetTimeout(() => console.log(out.join(', ')), 5);"
        ),
    )


_EQUALITY_POOL = (
    ("0 == ''", True),
    ("null == undefined", True),
    ("NaN === NaN", False),
    ("'1' == 1", True),
    ("'1' === 1", False),
    ("[] == false", True),
    ("null == 0", False),
    ("[1] == 1", True),
    ("undefined == 0", False),
    ("'' == false", True),
    ("null === undefined", False),
    ("'0' == false", True),
)


@family(
    "js.equality_count",
    title="Нестрогое и строгое сравнение",
    competency="js_core",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.2,
    difficulty_offset=-0.3,
)
def equality_count(rng: Random) -> GeneratedItem:
    """Сколько выражений из пяти истинны: проверяет знание алгоритма `==`."""
    chosen = rng.sample(_EQUALITY_POOL, 5)
    code = "\n".join(f"console.log({expression});" for expression, _ in chosen)
    check_code = (
        "const results = [" + ", ".join(expression for expression, _ in chosen) + "];\n"
        "console.log(results.filter(Boolean).length);"
    )
    return numeric(
        prompt="Сколько строк выведут true?",
        value=sum(1 for _, result in chosen if result),
        code=code,
        code_language="javascript",
        check=NodeCheck(check_code),
    )


def _event_loop_program(rng: Random) -> tuple[str, list[str], dict[str, list[str]]]:
    """Случайная смесь синхронного кода, микрозадач и таймеров с метками в порядке программы."""
    labels = rng.sample(list("ABCDEFGHKM"), 5)
    kinds = [
        "sync",
        "micro",
        "macro",
        rng.choice(["sync", "micro"]),
        rng.choice(["sync", "micro", "macro"]),
    ]
    rng.shuffle(kinds)
    templates = {
        "sync": "console.log('{label}');",
        "micro": "Promise.resolve().then(() => console.log('{label}'));",
        "macro": "setTimeout(() => console.log('{label}'), 0);",
    }
    lines = [templates[kind].format(label=label) for label, kind in zip(labels, kinds, strict=True)]
    groups = {
        name: [label for label, kind in zip(labels, kinds, strict=True) if kind == name]
        for name in ("sync", "micro", "macro")
    }
    return "\n".join(lines), labels, groups


@family(
    "js.event_loop_order",
    title="Event loop: синхронный код, микро- и макрозадачи",
    competency="js_core",
    grade="middle",
    response_format=_CHOICE,
    time_limit=120,
    discrimination=1.5,
)
def event_loop_order(rng: Random) -> GeneratedItem:
    """Сначала весь синхронный код, затем очередь микрозадач, затем таймеры."""
    code, program_order, groups = _event_loop_program(rng)
    sync, micro, macro = groups["sync"], groups["micro"], groups["macro"]
    correct = sync + micro + macro
    return single_choice(
        rng,
        prompt=_PROMPT_ORDER,
        code=code,
        code_language="javascript",
        correct=" ".join(correct),
        distractors=[
            " ".join(program_order),
            " ".join(sync + macro + micro),
            " ".join(micro + sync + macro),
            " ".join(reversed(correct)),
        ],
        check=NodeCheck(_collecting(code)),
    )


def _collecting(code: str) -> str:
    """Оборачивает console.log, чтобы вывод собрался в одну строку через пробел."""
    return (
        "const out = [];\nconst log = (x) => out.push(x);\n"
        + code.replace("console.log(", "log(")
        + "\nsetTimeout(() => console.log(out.join(' ')), 20);"
    )


@family(
    "js.async_await_order",
    title="Порядок выполнения async/await",
    competency="js_core",
    grade="senior",
    response_format=_CHOICE,
    time_limit=150,
    discrimination=1.5,
    difficulty_offset=-0.2,
)
def async_await_order(rng: Random) -> GeneratedItem:
    """Код до первого await выполняется синхронно, продолжение становится микрозадачей."""
    l1, l2, l3, l4, l5, l6 = rng.sample(list("ABCDEFGHKMPRST"), 6)
    promise_first = rng.random() < 0.5
    call = "load();"
    then = f"Promise.resolve().then(() => console.log('{l5}'));"
    lines = [
        f"console.log('{l1}');",
        "async function load() {",
        f"  console.log('{l2}');",
        "  await null;",
        f"  console.log('{l3}');",
        "}",
        f"setTimeout(() => console.log('{l4}'), 0);",
        *([then, call] if promise_first else [call, then]),
        f"console.log('{l6}');",
    ]
    code = "\n".join(lines)
    micro = [l5, l3] if promise_first else [l3, l5]
    correct = [l1, l2, l6, *micro, l4]
    return single_choice(
        rng,
        prompt=_PROMPT_ORDER,
        code=code,
        code_language="javascript",
        correct=" ".join(correct),
        distractors=[
            " ".join([l1, l2, l3, l6, l5, l4]),
            " ".join([l1, l2, l6, *reversed(micro), l4]),
            " ".join([l1, l6, l2, *micro, l4]),
            " ".join([l1, l2, l6, l4, *micro]),
        ],
        params={"promise_first": promise_first},
        check=NodeCheck(_collecting(code)),
    )
