from itertools import permutations
from random import Random

from app.models.assessment import ItemFamilyStatus, ResponseFormat
from app.services.assessment.item_generators.base import (
    GeneratedItem,
    family,
    numeric,
    single_choice,
)

_CHOICE = ResponseFormat.SINGLE_CHOICE
_NUMERIC = ResponseFormat.NUMERIC


@family(
    "dom.event_propagation",
    title="Фазы перехвата и всплытия событий",
    competency="browser_dom",
    grade="middle",
    response_format=_CHOICE,
    time_limit=120,
    discrimination=1.4,
)
def event_propagation(rng: Random) -> GeneratedItem:
    """Сначала перехват сверху вниз, затем обработчик цели, затем всплытие снизу вверх."""
    outer, middle, inner = rng.sample(
        ["page", "card", "list", "item", "panel", "menu", "button"], 3
    )
    outer_capture = rng.random() < 0.5
    middle_capture = rng.random() < 0.5
    if not outer_capture and not middle_capture:
        middle_capture = True
    html = f'<div id="{outer}">\n  <div id="{middle}">\n    <button id="{inner}">OK</button>\n  </div>\n</div>'
    script = "\n".join(
        [
            f"{outer}.addEventListener('click', () => log('{outer}'), {str(outer_capture).lower()});",
            f"{middle}.addEventListener('click', () => log('{middle}'), {str(middle_capture).lower()});",
            f"{inner}.addEventListener('click', () => log('{inner}'));",
        ]
    )
    capturing = [name for name, flag in ((outer, outer_capture), (middle, middle_capture)) if flag]
    bubbling = [
        name for name, flag in ((middle, middle_capture), (outer, outer_capture)) if not flag
    ]
    correct = [*capturing, inner, *bubbling]
    return single_choice(
        rng,
        prompt=(
            f"Пользователь нажал на кнопку #{inner}. Третий аргумент addEventListener — флаг "
            "capture. В каком порядке выполнятся обработчики?"
        ),
        code=f"{html}\n\n<script>\n{script}\n</script>",
        code_language="html",
        correct=" → ".join(correct),
        distractors=[
            " → ".join([inner, middle, outer]),
            " → ".join([outer, middle, inner]),
            " → ".join([inner, *capturing, *bubbling]),
            *(" → ".join(order) for order in permutations(correct)),
        ],
    )


_STORAGE_CASES = (
    (
        "Черновик формы должен пережить закрытие браузера, на сервер его отправлять не нужно",
        "localStorage",
    ),
    ("Данные нужны только в текущей вкладке и должны пропасть при её закрытии", "sessionStorage"),
    (
        "Идентификатор сессии, который нельзя прочитать из JavaScript даже при XSS",
        "Cookie с флагом HttpOnly",
    ),
    (
        "Небольшое значение, которое браузер сам отправляет на сервер с каждым запросом, и скрипт тоже может его читать",
        "Обычная cookie без HttpOnly",
    ),
)


@family(
    "dom.storage_choice",
    title="Выбор хранилища в браузере",
    competency="browser_dom",
    grade="junior",
    response_format=_CHOICE,
    time_limit=75,
    discrimination=1.1,
)
def storage_choice(rng: Random) -> GeneratedItem:
    """Время жизни, область видимости и доступность хранилища из JavaScript."""
    case, correct = rng.choice(_STORAGE_CASES)
    return single_choice(
        rng,
        prompt=f"Где лучше хранить данные в такой ситуации?\n\n{case}.",
        correct=correct,
        distractors=[answer for _, answer in _STORAGE_CASES if answer != correct],
    )


@family(
    "css.box_model",
    title="Box model и box-sizing",
    competency="css_layout",
    grade="intern",
    response_format=_NUMERIC,
    time_limit=75,
    discrimination=1.1,
    difficulty_offset=0.2,
)
def box_model(rng: Random) -> GeneratedItem:
    """При content-box padding и border добавляются к width, при border-box — нет."""
    width = rng.choice([160, 200, 240, 280, 300, 320])
    padding = rng.choice([8, 10, 12, 16, 20, 24])
    border = rng.choice([1, 2, 3, 4])
    sizing = rng.choice(["content-box", "border-box"])
    value = width + 2 * padding + 2 * border if sizing == "content-box" else width
    return numeric(
        prompt="Какую ширину в пикселях займёт элемент на странице (без учёта margin)?",
        value=value,
        code=f".card {{\n  box-sizing: {sizing};\n  width: {width}px;\n  padding: {padding}px;\n  border: {border}px solid;\n  margin: 16px;\n}}",
        code_language="css",
        unit="px",
        params={"box_sizing": sizing},
    )


