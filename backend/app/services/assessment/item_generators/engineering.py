import math
from itertools import permutations
from random import Random

from app.models.assessment import ResponseFormat
from app.services.assessment.item_generators.base import (
    GeneratedItem,
    PythonCheck,
    family,
    format_number,
    numeric,
    single_choice,
)

_CHOICE = ResponseFormat.SINGLE_CHOICE
_NUMERIC = ResponseFormat.NUMERIC


@family(
    "conc.thread_pool_time",
    title="Время выполнения задач в пуле потоков",
    competency="concurrency",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=90,
    discrimination=1.1,
)
def thread_pool_time(rng: Random) -> GeneratedItem:
    """Задачи ввода-вывода идут волнами по размеру пула: ⌈N / K⌉ × T."""
    tasks = rng.randint(7, 30)
    workers = rng.randint(2, 6)
    duration = rng.choice([1, 2, 3, 5])
    return numeric(
        prompt=(
            f"Нужно выполнить {tasks} одинаковых HTTP-запросов, каждый ждёт ответа {duration} с "
            f"и почти не нагружает процессор. Запросы отправляются через ThreadPoolExecutor "
            f"с max_workers={workers}. За сколько секунд выполнятся все запросы?"
        ),
        value=math.ceil(tasks / workers) * duration,
        unit="с",
    )


@family(
    "conc.asyncio_order",
    title="Порядок завершения корутин в asyncio.gather",
    competency="concurrency",
    grade="middle",
    response_format=_CHOICE,
    time_limit=120,
    discrimination=1.3,
)
def asyncio_order(rng: Random) -> GeneratedItem:
    """Корутины выполняются конкурентно: печать идёт в порядке длительности ожиданий."""
    names = rng.sample(["fetch", "parse", "store", "notify", "index", "audit"], 3)
    delays = rng.sample([0.01, 0.02, 0.03, 0.05], 3)
    lines = [
        "import asyncio",
        "",
        "async def job(name, delay):",
        "    await asyncio.sleep(delay)",
        "    print(name)",
        "",
    ]
    lines += ["async def main():", "    await asyncio.gather("]
    lines += [f'        job("{name}", {delay}),' for name, delay in zip(names, delays, strict=True)]
    lines += ["    )", "", "asyncio.run(main())"]
    code = "\n".join(lines)
    by_delay = [name for _, name in sorted(zip(delays, names, strict=True))]
    return single_choice(
        rng,
        prompt="В каком порядке будут напечатаны имена?",
        code=code,
        code_language="python",
        correct=" ".join(by_delay),
        distractors=[
            " ".join(names),
            " ".join(reversed(by_delay)),
            *(" ".join(order) for order in permutations(by_delay)),
        ],
        check=PythonCheck(code.replace("print(name)", "print(name, end=' ')") + "\nprint()"),
    )


@family(
    "conc.lock_order_deadlock",
    title="Взаимная блокировка из-за порядка захвата",
    competency="concurrency",
    grade="senior",
    response_format=_CHOICE,
    time_limit=150,
    discrimination=1.4,
    difficulty_offset=-0.2,
)
def lock_order_deadlock(rng: Random) -> GeneratedItem:
    """Взаимная блокировка возможна, только если два потока берут одну пару замков в разном порядке."""
    locks = rng.sample(["accounts", "orders", "stock", "users", "audit"], 3)
    pairs = [(locks[0], locks[1]), (locks[1], locks[2]), (locks[0], locks[2])]
    deadlock = rng.random() < 0.75
    first_pair = rng.choice(pairs)
    workers = [first_pair]
    if deadlock:
        workers.append((first_pair[1], first_pair[0]))
    else:
        workers.append(first_pair)
    third = rng.choice([p for p in pairs if set(p) != set(first_pair)])
    workers.append(third)
    order = [0, 1, 2]
    rng.shuffle(order)
    workers = [workers[index] for index in order]
    lines = [
        f"Поток {index + 1}: захватывает {a}, затем {b}" for index, (a, b) in enumerate(workers)
    ]

    def conflict(first: tuple[str, str], second: tuple[str, str]) -> bool:
        """Пара потоков берёт одни и те же замки в противоположном порядке."""
        return first == (second[1], second[0])

    found = [
        f"Потоки {i + 1} и {j + 1}"
        for i in range(3)
        for j in range(i + 1, 3)
        if conflict(workers[i], workers[j])
    ]
    correct = found[0] if found else "Взаимная блокировка невозможна"
    options = ["Потоки 1 и 2", "Потоки 1 и 3", "Потоки 2 и 3", "Взаимная блокировка невозможна"]
    return single_choice(
        rng,
        prompt=(
            "Каждый поток захватывает два замка по очереди и держит их до конца работы. "
            "Какие потоки могут попасть во взаимную блокировку?"
        ),
        code="\n".join(lines),
        code_language="text",
        correct=correct,
        distractors=[option for option in options if option != correct],
    )


@family(
    "arch.cache_latency",
    title="Средняя задержка с кешем",
    competency="architecture",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.2,
)
def cache_latency(rng: Random) -> GeneratedItem:
    """Средняя задержка = проверка кеша + доля промахов × запрос в базу."""
    hit_ratio = rng.choice([70, 75, 80, 85, 90, 95])
    cache_ms = rng.choice([1, 2, 3])
    database_ms = rng.choice([20, 40, 50, 80, 100])
    value = cache_ms + (100 - hit_ratio) / 100 * database_ms
    return numeric(
        prompt=(
            f"Сервис сначала проверяет Redis ({cache_ms} мс), а при промахе дополнительно идёт в "
            f"PostgreSQL ({database_ms} мс). Доля попаданий в кеш — {hit_ratio} %. Какова средняя "
            "задержка чтения в миллисекундах?"
        ),
        value=round(value, 2),
        tolerance=0.05,
        input_hint="Число, можно с десятичной частью",
        unit="мс",
    )


