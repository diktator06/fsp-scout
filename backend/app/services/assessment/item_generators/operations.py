import ipaddress
from random import Random

from app.models.assessment import ItemFamilyStatus, ResponseFormat
from app.services.assessment.item_generators.base import (
    GeneratedItem,
    PythonCheck,
    family,
    numeric,
    single_choice,
)

_CHOICE = ResponseFormat.SINGLE_CHOICE
_NUMERIC = ResponseFormat.NUMERIC


@family(
    "qa.boundary_values",
    title="Анализ граничных значений",
    competency="test_design",
    grade="intern",
    response_format=_NUMERIC,
    time_limit=90,
    discrimination=1.0,
)
def boundary_values(rng: Random) -> GeneratedItem:
    """Трёхточечный анализ: для каждой границы — значение до, на и после неё."""
    fields = rng.sample(
        [
            ("возраст", 18, 65),
            ("стаж в годах", 0, 40),
            ("количество товаров", 1, 99),
            ("сумма заказа", 500, 50000),
            ("рейтинг", 1, 5),
        ],
        rng.randint(1, 3),
    )
    description = "\n".join(
        f"• {name}: целое число от {low} до {high} включительно" for name, low, high in fields
    )
    return numeric(
        prompt=(
            "Форма проверяет поля ниже, каждое независимо. Сколько значений нужно проверить "
            "трёхточечным анализом граничных значений (для каждой границы: на единицу меньше, "
            "сама граница и на единицу больше), если не объединять проверки разных полей?\n\n"
            f"{description}"
        ),
        value=6 * len(fields),
    )


@family(
    "qa.equivalence_classes",
    title="Классы эквивалентности",
    competency="test_design",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=120,
    discrimination=1.2,
)
def equivalence_classes(rng: Random) -> GeneratedItem:
    """Каждый диапазон правила — отдельный класс, плюс класс некорректных значений."""
    thresholds = sorted(rng.sample([1000, 3000, 5000, 10000, 20000, 50000], rng.randint(2, 4)))
    discounts = sorted(rng.sample([3, 5, 7, 10, 12, 15, 20], len(thresholds)))
    lines = [f"• до {thresholds[0] - 1} ₽ — без скидки"]
    for index, threshold in enumerate(thresholds):
        upper = f"до {thresholds[index + 1] - 1} ₽" if index + 1 < len(thresholds) else "и выше"
        lines.append(f"• от {threshold} ₽ {upper} — скидка {discounts[index]} %")
    lines.append("• отрицательная или нулевая сумма — ошибка «Некорректная сумма»")
    return numeric(
        prompt=(
            "Сколько классов эквивалентности, включая класс некорректных значений, нужно "
            "проверить для правила расчёта скидки?\n\n" + "\n".join(lines)
        ),
        value=len(thresholds) + 2,
    )


@family(
    "qa.pairwise_minimum",
    title="Минимальный набор попарного тестирования",
    competency="test_design",
    grade="senior",
    response_format=_NUMERIC,
    time_limit=150,
    discrimination=1.3,
)
def pairwise_minimum(rng: Random) -> GeneratedItem:
    """Для трёх параметров минимум пар — произведение двух наибольших размеров (оно достижимо)."""
    pools = {
        "Браузер": ["Chrome", "Firefox", "Safari", "Edge", "Яндекс"],
        "ОС": ["Windows", "macOS", "Linux", "Android"],
        "Язык": ["ru", "en", "kk"],
        "Оплата": ["Карта", "СБП", "Наличные"],
        "Доставка": ["Курьер", "Пункт выдачи"],
    }
    names = rng.sample(sorted(pools), 3)
    sizes = {name: rng.randint(2, len(pools[name])) for name in names}
    ordered = sorted(sizes.values(), reverse=True)
    description = "\n".join(f"• {name}: {', '.join(pools[name][: sizes[name]])}" for name in names)
    return numeric(
        prompt=(
            "Какое наименьшее число тестов покрывает все пары значений любых двух параметров "
            f"(pairwise)?\n\n{description}"
        ),
        value=ordered[0] * ordered[1],
        params={"sizes": sizes},
    )


@family(
    "net.cidr_hosts",
    title="Число адресов хостов в подсети",
    competency="networking",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=90,
    discrimination=1.2,
)
def cidr_hosts(rng: Random) -> GeneratedItem:
    """Адресов хостов в IPv4-подсети /n: 2^(32−n) − 2 (адрес сети и широковещательный)."""
    prefix = rng.randint(22, 29)
    network = ipaddress.ip_network(
        f"10.{rng.randint(0, 200)}.{rng.randint(0, 3) * 64}.0/{prefix}", strict=False
    )
    return numeric(
        prompt=f"Сколько адресов можно выдать хостам в подсети {network}?",
        value=2 ** (32 - prefix) - 2,
        check=PythonCheck(
            f"import ipaddress\nprint(len(list(ipaddress.ip_network('{network}').hosts())))"
        ),
    )


