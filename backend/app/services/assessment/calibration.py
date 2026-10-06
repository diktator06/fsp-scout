from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from app.services.assessment.irt import PRIOR, THETA_GRID

MIN_RESPONSES_FOR_CALIBRATION = 200


@dataclass(frozen=True, slots=True)
class CalibratedItem:
    """Результат калибровки одного семейства."""

    a: float
    b: float
    c: float
    responses: int


def _item_probabilities(
    a: NDArray[np.float64], b: NDArray[np.float64], c: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Матрица P[узел сетки, задание] для текущих параметров."""
    logits = a[None, :] * (THETA_GRID[:, None] - b[None, :])
    return c[None, :] + (1.0 - c[None, :]) / (1.0 + np.exp(-logits))


def calibrate(
    responses: NDArray[np.float64],
    guessing: NDArray[np.float64],
    *,
    iterations: int = 60,
    tolerance: float = 1e-4,
) -> list[CalibratedItem]:
    """Калибрует a и b семейств методом маргинального максимального правдоподобия (EM).

    `responses` — матрица «кандидат × семейство» с 0/1 и NaN там, где семейство не
    показывалось (адаптивный тест даёт разреженную матрицу). Параметр c фиксирован:
    для выбора из четырёх вариантов его оценка нестабильна на малых выборках.

    E-шаг: апостериорное распределение θ каждого кандидата на сетке квадратуры.
    M-шаг: для каждого семейства — несколько шагов Fisher scoring по (a, b) на
    ожидаемых числах попыток и успехов в узлах сетки. Это классическая схема
    Бока–Айткина.
    """
    observed = ~np.isnan(responses)
    scores = np.where(observed, responses, 0.0)
    n_items = responses.shape[1]
    a = np.full(n_items, 1.0)
    b = np.zeros(n_items)
    c = guessing.astype(np.float64)

    for _ in range(iterations):
        p = np.clip(_item_probabilities(a, b, c), 1e-9, 1 - 1e-9)
        log_like = scores @ np.log(p).T + (observed & (scores == 0)).astype(float) @ np.log(1 - p).T
        log_post = log_like + np.log(PRIOR)[None, :]
        log_post -= log_post.max(axis=1, keepdims=True)
        posterior = np.exp(log_post)
        posterior /= posterior.sum(axis=1, keepdims=True)

        attempts = posterior.T @ observed.astype(float)
        successes = posterior.T @ scores

        a_new, b_new = a.copy(), b.copy()
        for item in range(n_items):
            a_new[item], b_new[item] = _fisher_scoring_update(
                a[item], b[item], c[item], attempts[:, item], successes[:, item]
            )
        converged = np.max(np.abs(a_new - a)) < tolerance and np.max(np.abs(b_new - b)) < tolerance
        a, b = a_new, b_new
        if converged:
            break

    counts = observed.sum(axis=0)
    return [
        CalibratedItem(a=float(a[i]), b=float(b[i]), c=float(c[i]), responses=int(counts[i]))
        for i in range(n_items)
    ]


def _fisher_scoring_update(
    a: float,
    b: float,
    c: float,
    attempts: NDArray[np.float64],
    successes: NDArray[np.float64],
    steps: int = 6,
) -> tuple[float, float]:
    """Шаги Fisher scoring по (a, b) для одного семейства.

    Градиент считается аналитически, а вместо гессиана берётся ожидаемая
    информационная матрица Фишера. Она всегда положительно определена, поэтому шаг
    идёт в сторону роста правдоподобия даже вдали от оптимума. Обычный метод
    Ньютона там может уйти к седловой точке.

    Для 3PL с фиксированным c: P = c + (1 − c)·L, L = σ(a(θ − b)),
    ∂P/∂a = (1 − c)·L(1 − L)·(θ − b), ∂P/∂b = −(1 − c)·L(1 − L)·a.
    Ограничения a ∈ [0,2; 3,5] и b ∈ [−4; 4] не дают оценке уйти в бесконечность на
    почти безошибочных или почти нерешаемых семействах.
    """
    for _ in range(steps):
        logistic = 1.0 / (1.0 + np.exp(-a * (THETA_GRID - b)))
        p = np.clip(c + (1.0 - c) * logistic, 1e-9, 1.0 - 1e-9)
        slope = (1.0 - c) * logistic * (1.0 - logistic)
        derivatives = np.vstack([slope * (THETA_GRID - b), -slope * a])
        weights = 1.0 / (p * (1.0 - p))
        gradient = derivatives @ ((successes - attempts * p) * weights)
        fisher = (derivatives * (attempts * weights)) @ derivatives.T + np.eye(2) * 1e-6
        try:
            step = np.linalg.solve(fisher, gradient)
        except np.linalg.LinAlgError:
            break
        if not np.all(np.isfinite(step)):
            break
        step = np.clip(step, -0.5, 0.5)
        a = float(np.clip(a + step[0], 0.2, 3.5))
        b = float(np.clip(b + step[1], -4.0, 4.0))
        if np.max(np.abs(step)) < 1e-5:
            break
    return a, b
