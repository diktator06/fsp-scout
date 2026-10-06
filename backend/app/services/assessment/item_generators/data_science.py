import math
import statistics
from collections import defaultdict
from random import Random

from app.models.assessment import ItemFamilyStatus, ResponseFormat
from app.services.assessment.item_generators.base import (
    DataTable,
    GeneratedItem,
    PythonCheck,
    family,
    format_number,
    numeric,
    single_choice,
)

_CHOICE = ResponseFormat.SINGLE_CHOICE
_NUMERIC = ResponseFormat.NUMERIC
_PERCENT_HINT = "Процент, округлите до одного знака после запятой"
_CITIES = ("Москва", "Казань", "Пермь", "Томск", "Сочи", "Омск")


def _sample(rng: Random, size: int, low: int = 10, high: int = 99) -> list[int]:
    """Случайная выборка целых чисел."""
    return [rng.randint(low, high) for _ in range(size)]


@family(
    "stats.median",
    title="Медиана выборки",
    competency="statistics",
    grade="intern",
    response_format=_NUMERIC,
    time_limit=75,
    discrimination=1.0,
)
def median(rng: Random) -> GeneratedItem:
    """Медиана: середина упорядоченной выборки, для чётного размера — среднее двух центральных."""
    values = _sample(rng, rng.choice([7, 8, 9, 10]))
    return numeric(
        prompt="Время ответа сервиса в миллисекундах по замерам ниже. Чему равна медиана?",
        value=statistics.median(values),
        tolerance=0.01,
        input_hint="Число, можно с десятичной частью",
        code=", ".join(map(str, values)),
        code_language="text",
        unit="мс",
    )


@family(
    "stats.percentile_nearest_rank",
    title="Перцентиль методом ближайшего ранга",
    competency="statistics",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.2,
)
def percentile_nearest_rank(rng: Random) -> GeneratedItem:
    """p-й перцентиль по ближайшему рангу: элемент с номером ⌈p/100 × n⌉ в упорядоченной выборке."""
    size = rng.choice([12, 15, 16, 20])
    values = rng.sample(range(40, 400), size)
    level = rng.choice([75, 90, 95])
    rank = math.ceil(level / 100 * size)
    return numeric(
        prompt=(
            f"Замеры времени ответа (мс) ниже. Найдите p{level} методом ближайшего ранга: "
            f"элемент с номером ⌈{level}/100 × n⌉ в выборке, упорядоченной по возрастанию."
        ),
        value=sorted(values)[rank - 1],
        code=", ".join(map(str, values)),
        code_language="text",
        unit="мс",
    )


@family(
    "stats.conditional_probability",
    title="Условная вероятность по таблице сопряжённости",
    competency="statistics",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.3,
)
def conditional_probability(rng: Random) -> GeneratedItem:
    """P(A | B) = P(A и B) / P(B): делим на итог по условию, а не на всю выборку."""
    counts = {
        ("mobile", True): rng.randint(20, 90),
        ("mobile", False): rng.randint(200, 600),
        ("desktop", True): rng.randint(20, 90),
        ("desktop", False): rng.randint(100, 400),
    }
    device = rng.choice(["mobile", "desktop"])
    value = counts[(device, True)] / (counts[(device, True)] + counts[(device, False)]) * 100
    table = DataTable(
        title="Сессии за неделю",
        columns=("Устройство", "Покупка была", "Покупки не было"),
        rows=(
            ("mobile", counts[("mobile", True)], counts[("mobile", False)]),
            ("desktop", counts[("desktop", True)], counts[("desktop", False)]),
        ),
    )
    return numeric(
        prompt=f"Какова вероятность покупки при условии, что сессия была с устройства {device}?",
        value=round(value, 1),
        tolerance=0.1,
        input_hint=_PERCENT_HINT,
        tables=[table],
        unit="%",
    )


