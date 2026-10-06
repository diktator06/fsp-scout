from collections import defaultdict
from dataclasses import dataclass
from random import Random

from app.models.assessment import ResponseFormat
from app.services.assessment.item_generators.base import (
    DataTable,
    GeneratedItem,
    SqliteCheck,
    family,
    numeric,
)

_NUMERIC = ResponseFormat.NUMERIC
_CUSTOMERS = ("Анна", "Борис", "Вера", "Глеб", "Дина", "Егор", "Жанна", "Зоя")
_STATUSES = ("paid", "new", "cancelled")
_PROMPT_VALUE = "Какое число вернёт запрос?"
_PROMPT_ROWS = "Сколько строк вернёт запрос?"


@dataclass(frozen=True, slots=True)
class Order:
    """Строка таблицы orders."""

    id: int
    customer: str
    amount: int
    status: str
    day: int


def _orders(rng: Random, *, count: int | None = None, customers: int = 5) -> list[Order]:
    """Случайная таблица заказов: суммы кратны 100, чтобы считать в уме было реально."""
    names = rng.sample(_CUSTOMERS, customers)
    total = count or rng.randint(8, 11)
    return [
        Order(
            id=index + 1,
            customer=rng.choice(names),
            amount=rng.randint(3, 60) * 100,
            status=rng.choices(_STATUSES, weights=(5, 3, 2))[0],
            day=rng.randint(1, 9),
        )
        for index in range(total)
    ]


def _orders_table(orders: list[Order]) -> DataTable:
    """Таблица orders для условия задания."""
    return DataTable(
        title="orders",
        columns=("id", "customer", "amount", "status", "day"),
        rows=tuple((o.id, o.customer, o.amount, o.status, o.day) for o in orders),
    )


def _quote(value: object) -> str:
    """Литерал SQL для генерации вставок проверочной базы."""
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def _setup(table: DataTable, column_types: tuple[str, ...]) -> tuple[str, ...]:
    """DDL и INSERT для проверки запроса в SQLite в тестах."""
    columns = ", ".join(
        f"{name} {kind}" for name, kind in zip(table.columns, column_types, strict=True)
    )
    statements = [f"CREATE TABLE {table.title} ({columns})"]
    statements += [
        f"INSERT INTO {table.title} VALUES ({', '.join(_quote(v) for v in row)})"
        for row in table.rows
    ]
    return tuple(statements)


_ORDER_TYPES = ("INTEGER", "TEXT", "INTEGER", "TEXT", "INTEGER")


@family(
    "sql.where_count",
    title="Фильтрация и COUNT",
    competency="sql",
    grade="intern",
    response_format=_NUMERIC,
    time_limit=90,
    discrimination=1.1,
)
def where_count(rng: Random) -> GeneratedItem:
    """Подсчёт строк с двумя условиями в WHERE."""
    orders = _orders(rng)
    threshold = rng.choice([1000, 1500, 2000, 2500, 3000])
    query = f"SELECT COUNT(*)\nFROM orders\nWHERE status = 'paid' AND amount > {threshold};"
    answer = sum(1 for o in orders if o.status == "paid" and o.amount > threshold)
    table = _orders_table(orders)
    return numeric(
        prompt=_PROMPT_VALUE,
        value=answer,
        code=query,
        code_language="sql",
        tables=[table],
        check=SqliteCheck(_setup(table, _ORDER_TYPES), query),
    )


@family(
    "sql.distinct_count",
    title="COUNT(DISTINCT)",
    competency="sql",
    grade="intern",
    response_format=_NUMERIC,
    time_limit=90,
    discrimination=1.1,
    difficulty_offset=0.2,
)
def distinct_count(rng: Random) -> GeneratedItem:
    """Число различных покупателей среди отфильтрованных заказов."""
    orders = _orders(rng)
    threshold = rng.choice([1000, 1500, 2000, 2500])
    query = f"SELECT COUNT(DISTINCT customer)\nFROM orders\nWHERE amount >= {threshold};"
    answer = len({o.customer for o in orders if o.amount >= threshold})
    table = _orders_table(orders)
    return numeric(
        prompt=_PROMPT_VALUE,
        value=answer,
        code=query,
        code_language="sql",
        tables=[table],
        check=SqliteCheck(_setup(table, _ORDER_TYPES), query),
    )


@family(
    "sql.group_by_having",
    title="GROUP BY и HAVING",
    competency="sql",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.3,
)
def group_by_having(rng: Random) -> GeneratedItem:
    """HAVING фильтрует уже сгруппированные строки по сумме, а не отдельные заказы."""
    orders = _orders(rng, count=rng.randint(9, 11))
    totals: defaultdict[str, int] = defaultdict(int)
    for order in orders:
        if order.status != "cancelled":
            totals[order.customer] += order.amount
    threshold = rng.choice([3000, 4000, 5000, 6000])
    query = (
        "SELECT customer, SUM(amount) AS total\n"
        "FROM orders\n"
        "WHERE status <> 'cancelled'\n"
        "GROUP BY customer\n"
        f"HAVING SUM(amount) > {threshold};"
    )
    answer = sum(1 for total in totals.values() if total > threshold)
    table = _orders_table(orders)
    return numeric(
        prompt=_PROMPT_ROWS,
        value=answer,
        code=query,
        code_language="sql",
        tables=[table],
        check=SqliteCheck(
            _setup(table, _ORDER_TYPES), f"SELECT COUNT(*) FROM ({query.rstrip(';')})"
        ),
    )


