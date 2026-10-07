import json
import math
from datetime import date, timedelta
from pathlib import Path
from random import Random
from typing import Any

OUTPUT = Path(__file__).resolve().parents[1] / "app" / "data" / "participants.json"
SEED = 2026
PARTICIPANTS = 260

DISCIPLINES = (
    "продуктовое программирование",
    "алгоритмическое программирование",
    "программирование беспилотных авиационных систем",
    "программирование робототехники",
    "информационная безопасность",
)
LEVELS = ("international", "national", "interregional", "regional", "local")
REGIONS = (
    "Москва",
    "Санкт-Петербург",
    "Республика Татарстан",
    "Новосибирская область",
    "Свердловская область",
    "Нижегородская область",
    "Томская область",
    "Краснодарский край",
    "Самарская область",
    "Республика Башкортостан",
)
RANKS = (None, None, "3 разряд", "2 разряд", "1 разряд", "КМС", "МС")
MALE = ("Алексей", "Артём", "Дмитрий", "Иван", "Кирилл", "Максим", "Никита", "Павел", "Тимур")
FEMALE = ("Анна", "Алина", "Дарья", "Екатерина", "Мария", "Полина", "София", "Ксения", "Диана")
LAST = (
    ("Орлов", "Орлова"),
    ("Белов", "Белова"),
    ("Соколов", "Соколова"),
    ("Лебедев", "Лебедева"),
    ("Волков", "Волкова"),
    ("Ким", "Ким"),
    ("Гарипов", "Гарипова"),
    ("Фролов", "Фролова"),
    ("Зайцев", "Зайцева"),
)
EVENT_NAMES = (
    "Кубок «Северное сияние»",
    "Турнир «Цифровой рубеж»",
    "Открытые соревнования «Код без границ»",
    "Кубок «Волжская волна»",
    "Турнир «Сибирский алгоритм»",
    "Соревнования «Байкальский хакатон»",
    "Кубок «Уральский кремний»",
    "Турнир «Балтийский кейс»",
    "Соревнования «Южный вектор»",
    "Кубок «Полярный код»",
)
LEVEL_TITLES = {
    "international": "международные соревнования",
    "national": "всероссийские соревнования",
    "interregional": "межрегиональные соревнования",
    "regional": "региональный этап",
    "local": "городские соревнования",
}
TEAM_NAMES = (
    "Bit Rebels",
    "Нулевой указатель",
    "Kernel Panic",
    "Сеть 42",
    "Байт и Байтина",
    "Stack Overflowers",
)


def _events(rng: Random) -> list[dict[str, object]]:
    """Каталог вымышленных соревнований 2022–2026 годов."""
    events = []
    for index in range(70):
        level = rng.choices(LEVELS, weights=(1, 3, 3, 5, 4))[0]
        discipline = rng.choice(DISCIPLINES)
        held = date(2022, 1, 15) + timedelta(days=rng.randint(0, 4 * 365 + 200))
        events.append(
            {
                "event_id": f"EV-{held.year}-{index + 1:03d}",
                "event_name": f"{rng.choice(EVENT_NAMES)}: {LEVEL_TITLES[level]}, {discipline}",
                "event_level": level,
                "discipline": discipline,
                "event_date": held.isoformat(),
                "is_online": rng.random() < 0.35,
                "team_event": discipline in DISCIPLINES[:3] and rng.random() < 0.6,
                "participants_total": rng.choice((24, 40, 60, 80, 120, 200, 320)),
            }
        )
    return events


def _result(place: int, total: int) -> str:
    """Статус результата по месту: без иерархии соревнований, только итог участия."""
    if place == 1:
        return "winner"
    if place <= 3:
        return "prize"
    if place <= max(4, total // 10):
        return "finalist"
    return "participant"


def build() -> list[dict[str, Any]]:
    """Участники с историей, зависящей от скрытой «силы»: сильные чаще занимают места.

    У части участников истории нет вовсе — это штатное состояние «привязан без
    участий», которое платформа обязана показывать корректно.
    """
    rng = Random(SEED)
    events = _events(rng)
    participants = []
    for index in range(1, PARTICIPANTS + 1):
        strength = rng.gauss(0, 1)
        count = (
            0
            if rng.random() < 0.15
            else max(1, min(10, round(rng.gauss(2.5 + strength * 1.5, 1.5))))
        )
        history = []
        for event in rng.sample(events, k=count):
            total = int(str(event["participants_total"]))
            quantile = 1 / (1 + math.exp(-(strength + rng.gauss(0, 0.9)) * 1.2))
            place = max(1, round(total * (1 - quantile) ** 1.15))
            team = bool(event["team_event"])
            history.append(
                {
                    "event_id": event["event_id"],
                    "event_name": event["event_name"],
                    "event_level": event["event_level"],
                    "discipline": event["discipline"],
                    "event_date": event["event_date"],
                    "participation_format": "team" if team else "individual",
                    "team_name": rng.choice(TEAM_NAMES) if team else None,
                    "team_role": rng.choice(("капитан", "участник", "участник")) if team else None,
                    "place": min(place, total),
                    "participants_total": total,
                    "result_status": _result(min(place, total), total),
                    "is_online": event["is_online"],
                    "rating_points": round(max(0.0, 100 * (1 - (place - 1) / total)), 1),
                    "protocol_url": f"https://fsp-registry.example/protocols/{event['event_id']}",
                }
            )
        history.sort(key=lambda item: str(item["event_date"]), reverse=True)
        female = rng.random() < 0.4
        first = rng.choice(FEMALE if female else MALE)
        last = rng.choice(LAST)[1 if female else 0]
        participants.append(
            {
                "id": f"fsp-{index:06d}",
                "login": f"fsp{index:06d}",
                "full_name": f"{first} {last}",
                "region": rng.choice(REGIONS),
                "sport_rank": rng.choice(RANKS) if count else None,
                "achievements": history,
            }
        )
    return participants


def main() -> None:
    """Пишет participants.json. Сид фиксирован, поэтому файл воспроизводим."""
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Участников: {PARTICIPANTS}, файл: {OUTPUT}")


if __name__ == "__main__":
    main()