@family(
    "stats.bayes_posterior",
    title="Теорема Байеса: доля ложных срабатываний",
    competency="statistics",
    grade="senior",
    response_format=_NUMERIC,
    time_limit=180,
    discrimination=1.6,
    difficulty_offset=-0.2,
)
def bayes_posterior(rng: Random) -> GeneratedItem:
    """При редком событии даже точный детектор даёт много ложных тревог."""
    prevalence = rng.choice([0.5, 1, 2, 3, 5])
    sensitivity = rng.choice([90, 95, 98, 99])
    specificity = rng.choice([90, 95, 97, 99])
    p = prevalence / 100
    true_positive = p * sensitivity / 100
    false_positive = (1 - p) * (1 - specificity / 100)
    value = true_positive / (true_positive + false_positive) * 100
    return numeric(
        prompt=(
            f"Мошеннические транзакции составляют {format_number(prevalence)} % от всех. Антифрод "
            f"помечает {sensitivity} % мошеннических операций и ошибочно помечает "
            f"{100 - specificity} % честных. Какова вероятность, что помеченная операция "
            "действительно мошенническая?"
        ),
        value=round(value, 1),
        tolerance=0.5,
        input_hint=_PERCENT_HINT,
        unit="%",
    )


@family(
    "stats.variance_sum",
    title="Дисперсия суммы независимых величин",
    competency="statistics",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.3,
    status=ItemFamilyStatus.PILOT,
)
def variance_sum(rng: Random) -> GeneratedItem:
    """Для независимых величин складываются дисперсии, а не стандартные отклонения."""
    first = rng.choice([3, 5, 6, 8, 9, 12])
    second = rng.choice([4, 5, 8, 10, 12, 15])
    sign = rng.choice(["+", "−"])
    value = math.sqrt(first**2 + second**2)
    return numeric(
        prompt=(
            f"Время обработки заявки складывается из двух независимых этапов со стандартными "
            f"отклонениями {first} и {second} минут. Каково стандартное отклонение величины "
            f"X {sign} Y, где X и Y — длительности этапов?"
        ),
        value=round(value, 2),
        tolerance=0.05,
        input_hint="Число, округлите до двух знаков после запятой",
        unit="мин",
    )


_SIGNIFICANCE_OPTIONS = (
    "Различие статистически значимо: |z| > 1,96",
    "Различие не значимо: |z| < 1,96",
    "Различие значимо, потому что конверсия B выше",
    "Без p-value из таблицы распределения ничего сказать нельзя",
)


@family(
    "stats.ab_ztest",
    title="Значимость различия конверсий (z-тест)",
    competency="statistics",
    grade="senior",
    response_format=_CHOICE,
    time_limit=180,
    discrimination=1.4,
    difficulty_offset=-0.3,
)
def ab_ztest(rng: Random) -> GeneratedItem:
    """Двухвыборочный z-тест для долей с объединённой оценкой p."""
    while True:
        size = rng.choice([2000, 4000, 5000, 8000])
        base = rng.uniform(0.04, 0.12)
        lift = rng.uniform(0.0, 0.03)
        conv_a = round(size * base)
        conv_b = round(size * (base + lift))
        pooled = (conv_a + conv_b) / (2 * size)
        z = (conv_b / size - conv_a / size) / math.sqrt(pooled * (1 - pooled) * (2 / size))
        if abs(abs(z) - 1.96) > 0.25 and conv_b > conv_a:
            break
    correct = _SIGNIFICANCE_OPTIONS[0] if abs(z) > 1.96 else _SIGNIFICANCE_OPTIONS[1]
    table = DataTable(
        title="Результаты эксперимента",
        columns=("Группа", "Пользователи", "Покупки"),
        rows=(("A", size, conv_a), ("B", size, conv_b)),
    )
    return single_choice(
        rng,
        prompt=(
            "Используйте двухсторонний z-тест для долей с объединённой оценкой конверсии, "
            "α = 0,05. Какой вывод верен?"
        ),
        tables=[table],
        correct=correct,
        distractors=[option for option in _SIGNIFICANCE_OPTIONS if option != correct],
        params={"z": round(z, 3)},
    )


@family(
    "metrics.funnel_conversion",
    title="Сквозная конверсия воронки",
    competency="product_metrics",
    grade="intern",
    response_format=_NUMERIC,
    time_limit=90,
    discrimination=1.0,
)
def funnel_conversion(rng: Random) -> GeneratedItem:
    """Сквозная конверсия — последний шаг, делённый на первый, а не произведение шагов «на глаз»."""
    visits = rng.randint(8, 30) * 1000
    cart = int(visits * rng.uniform(0.15, 0.35))
    checkout = int(cart * rng.uniform(0.3, 0.6))
    paid = int(checkout * rng.uniform(0.5, 0.85))
    table = DataTable(
        title="Воронка за день",
        columns=("Шаг", "Пользователи"),
        rows=(
            ("Открыли каталог", visits),
            ("Добавили в корзину", cart),
            ("Начали оформление", checkout),
            ("Оплатили", paid),
        ),
    )
    return numeric(
        prompt="Какова сквозная конверсия из открытия каталога в оплату?",
        value=round(paid / visits * 100, 1),
        tolerance=0.1,
        input_hint=_PERCENT_HINT,
        tables=[table],
        unit="%",
    )


