from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

THETA_MIN = -4.0
THETA_MAX = 4.0
GRID_POINTS = 121

FINE_GRID_POINTS = 801

THETA_GRID: NDArray[np.float64] = np.linspace(THETA_MIN, THETA_MAX, GRID_POINTS)
FINE_THETA_GRID: NDArray[np.float64] = np.linspace(THETA_MIN, THETA_MAX, FINE_GRID_POINTS)
_STANDARD_NORMAL = np.exp(-0.5 * THETA_GRID**2)
PRIOR: NDArray[np.float64] = _STANDARD_NORMAL / _STANDARD_NORMAL.sum()


@dataclass(frozen=True, slots=True)
class ItemParameters:
    """Параметры трёхпараметрической логистической модели (3PL).

    a — дискриминативность (насколько резко растёт вероятность успеха около b),
    b — сложность по шкале способностей, c — нижняя асимптота (угадывание).
    """

    a: float
    b: float
    c: float = 0.0


@dataclass(frozen=True, slots=True)
class AbilityEstimate:
    """Оценка способности θ и её стандартная ошибка."""

    theta: float
    se: float


def probability(theta: float | NDArray[np.float64], item: ItemParameters) -> NDArray[np.float64]:
    """Вероятность верного ответа при способности θ: c + (1 − c) / (1 + e^(−a(θ − b)))."""
    logistic = 1.0 / (1.0 + np.exp(-item.a * (np.asarray(theta, dtype=np.float64) - item.b)))
    return item.c + (1.0 - item.c) * logistic


def information(theta: float, item: ItemParameters) -> float:
    """Информация Фишера задания в точке θ.

    Формула для 3PL: I(θ) = a² · (P − c)² / (1 − c)² · Q / P. Максимум лежит чуть
    правее b: угадывание снижает ценность задания для слабых кандидатов.
    """
    p = float(probability(theta, item))
    q = 1.0 - p
    if p <= item.c or p >= 1.0:
        return 0.0
    return item.a**2 * ((p - item.c) ** 2 / (1.0 - item.c) ** 2) * (q / p)


def estimate_ability(responses: Sequence[tuple[ItemParameters, float]]) -> AbilityEstimate:
    """EAP-оценка θ по ответам на сетке квадратуры с априорным N(0, 1).

    Апостериорное распределение — априорное, умноженное на правдоподобие ответов.
    θ̂ — его среднее, SE — стандартное отклонение. В отличие от метода максимального
    правдоподобия EAP даёт конечную оценку, даже когда все ответы верны или все
    неверны. В начале теста это обычная ситуация.

    Счёт ответа в [0, 1] допускает частичный балл, сейчас используется 0 или 1.
    """
    log_posterior = np.log(PRIOR)
    for item, score in responses:
        p = np.clip(probability(THETA_GRID, item), 1e-9, 1 - 1e-9)
        log_posterior = log_posterior + score * np.log(p) + (1.0 - score) * np.log(1.0 - p)
    log_posterior -= log_posterior.max()
    posterior = np.exp(log_posterior)
    posterior /= posterior.sum()
    theta = float(np.sum(THETA_GRID * posterior))
    se = float(np.sqrt(np.sum((THETA_GRID - theta) ** 2 * posterior)))
    return AbilityEstimate(theta=theta, se=se)


def estimate_ability_wle(responses: Sequence[tuple[ItemParameters, float]]) -> AbilityEstimate:
    """Итоговая оценка θ взвешенным правдоподобием Уорма (WLE) — для решения о грейде.

    EAP с априорным N(0, 1) стягивает крайние оценки к среднему популяции: сильного
    кандидата она занижает, слабого — завышает. Для подбора заданий по ходу теста это
    полезная устойчивость, а для решения о грейде — систематическая несправедливость к
    сильным. WLE максимизирует правдоподобие с поправкой ½·ln I(θ), почти не смещена и,
    в отличие от обычного максимального правдоподобия, конечна при всех верных или
    всех неверных ответах. SE = 1 / √I(θ̂). Без ответов оценки нет — возвращается EAP.
    """
    if not responses:
        return estimate_ability(responses)
    log_likelihood = np.zeros_like(FINE_THETA_GRID)
    test_information = np.zeros_like(FINE_THETA_GRID)
    for item, score in responses:
        p = np.clip(probability(FINE_THETA_GRID, item), 1e-9, 1 - 1e-9)
        log_likelihood += score * np.log(p) + (1.0 - score) * np.log(1.0 - p)
        useful = np.clip((p - item.c) / (1.0 - item.c), 0.0, 1.0)
        test_information += item.a**2 * useful**2 * (1.0 - p) / p
    weighted = log_likelihood + 0.5 * np.log(np.maximum(test_information, 1e-12))
    index = int(np.argmax(weighted))
    theta = float(FINE_THETA_GRID[index])
    info = float(test_information[index])
    se = float(1.0 / np.sqrt(info)) if info > 1e-9 else THETA_MAX - THETA_MIN
    return AbilityEstimate(theta=theta, se=se)


def simulate_response(theta: float, item: ItemParameters, uniform: float) -> float:
    """Ответ виртуального кандидата: 1, если равномерное число меньше вероятности успеха."""
    return 1.0 if uniform < float(probability(theta, item)) else 0.0