def _people_with_bonus(rng: Random) -> DataTable:
    """Таблица сотрудников, где у части людей премия не указана (NULL)."""
    departments = rng.sample(["sales", "dev", "support", "hr"], 2)
    names = rng.sample(
        ["Ира", "Олег", "Петя", "Рита", "Саша", "Тимур", "Ульяна", "Фёдор", "Юля"], 7
    )
    rows = []
    for index, name in enumerate(names, start=1):
        bonus = None if rng.random() < 0.35 else rng.randint(1, 9) * 1000
        rows.append((index, name, rng.choice(departments), bonus))
    if all(row[3] is None for row in rows if row[2] == rows[0][2]):
        rows[0] = (rows[0][0], rows[0][1], rows[0][2], 5000)
    return DataTable(title="employees", columns=("id", "name", "dept", "bonus"), rows=tuple(rows))


@family(
    "sql.null_aggregates",
    title="NULL в агрегатных функциях",
    competency="sql",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.4,
    difficulty_offset=-0.2,
)
def null_aggregates(rng: Random) -> GeneratedItem:
    """AVG пропускает NULL: делится на число заполненных значений, а не на число строк."""
    table = _people_with_bonus(rng)
    department = table.rows[0][2]
    bonuses = [row[3] for row in table.rows if row[2] == department and row[3] is not None]
    query = f"SELECT AVG(bonus)\nFROM employees\nWHERE dept = '{department}';"
    answer = round(sum(bonuses) / len(bonuses), 2)
    return numeric(
        prompt=_PROMPT_VALUE,
        value=answer,
        tolerance=0.01,
        input_hint="Число, при необходимости с двумя знаками после запятой",
        code=query,
        code_language="sql",
        tables=[table],
        explanation=f"Учитываются только заполненные премии: {len(bonuses)} шт.",
        check=SqliteCheck(
            _setup(table, ("INTEGER", "TEXT", "TEXT", "INTEGER")),
            f"SELECT ROUND(AVG(bonus), 2) FROM employees WHERE dept = '{department}'",
        ),
    )


def _customers_and_orders(rng: Random) -> tuple[DataTable, DataTable]:
    """Покупатели и их заказы: у кого-то несколько заказов, у кого-то ни одного."""
    names = rng.sample(_CUSTOMERS, rng.randint(5, 6))
    customers = tuple((index, name) for index, name in enumerate(names, start=1))
    buyers = rng.sample([c[0] for c in customers], rng.randint(2, len(customers) - 2))
    orders = []
    for order_id in range(1, rng.randint(6, 9) + 1):
        orders.append((order_id, rng.choice(buyers), rng.randint(3, 40) * 100))
    return (
        DataTable(title="customers", columns=("id", "name"), rows=customers),
        DataTable(title="orders", columns=("id", "customer_id", "amount"), rows=tuple(orders)),
    )


_CUSTOMER_TYPES = ("INTEGER", "TEXT")
_SHORT_ORDER_TYPES = ("INTEGER", "INTEGER", "INTEGER")


@family(
    "sql.join_row_count",
    title="Число строк после INNER JOIN",
    competency="sql",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.2,
    difficulty_offset=0.2,
)
def join_row_count(rng: Random) -> GeneratedItem:
    """При связи «один ко многим» JOIN размножает строки покупателя по числу заказов."""
    customers, orders = _customers_and_orders(rng)
    query = "SELECT c.name, o.amount\nFROM customers c\nJOIN orders o ON o.customer_id = c.id;"
    return numeric(
        prompt=_PROMPT_ROWS,
        value=len(orders.rows),
        code=query,
        code_language="sql",
        tables=[customers, orders],
        check=SqliteCheck(
            _setup(customers, _CUSTOMER_TYPES) + _setup(orders, _SHORT_ORDER_TYPES),
            f"SELECT COUNT(*) FROM ({query.rstrip(';')})",
        ),
    )


@family(
    "sql.left_join_rows",
    title="Число строк после LEFT JOIN",
    competency="sql",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.5,
)
def left_join_rows(rng: Random) -> GeneratedItem:
    """LEFT JOIN: строки заказов плюс по одной строке на покупателя без заказов."""
    customers, orders = _customers_and_orders(rng)
    with_orders = {row[1] for row in orders.rows}
    without = sum(1 for row in customers.rows if row[0] not in with_orders)
    query = "SELECT c.name, o.id\nFROM customers c\nLEFT JOIN orders o ON o.customer_id = c.id;"
    return numeric(
        prompt=_PROMPT_ROWS,
        value=len(orders.rows) + without,
        code=query,
        code_language="sql",
        tables=[customers, orders],
        check=SqliteCheck(
            _setup(customers, _CUSTOMER_TYPES) + _setup(orders, _SHORT_ORDER_TYPES),
            f"SELECT COUNT(*) FROM ({query.rstrip(';')})",
        ),
    )