@family(
    "metrics.retention",
    title="Retention когорты",
    competency="product_metrics",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=90,
    discrimination=1.1,
)
def retention(rng: Random) -> GeneratedItem:
    """Retention дня N считается от размера когорты, а не от активных накануне."""
    cohort = rng.randint(800, 5000)
    day1 = int(cohort * rng.uniform(0.35, 0.55))
    day7 = int(day1 * rng.uniform(0.35, 0.6))
    table = DataTable(
        title="Когорта установок 1 сентября",
        columns=("День", "Активные пользователи"),
        rows=((0, cohort), (1, day1), (7, day7)),
    )
    return numeric(
        prompt="Каков retention седьмого дня этой когорты?",
        value=round(day7 / cohort * 100, 1),
        tolerance=0.1,
        input_hint=_PERCENT_HINT,
        tables=[table],
        unit="%",
    )


@family(
    "metrics.arppu",
    title="ARPU и ARPPU",
    competency="product_metrics",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=90,
    discrimination=1.2,
    difficulty_offset=0.2,
)
def arppu(rng: Random) -> GeneratedItem:
    """ARPPU делит выручку на платящих, ARPU — на всех пользователей."""
    users = rng.randint(10, 50) * 1000
    paying = int(users * rng.uniform(0.02, 0.08))
    revenue = paying * rng.randint(3, 15) * 100
    metric = rng.choice(["ARPPU", "ARPU"])
    value = revenue / paying if metric == "ARPPU" else revenue / users
    return numeric(
        prompt=(
            f"За месяц в приложении было {users} активных пользователей, из них {paying} что-то "
            f"купили. Выручка — {revenue} ₽. Чему равен {metric} в рублях?"
        ),
        value=round(value, 2),
        tolerance=0.5,
        input_hint="Сумма в рублях, можно с копейками",
        unit="₽",
    )


@family(
    "metrics.ltv_churn",
    title="LTV через ежемесячный отток",
    competency="product_metrics",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.3,
)
def ltv_churn(rng: Random) -> GeneratedItem:
    """При постоянном оттоке средний срок жизни — 1 / churn, LTV = ARPU / churn."""
    arpu = rng.choice([150, 200, 300, 450, 600])
    churn = rng.choice([4, 5, 8, 10, 12, 15])
    return numeric(
        prompt=(
            f"Подписка приносит {arpu} ₽ с пользователя в месяц, ежемесячно уходит {churn} % "
            "подписчиков, отток постоянный. Оцените LTV пользователя в рублях."
        ),
        value=round(arpu / (churn / 100), 2),
        tolerance=1.0,
        input_hint="Сумма в рублях",
        unit="₽",
    )


@family(
    "metrics.ab_sample_scaling",
    title="Размер выборки и MDE",
    competency="product_metrics",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=90,
    discrimination=1.4,
    difficulty_offset=0.3,
)
def ab_sample_scaling(rng: Random) -> GeneratedItem:
    """Нужный размер выборки обратно пропорционален квадрату минимального детектируемого эффекта."""
    factor = rng.choice([2, 3, 4])
    return numeric(
        prompt=(
            f"Эксперимент рассчитан на минимальный детектируемый эффект 2 п. п. Продакт хочет "
            f"ловить эффект в {factor} раза меньше при той же мощности и α. Во сколько раз "
            "должна вырасти выборка в каждой группе?"
        ),
        value=factor**2,
    )


def _sales_frame(rng: Random, *, with_gaps: bool = False) -> DataTable:
    """Небольшой DataFrame с продажами по городам; при with_gaps часть значений пустая."""
    cities = rng.sample(_CITIES, 3)
    rows = []
    for index in range(rng.randint(7, 9)):
        amount: int | None = rng.randint(1, 30) * 100
        discount: int | None = rng.choice([0, 5, 10, 15])
        if with_gaps and rng.random() < 0.3:
            amount = None
        if with_gaps and rng.random() < 0.25:
            discount = None
        rows.append((index, rng.choice(cities), amount, discount))
    return DataTable(
        title="df", columns=("order_id", "city", "amount", "discount"), rows=tuple(rows)
    )


