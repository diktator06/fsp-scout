import math
from collections import deque
from random import Random

from app.models.assessment import ResponseFormat
from app.services.assessment.item_generators.base import (
    GeneratedItem,
    PythonCheck,
    family,
    numeric,
    single_choice,
)

_CHOICE = ResponseFormat.SINGLE_CHOICE
_NUMERIC = ResponseFormat.NUMERIC
_COMPLEXITIES = ("O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n²)")


@family(
    "algo.stack_ops",
    title="Операции со стеком",
    competency="algorithms",
    grade="intern",
    response_format=_NUMERIC,
    time_limit=75,
    discrimination=1.0,
)
def stack_ops(rng: Random) -> GeneratedItem:
    """Последовательность push/pop: что окажется на вершине стека (LIFO)."""
    stack: list[int] = []
    operations: list[str] = []
    values = iter(rng.sample(range(10, 99), 12))
    length = rng.randint(7, 9)
    while len(operations) < length or not stack:
        if stack and rng.random() < 0.4:
            stack.pop()
            operations.append("pop()")
        else:
            value = next(values)
            stack.append(value)
            operations.append(f"push({value})")
    check_lines = ["stack = []"]
    check_lines += [
        "stack.pop()" if op == "pop()" else f"stack.append({op[5:-1]})" for op in operations
    ]
    check_lines.append("print(stack[-1])")
    return numeric(
        prompt="Над пустым стеком выполнили операции по порядку. Какое число окажется на вершине?",
        value=stack[-1],
        code="\n".join(operations),
        code_language="text",
        check=PythonCheck("\n".join(check_lines)),
    )


def _complexity_snippet(rng: Random) -> tuple[str, str]:
    """Один из трёх изоморфных по сложности фрагментов кода и его асимптотика."""
    n, i, j = rng.choice([("n", "i", "j"), ("size", "a", "b"), ("count", "x", "y")])
    factor = rng.choice([2, 3])
    variant = rng.choice(["quadratic", "n_log_n", "log"])
    if variant == "quadratic":
        code = f"total = 0\nfor {i} in range({n}):\n    for {j} in range({i}, {n}):\n        total += {j}"
        return code, "O(n²)"
    if variant == "n_log_n":
        code = (
            f"total = 0\nfor {i} in range({n}):\n    {j} = 1\n    while {j} < {n}:\n"
            f"        total += {j}\n        {j} *= {factor}"
        )
        return code, "O(n log n)"
    code = f"steps = 0\n{i} = {n}\nwhile {i} > 1:\n    {i} //= {factor}\n    steps += 1"
    return code, "O(log n)"


@family(
    "algo.complexity_loops",
    title="Асимптотика вложенных циклов",
    competency="algorithms",
    grade="junior",
    response_format=_CHOICE,
    time_limit=90,
    discrimination=1.2,
)
def complexity_loops(rng: Random) -> GeneratedItem:
    """Оценка времени работы фрагмента в O-нотации."""
    code, correct = _complexity_snippet(rng)
    distractors = [option for option in _COMPLEXITIES if option != correct]
    rng.shuffle(distractors)
    return single_choice(
        rng,
        prompt="Какова временная сложность фрагмента в зависимости от n?",
        code=code,
        code_language="python",
        correct=correct,
        distractors=distractors,
    )


_OPERATIONS = (
    ("Проверка `x in s`, где s — set", "O(1)"),
    ("Проверка `x in items`, где items — list", "O(n)"),
    ("Вставка в начало списка: `items.insert(0, x)`", "O(n)"),
    ("Получение значения по ключу: `d[key]` у dict", "O(1)"),
    ("Сортировка списка: `sorted(items)`", "O(n log n)"),
    ("Бинарный поиск в отсортированном массиве", "O(log n)"),
    ("Добавление в конец списка: `items.append(x)` (амортизированно)", "O(1)"),
)


@family(
    "algo.collection_complexity",
    title="Сложность операций с коллекциями",
    competency="algorithms",
    grade="intern",
    response_format=_CHOICE,
    time_limit=60,
    discrimination=1.0,
    difficulty_offset=-0.2,
)
def collection_complexity(rng: Random) -> GeneratedItem:
    """Средняя сложность типовой операции стандартной коллекции Python."""
    operation, correct = rng.choice(_OPERATIONS)
    distractors = [option for option in _COMPLEXITIES if option != correct]
    rng.shuffle(distractors)
    return single_choice(
        rng,
        prompt=f"Какова средняя временная сложность операции?\n\n{operation}",
        correct=correct,
        distractors=distractors,
    )


