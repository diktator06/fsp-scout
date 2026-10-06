from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompetencyWeight:
    """Компетенция в blueprint специализации."""

    code: str
    weight: float
    gate_skill_slugs: tuple[str, ...] = ()


def build_blueprint(
    competencies: Iterable[CompetencyWeight],
    candidate_skill_slugs: Iterable[str],
    available_competencies: Iterable[str] | None = None,
) -> dict[str, float]:
    """Собирает веса компетенций теста под конкретного кандидата.

    Языково-зависимая компетенция (у неё есть `gate_skill_slugs`) попадает в тест,
    только если кандидат указал в опросе хотя бы один из этих навыков. Бэкендер на
    Java не получает заданий на особенности Python, а его вес делится между
    остальными компетенциями пропорционально. Так опрос формирует тест, а не
    просто заполняет анкету.

    `available_competencies` отсекает компетенции, по которым в банке нет активных
    семейств.
    """
    skills = set(candidate_skill_slugs)
    available = set(available_competencies) if available_competencies is not None else None
    selected = {
        item.code: item.weight
        for item in competencies
        if (not item.gate_skill_slugs or skills.intersection(item.gate_skill_slugs))
        and (available is None or item.code in available)
    }
    total = sum(selected.values())
    if total <= 0:
        return {}
    return {code: round(weight / total, 4) for code, weight in sorted(selected.items())}


def blueprint_shares(
    blueprint: Mapping[str, float], administered: Iterable[str]
) -> dict[str, float]:
    """Фактические доли компетенций среди уже показанных заданий."""
    counts: dict[str, int] = dict.fromkeys(blueprint, 0)
    total = 0
    for code in administered:
        if code in counts:
            counts[code] += 1
            total += 1
    return {code: (count / total if total else 0.0) for code, count in counts.items()}