def _frame_code(table: DataTable) -> str:
    """Код создания DataFrame, совпадающий с таблицей в условии."""
    columns = {name: [row[index] for row in table.rows] for index, name in enumerate(table.columns)}
    body = ",\n".join(f"    {name!r}: {values!r}" for name, values in columns.items())
    return f"import pandas as pd\n\ndf = pd.DataFrame({{\n{body}\n}})"


@family(
    "pandas.value_counts",
    title="value_counts",
    competency="data_wrangling",
    grade="intern",
    response_format=_NUMERIC,
    time_limit=75,
    discrimination=1.0,
)
def value_counts(rng: Random) -> GeneratedItem:
    """value_counts сортирует по убыванию частоты: iloc[0] — число строк самого частого значения."""
    table = _sales_frame(rng)
    counts: defaultdict[str, int] = defaultdict(int)
    for row in table.rows:
        counts[row[1]] += 1
    return numeric(
        prompt="Что вернёт выражение `df['city'].value_counts().iloc[0]` для таблицы df?",
        value=max(counts.values()),
        tables=[table],
    )


@family(
    "pandas.groupby_mean",
    title="groupby и mean",
    competency="data_wrangling",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.2,
)
def groupby_mean(rng: Random) -> GeneratedItem:
    """Среднее по группе: делим сумму группы на число её строк."""
    table = _sales_frame(rng)
    groups: defaultdict[str, list[int]] = defaultdict(list)
    for row in table.rows:
        groups[row[1]].append(row[2])
    city = rng.choice(sorted(groups))
    expression = f"df.groupby('city')['amount'].mean()['{city}']"
    return numeric(
        prompt=f"Что вернёт выражение `{expression}`?",
        value=round(sum(groups[city]) / len(groups[city]), 2),
        tolerance=0.01,
        input_hint="Число, можно с двумя знаками после запятой",
        tables=[table],
        check=PythonCheck(f"{_frame_code(table)}\nprint(round({expression}, 2))"),
    )


@family(
    "pandas.dropna_rows",
    title="dropna и пропуски",
    competency="data_wrangling",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=100,
    discrimination=1.2,
    difficulty_offset=0.2,
)
def dropna_rows(rng: Random) -> GeneratedItem:
    """dropna без subset удаляет строку при пропуске в любом столбце, с subset — только в указанных."""
    table = _sales_frame(rng, with_gaps=True)
    use_subset = rng.random() < 0.5
    if use_subset:
        expression = "len(df.dropna(subset=['amount']))"
        value = sum(1 for row in table.rows if row[2] is not None)
    else:
        expression = "len(df.dropna())"
        value = sum(1 for row in table.rows if row[2] is not None and row[3] is not None)
    return numeric(
        prompt=f"Пустые ячейки — это NaN. Что вернёт выражение `{expression}`?",
        value=value,
        tables=[table],
        check=PythonCheck(f"{_frame_code(table)}\nprint({expression})"),
    )


@family(
    "pandas.merge_left_rows",
    title="Число строк после merge(how='left')",
    competency="data_wrangling",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=150,
    discrimination=1.4,
)
def merge_left_rows(rng: Random) -> GeneratedItem:
    """Левое соединение размножает строки при повторах ключа справа и сохраняет строки без пары."""
    left_keys = rng.sample(range(1, 9), rng.randint(4, 5))
    right_keys = [rng.choice([*left_keys, 9, 10]) for _ in range(rng.randint(5, 7))]
    left = DataTable(
        title="users",
        columns=("user_id", "city"),
        rows=tuple((key, rng.choice(_CITIES)) for key in left_keys),
    )
    right = DataTable(
        title="orders",
        columns=("user_id", "amount"),
        rows=tuple((key, rng.randint(1, 40) * 100) for key in right_keys),
    )
    value = sum(max(1, right_keys.count(key)) for key in left_keys)
    return numeric(
        prompt="Сколько строк будет в результате `users.merge(orders, on='user_id', how='left')`?",
        value=value,
        tables=[left, right],
    )


def _confusion(rng: Random) -> tuple[int, int, int, int]:
    """Матрица ошибок бинарного классификатора: TP, FP, FN, TN."""
    return rng.randint(40, 200), rng.randint(5, 80), rng.randint(5, 80), rng.randint(300, 900)