@family(
    "net.subnet_membership",
    title="Принадлежность адресов подсети",
    competency="networking",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=150,
    discrimination=1.4,
    difficulty_offset=-0.2,
)
def subnet_membership(rng: Random) -> GeneratedItem:
    """Адрес принадлежит подсети, если совпадают первые n бит."""
    prefix = rng.choice([25, 26, 27, 28])
    block = 2 ** (32 - prefix)
    third = rng.randint(0, 250)
    start = rng.randrange(0, 256, block)
    network = ipaddress.ip_network(f"192.168.{third}.{start}/{prefix}")
    addresses = []
    for _ in range(6):
        if rng.random() < 0.5:
            last = rng.randint(start, start + block - 1)
        else:
            last = (start + block + rng.randint(0, 40)) % 256
        addresses.append(ipaddress.ip_address(f"192.168.{third}.{last}"))
    value = sum(1 for address in addresses if address in network)
    listing = ", ".join(str(address) for address in addresses)
    return numeric(
        prompt=f"Сколько адресов из списка принадлежат подсети {network}?",
        value=value,
        code=listing,
        code_language="text",
        check=PythonCheck(
            "import ipaddress\n"
            f"net = ipaddress.ip_network('{network}')\n"
            f"print(sum(ipaddress.ip_address(a) in net for a in {[str(a) for a in addresses]!r}))"
        ),
    )


_PORTS = (
    ("SSH", "22"),
    ("HTTPS", "443"),
    ("PostgreSQL", "5432"),
    ("Redis", "6379"),
    ("DNS", "53"),
    ("SMTP (отправка почты между серверами)", "25"),
    ("HTTP", "80"),
)


@family(
    "net.default_ports",
    title="Стандартные порты сервисов",
    competency="networking",
    grade="intern",
    response_format=_CHOICE,
    time_limit=45,
    discrimination=0.9,
)
def default_ports(rng: Random) -> GeneratedItem:
    """Порт по умолчанию для распространённого сервиса."""
    service, correct = rng.choice(_PORTS)
    others = [port for _, port in _PORTS if port != correct]
    rng.shuffle(others)
    return single_choice(
        rng,
        prompt=f"Какой порт по умолчанию использует {service}?",
        correct=correct,
        distractors=others,
    )


def _permission_string(octal: str) -> str:
    """Строка прав вида rwxr-x--- по восьмеричной записи."""
    flags = ""
    for digit in octal:
        value = int(digit)
        flags += (
            ("r" if value & 4 else "-") + ("w" if value & 2 else "-") + ("x" if value & 1 else "-")
        )
    return flags


@family(
    "linux.chmod_octal",
    title="Права доступа в восьмеричной записи",
    competency="linux",
    grade="junior",
    response_format=_NUMERIC,
    time_limit=90,
    discrimination=1.2,
)
def chmod_octal(rng: Random) -> GeneratedItem:
    """Каждая тройка rwx — сумма r=4, w=2, x=1."""
    octal = f"{rng.choice([7, 6, 5])}{rng.choice([7, 5, 4, 0])}{rng.choice([5, 4, 0])}"
    name = rng.choice(["deploy.sh", "config.yml", "backup.tar", "app.log"])
    return numeric(
        prompt=(
            f"ls -l показывает для файла {name} права -{_permission_string(octal)}. Какое число "
            "нужно передать chmod, чтобы выставить такие же права?"
        ),
        value=int(octal),
        input_hint="Три цифры восьмеричной записи, например 644",
    )


_WEEKDAYS = {"1-5": 5, "*": 7, "1,3,5": 3, "6,0": 2}


@family(
    "linux.cron_runs",
    title="Расписание cron",
    competency="linux",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=150,
    discrimination=1.3,
)
def cron_runs(rng: Random) -> GeneratedItem:
    """Число запусков = запусков в час × часов × дней недели."""
    step = rng.choice([5, 10, 15, 20, 30])
    start_hour = rng.randint(7, 10)
    end_hour = start_hour + rng.randint(4, 9)
    days, days_count = rng.choice(sorted(_WEEKDAYS.items()))
    expression = f"*/{step} {start_hour}-{end_hour} * * {days}"
    value = (60 // step) * (end_hour - start_hour + 1) * days_count
    return numeric(
        prompt=f"Сколько раз за неделю выполнится задача с расписанием `{expression}`?",
        value=value,
        code=f"{expression} /usr/local/bin/sync-reports",
        code_language="bash",
    )


@family(
    "linux.grep_pipeline",
    title="Конвейер grep, sort, uniq, wc",
    competency="linux",
    grade="middle",
    response_format=_NUMERIC,
    time_limit=150,
    discrimination=1.2,
    status=ItemFamilyStatus.PILOT,
)
def grep_pipeline(rng: Random) -> GeneratedItem:
    """`grep | cut | sort | uniq | wc -l` считает различные значения среди отфильтрованных строк."""
    levels = ["INFO", "WARN", "ERROR"]
    services = rng.sample(["auth", "billing", "search", "mailer", "gateway"], 4)
    lines = [
        f"{rng.choice(levels)} {rng.choice(services)} request handled"
        for _ in range(rng.randint(8, 11))
    ]
    level = rng.choice(["WARN", "ERROR"])
    if not any(line.startswith(level) for line in lines):
        lines[0] = f"{level} {services[0]} request handled"
    value = len({line.split()[1] for line in lines if line.startswith(level)})
    return numeric(
        prompt=f"Что выведет команда `grep '^{level}' app.log | cut -d' ' -f2 | sort | uniq | wc -l` для файла ниже?",
        value=value,
        code="\n".join(lines),
        code_language="text",
    )