def _specificity(selector: str) -> tuple[int, int, int]:
    """Специфичность селектора из частей нашего словаря: (id, классы, элементы)."""
    ids = selector.count("#")
    classes = selector.count(".")
    elements = sum(
        1 for part in selector.replace(".", " .").split() if not part.startswith((".", "#"))
    )
    return ids, classes, elements


def _random_selector(rng: Random) -> str:
    """Селектор, который гарантированно подходит к абзацу из разметки задания.

    Предки берутся не больше чем по одному с каждого уровня вложенности: section и
    div. Иначе комбинатор потомка дал бы селектор, который ни к чему не применится.
    """
    section = rng.choice([None, "#main", "section", "section.card"])
    wrapper = rng.choice([None, "div", ".card", "div.card"])
    target = rng.choice(["p", "p.text", ".text", "p.active", ".text.active", "p.text.active"])
    return " ".join(part for part in (section, wrapper, target) if part)


@family(
    "css.specificity",
    title="Специфичность селекторов",
    competency="css_layout",
    grade="junior",
    response_format=_CHOICE,
    time_limit=120,
    discrimination=1.3,
)
def specificity(rng: Random) -> GeneratedItem:
    """Побеждает наибольшая специфичность (id, классы, элементы); равенство в задании исключено."""
    colors = rng.sample(["red", "green", "blue", "orange", "purple"], 4)
    while True:
        selectors = [_random_selector(rng) for _ in range(3)]
        scores = [_specificity(selector) for selector in selectors]
        if len(set(scores)) == 3:
            break
    winner = scores.index(max(scores))
    rules = "\n".join(
        f"{selector} {{ color: {color}; }}"
        for selector, color in zip(selectors, colors, strict=False)
    )
    html = '<section id="main" class="card">\n  <div class="card">\n    <p class="text active">Текст</p>\n  </div>\n</section>'
    return single_choice(
        rng,
        prompt="Все три правила подходят к абзацу. Какого цвета будет текст?",
        code=f"{html}\n\n<style>\n{rules}\n</style>",
        code_language="html",
        correct=colors[winner],
        distractors=[color for index, color in enumerate(colors) if index != winner],
        params={"specificity": scores},
    )


@family(
    "css.flex_grow",
    title="Распределение свободного места во flex-контейнере",
    competency="css_layout",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=150,
    discrimination=1.4,
)
def flex_grow(rng: Random) -> GeneratedItem:
    """Свободное место делится пропорционально flex-grow и прибавляется к flex-basis."""
    container = rng.choice([600, 720, 800, 900, 960])
    bases = [rng.choice([80, 100, 120, 150]) for _ in range(3)]
    grows = [rng.randint(0, 3) for _ in range(3)]
    if sum(grows) == 0:
        grows[0] = 1
    target = rng.choice([index for index, grow in enumerate(grows) if grow > 0])
    free = container - sum(bases)
    value = bases[target] + free * grows[target] / sum(grows)
    items = "\n".join(
        f".item-{index + 1} {{ flex: {grow} 0 {basis}px; }}"
        for index, (grow, basis) in enumerate(zip(grows, bases, strict=True))
    )
    return numeric(
        prompt=(
            f"Ширина контейнера — {container}px, отступов и gap нет. Какой будет ширина "
            f".item-{target + 1} в пикселях?"
        ),
        value=round(value, 2),
        tolerance=0.5,
        input_hint="Число, можно с десятичной частью",
        code=f".row {{ display: flex; width: {container}px; }}\n{items}",
        code_language="css",
        unit="px",
    )


@family(
    "css.margin_collapse",
    title="Схлопывание вертикальных отступов",
    competency="css_layout",
    grade="senior",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.2,
    difficulty_offset=-0.4,
    status=ItemFamilyStatus.PILOT,
)
def margin_collapse(rng: Random) -> GeneratedItem:
    """Соседние вертикальные margin не складываются: берётся больший или сумма с отрицательным."""
    first = rng.choice([16, 20, 24, 32, 40])
    second_positive = rng.random() < 0.6
    second = rng.choice([8, 12, 30, 48]) if second_positive else -rng.choice([8, 10, 12])
    value = max(first, second) if second_positive else first + second
    return numeric(
        prompt="Какое расстояние в пикселях будет между блоками .a и .b по вертикали?",
        value=value,
        code=(
            '<div class="a">Первый</div>\n<div class="b">Второй</div>\n\n'
            f".a {{ display: block; margin-bottom: {first}px; }}\n"
            f".b {{ display: block; margin-top: {second}px; }}"
        ),
        code_language="css",
        unit="px",
    )


