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
    M-шаг: для каждого семейства — несколько шагов Ньютона по (a, b) на ожидаемых
    числах попыток и успехов в узлах сетки. Это классическая схема Бока–Айткина.
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
            a_new[item], b_new[item] = _newton_update(
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


def _newton_update(
    a: float,
    b: float,
    c: float,
    attempts: NDArray[np.float64],
    successes: NDArray[np.float64],
    steps: int = 5,
) -> tuple[float, float]:
    """Шаги Ньютона по (a, b) для одного семейства с численным гессианом и ограничениями.

    Ограничения a ∈ [0,2; 3,5] и b ∈ [−4; 4] не дают оценке уйти в бесконечность на
    почти безошибочных или почти нерешаемых семействах.
    """

    def log_likelihood(params: NDArray[np.float64]) -> float:
        """Ожидаемое логарифмическое правдоподобие семейства."""
        logistic = 1.0 / (1.0 + np.exp(-params[0] * (THETA_GRID - params[1])))
        p = np.clip(c + (1 - c) * logistic, 1e-9, 1 - 1e-9)
        return float(np.sum(successes * np.log(p) + (attempts - successes) * np.log(1 - p)))

    params = np.array([a, b], dtype=np.float64)
    eps = 1e-4
    for _ in range(steps):
        gradient = np.zeros(2)
        hessian = np.zeros((2, 2))
        base = log_likelihood(params)
        for i in range(2):
            shift = np.zeros(2)
            shift[i] = eps
            plus, minus = log_likelihood(params + shift), log_likelihood(params - shift)
            gradient[i] = (plus - minus) / (2 * eps)
            hessian[i, i] = (plus - 2 * base + minus) / eps**2
        mixed = np.array([eps, eps])
        cross = np.array([eps, -eps])
        hessian[0, 1] = hessian[1, 0] = (
            log_likelihood(params + mixed)
            - log_likelihood(params + cross)
            - log_likelihood(params - cross)
            + log_likelihood(params - mixed)
        ) / (4 * eps**2)
        try:
            step = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError:
            break
        if not np.all(np.isfinite(step)):
            break
        params = params - np.clip(step, -0.5, 0.5)
        params[0] = float(np.clip(params[0], 0.2, 3.5))
        params[1] = float(np.clip(params[1], -4.0, 4.0))
    return float(params[0]), float(params[1])
