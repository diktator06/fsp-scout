from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from random import Random

from app.services.assessment.irt import AbilityEstimate, ItemParameters, information

ALGORITHM_VERSION = "cat-1.0"


@dataclass(frozen=True, slots=True)
class EngineConfig:
    """Параметры адаптивного теста. Значения обоснованы в docs/ASSESSMENT.md."""

    min_items: int = 12
    max_items: int = 20
    confidence_z: float = 1.64
    target_se: float = 0.30
    randomesque: int = 4
    max_exposure_rate: float = 0.35
    exposure_penalty: float = 2.0
    seen_penalty: float = 0.5
    pilot_items: int = 1


EXPRESS_CONFIG = EngineConfig(min_items=6, max_items=8, target_se=0.45, pilot_items=0)


@dataclass(frozen=True, slots=True)
class PoolItem:
    """Семейство-кандидат на показ."""

    family_id: int
    code: str
    competency: str
    params: ItemParameters
    exposure_rate: float = 0.0
    seen_before: bool = False


def competency_deficits(
    blueprint: Mapping[str, float], administered: Sequence[str]
) -> list[tuple[str, float]]:
    """Насколько каждая компетенция недобрана относительно blueprint, от самой недобранной.

    Дефицит считается как «должно было быть показано к следующему заданию» минус
    «показано»: target × (n + 1) − count. Так компетенция с маленьким весом рано
    или поздно тоже получает задание, а не проигрывает вечно тяжёлым осям.
    """
    upcoming = len(administered) + 1
    counts = dict.fromkeys(blueprint, 0)
    for code in administered:
        if code in counts:
            counts[code] += 1
    deficits = [(code, weight * upcoming - counts[code]) for code, weight in blueprint.items()]
    return sorted(deficits, key=lambda pair: (-pair[1], pair[0]))


def _effective_information(item: PoolItem, theta: float, config: EngineConfig) -> float:
    """Информация задания с поправкой на экспозицию и на прошлые попытки кандидата.

    Семейства, которые показываются чаще порога, получают штраф. Это упрощённый
    вариант Sympson–Hetter: самые информативные задания не становятся
    «общеизвестными» только потому, что всем подходят.

    Семейства, которые кандидат уже видел в прошлых сессиях, не исключаются, а
    понижаются в приоритете. Экземпляр всё равно будет новым, так что запомненный
    ответ не поможет, а в небольшом банке полное исключение оставило бы повторному
    тесту только плохо подходящие по сложности задания.
    """
    overshoot = max(0.0, item.exposure_rate - config.max_exposure_rate)
    weight = max(0.05, 1.0 - config.exposure_penalty * overshoot)
    if item.seen_before:
        weight *= config.seen_penalty
    return information(theta, item.params) * weight


def select_next_item(
    pool: Sequence[PoolItem],
    blueprint: Mapping[str, float],
    administered_competencies: Sequence[str],
    estimate: AbilityEstimate,
    rng: Random,
    config: EngineConfig,
) -> PoolItem | None:
    """Выбирает следующее семейство.

    1. Компетенция — с наибольшим дефицитом относительно blueprint среди тех, где
       ещё остались доступные семейства.
    2. Внутри компетенции семейства ранжируются по информации Фишера в текущей θ̂
       с учётом штрафа за экспозицию.
    3. Случайное из нескольких лучших (randomesque). Это защищает банк: даже при
       одинаковых ответах двое кандидатов пойдут по разным путям. В маленькой
       компетенции выбор сужается до половины семейств, чтобы не платить точностью
       за случайность там, где выбирать почти не из чего.
    """
    by_competency: dict[str, list[PoolItem]] = {}
    for item in pool:
        by_competency.setdefault(item.competency, []).append(item)

    for competency, _ in competency_deficits(blueprint, administered_competencies):
        candidates = by_competency.get(competency)
        if not candidates:
            continue
        ranked = sorted(
            candidates,
            key=lambda item: (-_effective_information(item, estimate.theta, config), item.code),
        )
        width = max(1, min(config.randomesque, len(ranked) // 2))
        return rng.choice(ranked[:width])

    leftovers = [item for item in pool if item.competency not in blueprint]
    return rng.choice(leftovers) if leftovers else None


def should_stop(
    *,
    scored_items: int,
    estimate: AbilityEstimate,
    cut: float,
    config: EngineConfig,
    pool_exhausted: bool,
) -> bool:
    """Правило остановки классификационного CAT.

    Тест заканчивается, когда доверительный интервал θ уверенно лежит по одну сторону
    порога заявленного грейда (|θ̂ − порог| ≥ z·SE), либо когда SE стала достаточно
    малой. Нижняя граница длины теста обеспечивает покрытие компетенций, верхняя
    ограничивает время кандидата.
    """
    if pool_exhausted or scored_items >= config.max_items:
        return True
    if scored_items < config.min_items:
        return False
    decided = abs(estimate.theta - cut) >= config.confidence_z * estimate.se
    return decided or estimate.se <= config.target_se