@family(
    "algo.binary_search_steps",
    title="Число сравнений бинарного поиска",
    competency="algorithms",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=100,
    discrimination=1.3,
    difficulty_offset=-0.3,
)
def binary_search_steps(rng: Random) -> GeneratedItem:
    """В худшем случае бинарный поиск делает ⌊log₂ n⌋ + 1 сравнений."""
    size = rng.randint(100, 9000)
    return numeric(
        prompt=(
            f"Отсортированный массив содержит {size} различных чисел. Какое наибольшее число "
            "сравнений с искомым значением сделает классический бинарный поиск, прежде чем "
            "найдёт элемент или убедится, что его нет?"
        ),
        value=math.floor(math.log2(size)) + 1,
        params={"size": size},
    )


def _edge(first: str, second: str) -> tuple[str, str]:
    """Ребро в каноническом порядке вершин, чтобы не было дублей A—B и B—A."""
    return (first, second) if first < second else (second, first)


def _random_graph(rng: Random) -> tuple[list[str], list[tuple[str, str]]]:
    """Связный неориентированный граф из 7 вершин: случайное дерево плюс пара лишних рёбер."""
    nodes = rng.sample(list("ABCDEFGHKLMNPRST"), 7)
    edges: set[tuple[str, str]] = set()
    for index in range(1, len(nodes)):
        parent = nodes[rng.randrange(index)]
        edges.add(_edge(parent, nodes[index]))
    while len(edges) < len(nodes) + 1:
        first, second = rng.sample(nodes, 2)
        edges.add(_edge(first, second))
    return nodes, sorted(edges)


def _distances(nodes: list[str], edges: list[tuple[str, str]], start: str) -> dict[str, int]:
    """Расстояния в рёбрах от start поиском в ширину."""
    neighbours: dict[str, list[str]] = {node: [] for node in nodes}
    for first, second in edges:
        neighbours[first].append(second)
        neighbours[second].append(first)
    distance = {start: 0}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for nxt in neighbours[current]:
            if nxt not in distance:
                distance[nxt] = distance[current] + 1
                queue.append(nxt)
    return distance


@family(
    "algo.bfs_shortest_path",
    title="Кратчайший путь в невзвешенном графе",
    competency="algorithms",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=150,
    discrimination=1.2,
)
def bfs_shortest_path(rng: Random) -> GeneratedItem:
    """Длина кратчайшего пути в рёбрах; пара вершин выбирается на расстоянии не меньше трёх."""
    while True:
        nodes, edges = _random_graph(rng)
        start = rng.choice(nodes)
        distance = _distances(nodes, edges, start)
        far = [node for node, d in distance.items() if d >= 3]
        if far:
            break
    target = rng.choice(far)
    return numeric(
        prompt=(
            "Граф неориентированный, рёбра перечислены ниже. Какое наименьшее число рёбер "
            f"нужно пройти из вершины {start} в вершину {target}?"
        ),
        value=distance[target],
        code="\n".join(f"{a} — {b}" for a, b in edges),
        code_language="text",
        params={"start": start, "target": target},
    )


def _min_coins(coins: list[int], amount: int) -> int:
    """Минимальное число монет динамическим программированием."""
    best = [0] + [math.inf] * amount
    for value in range(1, amount + 1):
        for coin in coins:
            if coin <= value and best[value - coin] + 1 < best[value]:
                best[value] = best[value - coin] + 1
    return int(best[amount])


def _greedy_coins(coins: list[int], amount: int) -> int:
    """Число монет жадным алгоритмом (всегда берём наибольшую подходящую)."""
    count = 0
    for coin in sorted(coins, reverse=True):
        count += amount // coin
        amount %= coin
    return count


@family(
    "algo.coin_change",
    title="Размен монет: жадность против динамики",
    competency="algorithms",
    grade="senior",
    response_format=_NUMERIC,
    time_limit=180,
    discrimination=1.5,
    difficulty_offset=-0.1,
)
def coin_change(rng: Random) -> GeneratedItem:
    """Набор монет подобран так, что жадный алгоритм ошибается: нужна динамика."""
    while True:
        middle = rng.randint(3, 6)
        large = rng.randint(middle + 2, 12)
        coins = [1, middle, large]
        amount = rng.randint(large + 2, 3 * large)
        if _greedy_coins(coins, amount) > _min_coins(coins, amount):
            break
    code = f"coins = {coins}\namount = {amount}"
    return numeric(
        prompt=(
            "Монеты каждого номинала есть в неограниченном количестве. Каким наименьшим "
            "числом монет можно набрать сумму amount?"
        ),
        value=_min_coins(coins, amount),
        code=code,
        code_language="python",
        explanation=f"Жадный алгоритм дал бы {_greedy_coins(coins, amount)}.",
        params={"coins": coins, "amount": amount},
    )