@family(
    "arch.composite_index",
    title="Выбор составного индекса",
    competency="architecture",
    grade="senior",
    response_format=_CHOICE,
    time_limit=120,
    discrimination=1.2,
    difficulty_offset=-0.3,
)
def composite_index(rng: Random) -> GeneratedItem:
    """Равенство — первым столбцом индекса, диапазон — вторым."""
    table, equality, range_column = rng.choice(
        [
            ("orders", "customer_id", "created_at"),
            ("payments", "merchant_id", "amount"),
            ("events", "user_id", "occurred_at"),
            ("tickets", "status", "updated_at"),
        ]
    )
    query = f"SELECT *\nFROM {table}\nWHERE {equality} = $1\n  AND {range_column} > $2;"
    correct = f"({equality}, {range_column})"
    return single_choice(
        rng,
        prompt="Таблица большая, запрос ниже выполняется очень часто. Какой индекс B-tree подойдёт лучше всего?",
        code=query,
        code_language="sql",
        correct=correct,
        distractors=[
            f"({range_column}, {equality})",
            f"Два отдельных индекса: ({equality}) и ({range_column})",
            f"({range_column})",
        ],
    )


@family(
    "arch.availability_budget",
    title="Допустимый простой по SLA",
    competency="architecture",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=90,
    discrimination=1.0,
)
def availability_budget(rng: Random) -> GeneratedItem:
    """Бюджет простоя = (1 − доступность) × длительность периода."""
    availability = rng.choice([99.0, 99.5, 99.9, 99.95])
    period, minutes = rng.choice([("месяц (30 дней)", 30 * 24 * 60), ("неделю", 7 * 24 * 60)])
    value = (100 - availability) / 100 * minutes
    return numeric(
        prompt=(
            f"SLA обещает доступность {format_number(availability)} %. Сколько минут простоя "
            f"допустимо за {period}?"
        ),
        value=round(value, 2),
        tolerance=0.1,
        input_hint="Число, можно с десятичной частью",
        unit="мин",
    )


@family(
    "tool.docker_layer_cache",
    title="Кеш слоёв Docker",
    competency="tooling",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.3,
)
def docker_layer_cache(rng: Random) -> GeneratedItem:
    """Изменение файла инвалидирует COPY, где он участвует, и все инструкции после неё."""
    language = rng.choice(["python", "node"])
    if language == "python":
        lines = [
            "FROM python:3.13-slim",
            "WORKDIR /app",
            "COPY requirements.txt .",
            "RUN pip install -r requirements.txt",
            "COPY . .",
            "RUN python -m compileall .",
            'CMD ["python", "main.py"]',
        ]
        changed, first_affected = rng.choice([("requirements.txt", 2), ("main.py", 4)])
    else:
        lines = [
            "FROM node:24-alpine",
            "WORKDIR /app",
            "COPY package.json package-lock.json ./",
            "RUN npm ci",
            "COPY . .",
            "RUN npm run build",
            'CMD ["node", "dist/server.js"]',
        ]
        changed, first_affected = rng.choice([("package-lock.json", 2), ("src/server.ts", 4)])
    return numeric(
        prompt=(
            f"Образ уже собирался, кеш слоёв на месте. Разработчик изменил только файл {changed} "
            "и запускает сборку снова. Сколько инструкций Dockerfile будут выполнены заново, "
            "без кеша? CMD тоже считается инструкцией."
        ),
        value=len(lines) - first_affected,
        code="\n".join(lines),
        code_language="docker",
        params={"changed": changed},
    )


def _version(major: int, minor: int, patch: int) -> str:
    """Версия в формате semver."""
    return f"{major}.{minor}.{patch}"


@family(
    "tool.semver_range",
    title="Диапазоны версий ^ и ~",
    competency="tooling",
    grade="junior",
    response_format=_CHOICE,
    time_limit=90,
    discrimination=1.2,
    difficulty_offset=0.2,
)
def semver_range(rng: Random) -> GeneratedItem:
    """^ разрешает новые minor и patch при том же major, ~ — только новые patch."""
    major = rng.randint(1, 5)
    minor = rng.randint(2, 8)
    patch = rng.randint(1, 6)
    operator = rng.choice(["^", "~"])
    base = _version(major, minor, patch)
    if operator == "^":
        correct = _version(major, minor + rng.randint(1, 4), rng.randint(0, 9))
        distractors = [
            _version(major + 1, 0, 0),
            _version(major, minor, patch - 1),
            _version(major, minor - 1, patch + 3),
        ]
    else:
        correct = _version(major, minor, patch + rng.randint(1, 5))
        distractors = [
            _version(major, minor + 1, 0),
            _version(major, minor, patch - 1),
            _version(major + 1, minor, patch),
        ]
    return single_choice(
        rng,
        prompt=f'В package.json указано "lib": "{operator}{base}". Какую версию npm может установить?',
        correct=correct,
        distractors=distractors,
        params={"operator": operator},
    )
