from collections.abc import Collection, Sequence

import numpy as np

from app.services.assessment.irt import ItemParameters, estimate_ability_wle, probability

MIN_PERSON_FIT_ITEMS = 5
MIN_REST_ITEMS = 5
MIN_EXPOSED_ITEMS = 2

type Responses = Sequence[tuple[ItemParameters, float]]


def person_fit(responses: Responses, theta: float) -> float | None:
    """Индекс согласованности ответов l_z (Drasgow, Levine, Williams, 1985).

    Сравнивает правдоподобие фактических ответов с ожидаемым при θ̂. Сильно
    отрицательное значение — паттерн, нетипичный для модели: верно решены трудные
    задания при ошибках в лёгких. При меньше чем пяти ответах не считается.
    """
    if len(responses) < MIN_PERSON_FIT_ITEMS:
        return None
    observed = expected = variance = 0.0
    for item, score in responses:
        p = float(np.clip(probability(theta, item), 1e-6, 1 - 1e-6))
        log_odds = float(np.log(p / (1.0 - p)))
        observed += score * np.log(p) + (1.0 - score) * np.log(1.0 - p)
        expected += p * np.log(p) + (1.0 - p) * np.log(1.0 - p)
        variance += p * (1.0 - p) * log_odds**2
    if variance <= 1e-9:
        return None
    return float((observed - expected) / np.sqrt(variance))


def preknowledge(
    codes: Sequence[str], responses: Responses, exposed: Collection[str]
) -> float | None:
    """Статистика предзнания: не решает ли кандидат «популярные» задания лучше прогноза.

    Утекают в первую очередь самые показываемые семейства. Способность оценивается по
    остальным заданиям, а по популярным считается стандартизованный остаток
    Σ(u − P) / √ΣP(1 − P). Большое положительное значение — подозрение на знание
    заданий заранее. Нужно хотя бы пять «обычных» и два «популярных» ответа.
    """
    rest = [pair for code, pair in zip(codes, responses, strict=True) if code not in exposed]
    hot = [pair for code, pair in zip(codes, responses, strict=True) if code in exposed]
    if len(rest) < MIN_REST_ITEMS or len(hot) < MIN_EXPOSED_ITEMS:
        return None
    theta = estimate_ability_wle(rest).theta
    expected = [float(probability(theta, item)) for item, _ in hot]
    residual = sum(score - p for (_, score), p in zip(hot, expected, strict=True))
    variance = sum(p * (1.0 - p) for p in expected)
    return float(residual / np.sqrt(variance)) if variance > 1e-9 else None