def _confusion_table(tp: int, fp: int, fn: int, tn: int) -> DataTable:
    """Матрица ошибок в виде таблицы."""
    return DataTable(
        title="Матрица ошибок",
        columns=("", "Предсказано: 1", "Предсказано: 0"),
        rows=(("Факт: 1", tp, fn), ("Факт: 0", fp, tn)),
    )


@family(
    "ml.precision_recall",
    title="Precision и recall",
    competency="ml_metrics",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=100,
    discrimination=1.3,
)
def precision_recall(rng: Random) -> GeneratedItem:
    """Precision — доля верных среди предсказанных единиц, recall — среди фактических."""
    tp, fp, fn, tn = _confusion(rng)
    metric = rng.choice(["precision", "recall"])
    value = tp / (tp + fp) if metric == "precision" else tp / (tp + fn)
    return numeric(
        prompt=f"Чему равен {metric} модели? Ответ — в процентах.",
        value=round(value * 100, 1),
        tolerance=0.1,
        input_hint=_PERCENT_HINT,
        tables=[_confusion_table(tp, fp, fn, tn)],
        unit="%",
    )


@family(
    "ml.f1_score",
    title="F1-мера",
    competency="ml_metrics",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.3,
)
def f1_score(rng: Random) -> GeneratedItem:
    """F1 — гармоническое среднее precision и recall, а не арифметическое."""
    tp, fp, fn, tn = _confusion(rng)
    value = 2 * tp / (2 * tp + fp + fn)
    return numeric(
        prompt="Чему равна F1-мера модели? Ответ — доля от 0 до 1.",
        value=round(value, 3),
        tolerance=0.005,
        input_hint="Число от 0 до 1, три знака после запятой",
        tables=[_confusion_table(tp, fp, fn, tn)],
    )


@family(
    "ml.imbalanced_accuracy",
    title="Accuracy на несбалансированных данных",
    competency="ml_metrics",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=90,
    discrimination=1.2,
    difficulty_offset=-0.3,
)
def imbalanced_accuracy(rng: Random) -> GeneratedItem:
    """Константный классификатор на редком классе показывает высокую accuracy при нулевом recall."""
    total = rng.choice([10000, 20000, 50000])
    rate = rng.choice([0.5, 1, 2, 3, 4])
    return numeric(
        prompt=(
            f"В выборке из {total} транзакций мошеннических {format_number(rate)} %. Модель для "
            "любой транзакции предсказывает «честная». Какова её accuracy в процентах?"
        ),
        value=round(100 - rate, 1),
        tolerance=0.1,
        input_hint=_PERCENT_HINT,
        unit="%",
    )


_FITTING_OPTIONS = ("Переобучение", "Недообучение", "Модель обучается нормально", "Утечка таргета")


@family(
    "ml.learning_curves",
    title="Диагностика по кривым обучения",
    competency="ml_metrics",
    grade="junior",
    response_format=_CHOICE,
    time_limit=100,
    discrimination=1.1,
)
def learning_curves(rng: Random) -> GeneratedItem:
    """Расходящиеся train и validation — переобучение, обе высокие — недообучение."""
    variant = rng.choice(["overfit", "underfit", "good"])
    epochs = 6
    train = []
    valid = []
    start = rng.uniform(0.9, 1.2)
    for epoch in range(epochs):
        if variant == "overfit":
            train.append(start * 0.55**epoch)
            valid.append(start * 0.8 + (epoch - 2) ** 2 * 0.04)
        elif variant == "underfit":
            train.append(start - epoch * 0.01)
            valid.append(start + 0.02 - epoch * 0.01)
        else:
            train.append(start * 0.7**epoch)
            valid.append(start * 0.72**epoch + 0.03)
    rows = tuple(
        (epoch + 1, round(t, 3), round(v, 3))
        for epoch, (t, v) in enumerate(zip(train, valid, strict=True))
    )
    correct = {
        "overfit": _FITTING_OPTIONS[0],
        "underfit": _FITTING_OPTIONS[1],
        "good": _FITTING_OPTIONS[2],
    }[variant]
    return single_choice(
        rng,
        prompt="По значениям функции потерь на обучении и валидации определите, что происходит с моделью.",
        tables=[
            DataTable(title="Loss по эпохам", columns=("Эпоха", "train", "validation"), rows=rows)
        ],
        correct=correct,
        distractors=[option for option in _FITTING_OPTIONS if option != correct],
        params={"variant": variant},
    )