@family(
    "sql.left_join_anti",
    title="Поиск строк без пары через LEFT JOIN … IS NULL",
    competency="sql",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.3,
    difficulty_offset=-0.2,
)
def left_join_anti(rng: Random) -> GeneratedItem:
    """Анти-соединение: покупатели, у которых нет ни одного заказа."""
    customers, orders = _customers_and_orders(rng)
    with_orders = {row[1] for row in orders.rows}
    query = (
        "SELECT COUNT(*)\n"
        "FROM customers c\n"
        "LEFT JOIN orders o ON o.customer_id = c.id\n"
        "WHERE o.id IS NULL;"
    )
    return numeric(
        prompt=_PROMPT_VALUE,
        value=sum(1 for row in customers.rows if row[0] not in with_orders),
        code=query,
        code_language="sql",
        tables=[customers, orders],
        check=SqliteCheck(
            _setup(customers, _CUSTOMER_TYPES) + _setup(orders, _SHORT_ORDER_TYPES), query
        ),
    )


@family(
    "sql.window_running_total",
    title="Нарастающий итог оконной функцией",
    competency="sql",
    grade="senior",
    response_format=_NUMERIC,
    time_limit=150,
    discrimination=1.4,
    difficulty_offset=-0.2,
)
def window_running_total(rng: Random) -> GeneratedItem:
    """SUM() OVER (PARTITION BY … ORDER BY …) — сумма по своей партиции до текущей строки."""
    names = rng.sample(_CUSTOMERS, 3)
    rows = []
    for name in names:
        days = sorted(rng.sample(range(1, 10), rng.randint(2, 3)))
        rows += [(name, day, rng.randint(3, 40) * 100) for day in days]
    rng.shuffle(rows)
    table_rows = tuple((index, *row) for index, row in enumerate(rows, start=1))
    target = rng.choice(
        [row for row in table_rows if row[2] != min(r[2] for r in table_rows if r[1] == row[1])]
    )
    answer = sum(row[3] for row in table_rows if row[1] == target[1] and row[2] <= target[2])
    table = DataTable(title="orders", columns=("id", "customer", "day", "amount"), rows=table_rows)
    query = (
        "SELECT id, customer, day,\n"
        "       SUM(amount) OVER (PARTITION BY customer ORDER BY day) AS running\n"
        "FROM orders;"
    )
    return numeric(
        prompt=f"Какое значение running будет в строке с id = {target[0]}?",
        value=answer,
        code=query,
        code_language="sql",
        tables=[table],
        check=SqliteCheck(
            _setup(table, ("INTEGER", "TEXT", "INTEGER", "INTEGER")),
            f"SELECT running FROM ({query.rstrip(';')}) WHERE id = {target[0]}",
        ),
    )


@family(
    "sql.dense_rank",
    title="DENSE_RANK при равных значениях",
    competency="sql",
    grade="senior",
    response_format=_NUMERIC,
    time_limit=130,
    discrimination=1.3,
)
def dense_rank(rng: Random) -> GeneratedItem:
    """DENSE_RANK не оставляет пропусков после повторов, в отличие от RANK."""
    players = rng.sample(["Лев", "Мила", "Нина", "Остап", "Полина", "Роман", "Стас", "Тая"], 7)
    pool = rng.sample(range(50, 100), 4)
    scores = [rng.choice(pool) for _ in players]
    while len(set(scores)) == len(scores) or len(set(scores)) < 3:
        scores = [rng.choice(pool) for _ in players]
    table_rows = tuple(
        (index, player, score)
        for index, (player, score) in enumerate(zip(players, scores, strict=True), start=1)
    )
    distinct = sorted(set(scores), reverse=True)
    lowest_candidates = [row for row in table_rows if distinct.index(row[2]) >= 2]
    target = rng.choice(lowest_candidates)
    answer = distinct.index(target[2]) + 1
    table = DataTable(title="results", columns=("id", "player", "score"), rows=table_rows)
    query = "SELECT player,\n       DENSE_RANK() OVER (ORDER BY score DESC) AS place\nFROM results;"
    return numeric(
        prompt=f"Какое значение place получит игрок {target[1]}?",
        value=answer,
        code=query,
        code_language="sql",
        tables=[table],
        explanation=f"RANK дал бы {sum(1 for s in scores if s > target[2]) + 1}.",
        params={"rank_would_be": sum(1 for s in scores if s > target[2]) + 1},
        check=SqliteCheck(
            _setup(table, ("INTEGER", "TEXT", "INTEGER")),
            f"SELECT place FROM ({query.rstrip(';')}) WHERE player = '{target[1]}'",
        ),
    )