@family(
    "react.state_batching",
    title="Пакетное обновление состояния",
    competency="react",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.5,
)
def state_batching(rng: Random) -> GeneratedItem:
    """setState(count + 1) несколько раз подряд видит одно и то же count; функция-апдейтер — нет."""
    start = rng.randint(0, 5)
    step = rng.randint(1, 3)
    calls = rng.randint(2, 4)
    updater = rng.random() < 0.5
    call = f"setCount((c) => c + {step});" if updater else f"setCount(count + {step});"
    body = "\n".join(f"    {call}" for _ in range(calls))
    code = (
        "function Counter() {\n"
        f"  const [count, setCount] = useState({start});\n"
        "  const handleClick = () => {\n"
        f"{body}\n"
        "  };\n"
        "  return <button onClick={handleClick}>{count}</button>;\n"
        "}"
    )
    value = start + step * calls if updater else start + step
    return numeric(
        prompt="Какое число будет на кнопке после одного нажатия?",
        value=value,
        code=code,
        code_language="jsx",
        params={"updater": updater},
    )


@family(
    "react.effect_runs",
    title="Зависимости useEffect",
    competency="react",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.3,
    difficulty_offset=0.3,
)
def effect_runs(rng: Random) -> GeneratedItem:
    """Эффект с [a] выполняется при монтировании и при каждом изменении a (по Object.is)."""
    initial_a = rng.randint(1, 3)
    current_a = initial_a
    actions: list[str] = []
    runs = 1
    for _ in range(rng.randint(4, 6)):
        if rng.random() < 0.55:
            new_a = current_a if rng.random() < 0.35 else current_a + rng.randint(1, 2)
            actions.append(f"setA({new_a})")
            if new_a != current_a:
                runs += 1
                current_a = new_a
        else:
            actions.append(f"setB({rng.randint(10, 99)})")
    code = (
        "function Widget() {\n"
        f"  const [a, setA] = useState({initial_a});\n"
        "  const [b, setB] = useState(0);\n"
        "  useEffect(() => {\n    console.log('effect');\n  }, [a]);\n"
        "  // …\n"
        "}"
    )
    return numeric(
        prompt=(
            "Компонент смонтировался (production-сборка, без StrictMode), затем по очереди "
            f"выполнились обновления: {', '.join(actions)}. Сколько раз всего будет напечатано "
            "«effect», включая монтирование?"
        ),
        value=runs,
        code=code,
        code_language="jsx",
    )


_PROP_KINDS = (
    ('title="Отчёт"', False),
    ("count={42}", False),
    ("style={{ color: 'red' }}", True),
    ("onSelect={() => setOpen(true)}", True),
    ("onSelect={handleSelect}", False),
    ("options={memoizedOptions}", False),
    ("items={[1, 2, 3]}", True),
)


@family(
    "react.memo_rerenders",
    title="React.memo и стабильность пропсов",
    competency="react",
    grade="senior",
    response_format=_NUMERIC,
    time_limit=150,
    discrimination=1.4,
    difficulty_offset=-0.2,
)
def memo_rerenders(rng: Random) -> GeneratedItem:
    """memo пропускает рендер, только если все пропсы равны по ссылке."""
    chosen = rng.sample(_PROP_KINDS, 4)
    children = "\n".join(
        f"      <Child{index + 1} {prop} />" for index, (prop, _) in enumerate(chosen)
    )
    code = (
        "const handleSelect = useCallback(() => setOpen(true), []);\n"
        "const memoizedOptions = useMemo(() => ['a', 'b'], []);\n\n"
        "// Child1…Child4 обёрнуты в React.memo\n"
        "return (\n    <>\n"
        f"{children}\n"
        "    </>\n);"
    )
    return numeric(
        prompt=(
            "Родитель перерисовался из-за изменения своего состояния (не связанного с пропсами "
            "детей). Сколько из четырёх дочерних компонентов тоже перерисуются?"
        ),
        value=sum(1 for _, rerenders in chosen if rerenders),
        code=code,
        code_language="jsx",
    )
