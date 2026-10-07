from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.models.fsp import FspState
from app.services.matching.facts import CandidateFacts
from app.services.matching.match_scoring import MatchResult, SkillMatch
from app.services.matching.verified_score import VerifiedScore

FORMAT_NAMES = {"office": "офис", "hybrid": "гибрид", "remote": "удалённо"}
FSP_NEUTRAL = {
    FspState.NOT_LINKED: "Профиль ФСП не привязан — оценка по тесту и профилю",
    FspState.LINKED_EMPTY: "ФСП ID привязан, участий пока нет — оценка по тесту и профилю",
    FspState.HIDDEN: "Достижения ФСП скрыты кандидатом — оценка по тесту и профилю",
}


@dataclass(frozen=True, slots=True)
class ExplanationItem:
    """Одна причина в блоке «Почему в подборке»: плюс, минус или нейтральная справка."""

    kind: str
    text: str


def _names(matches: Sequence[SkillMatch], names: Mapping[int, str]) -> str:
    """Перечисление навыков через запятую."""
    return ", ".join(names.get(match.skill_id, "?") for match in matches)


def _ordinal_percentile(value: float) -> str:
    """Перцентиль словами: «82-й перцентиль»."""
    return f"{round(value * 100)}-й перцентиль"


def explain_fsp(candidate: CandidateFacts) -> ExplanationItem:
    """Причина про ФСП: лучший результат, сводка участий или нейтральная справка."""
    if candidate.fsp_state is not FspState.LINKED:
        return ExplanationItem("info", FSP_NEUTRAL[candidate.fsp_state])
    if candidate.fsp_best:
        return ExplanationItem("plus", f"ФСП: {candidate.fsp_best}")
    return ExplanationItem("info", f"ФСП: {candidate.fsp_summary}")


def explain_match(
    result: MatchResult,
    candidate: CandidateFacts,
    score: VerifiedScore,
    *,
    skill_names: Mapping[int, str],
    category_title: str,
    grade_name: str,
    shared_terms: Sequence[str] = (),
) -> list[ExplanationItem]:
    """Человекочитаемые причины места кандидата в подборке.

    Объяснение строится из тех же чисел, что и балл: совпадения навыков, тест, условия.
    Скрытые кандидатом данные (ожидания, город) в тексте не раскрываются.
    """
    items: list[ExplanationItem] = []
    must = [match for match in result.skills if match.importance == "must"]
    nice = [match for match in result.skills if match.importance == "nice"]
    covered = [match for match in must if match.status in {"verified", "declared"}]
    if must:
        kind = "plus" if len(covered) == len(must) else "info" if covered else "minus"
        text = f"Закрывает {len(covered)} из {len(must)} обязательных навыков"
        items.append(
            ExplanationItem(kind, f"{text}: {_names(covered, skill_names)}" if covered else text)
        )
    verified = [match for match in result.skills if match.status == "verified"]
    if verified:
        items.append(
            ExplanationItem("plus", f"Подтверждено тестом: {_names(verified, skill_names)}")
        )
    for match in must:
        if match.status == "related" and match.via_skill_id is not None:
            items.append(
                ExplanationItem(
                    "info",
                    f"{skill_names.get(match.skill_id, '?')} — нет, но есть родственный "
                    f"{skill_names.get(match.via_skill_id, '?')}",
                )
            )
    missing = [match for match in must if match.status == "missing"]
    if missing:
        items.append(ExplanationItem("minus", f"Нет в профиле: {_names(missing, skill_names)}"))
    nice_covered = [match for match in nice if match.status in {"verified", "declared"}]
    if nice_covered:
        items.append(
            ExplanationItem("plus", f"Из желательного: {_names(nice_covered, skill_names)}")
        )

    if candidate.confirmed and candidate.test is not None and score.test_percentile is not None:
        text = f"Тест: {_ordinal_percentile(score.test_percentile)} в категории {category_title}"
        if candidate.test.express:
            text += " (экспресс-режим, точность ниже)"
        items.append(ExplanationItem("plus" if score.test_percentile >= 0.5 else "info", text))
    elif not candidate.confirmed:
        items.append(
            ExplanationItem("minus", f"Грейд {grade_name} заявлен, но не подтверждён тестом")
        )
    if any(code == "adjacent_grade" for code, _ in result.penalties):
        items.append(ExplanationItem("info", f"Грейд {grade_name} — соседний с запрошенным"))

    for check in result.conditions:
        if check.key == "salary":
            texts = {
                "ok": ("plus", "Ожидания укладываются в вашу вилку"),
                "partial": ("minus", "Ожидания немного выше верхней границы вилки"),
                "mismatch": ("minus", "Ожидания выше вилки больше чем на 30 %"),
                "unknown": ("info", "Зарплатные ожидания не указаны или скрыты"),
            }
        elif check.key == "format":
            preferred = ", ".join(
                FORMAT_NAMES.get(item, item) for item in sorted(candidate.work_formats)
            )
            texts = {
                "mismatch": ("minus", f"Предпочитает другой формат работы: {preferred}"),
                "unknown": ("info", "Формат работы не указан"),
            }
        else:
            texts = {
                "partial": ("info", "Живёт в другом городе, готов к переезду"),
                "mismatch": ("minus", "Живёт в другом городе и не готов к переезду"),
                "unknown": ("info", "Город не указан или скрыт"),
            }
        if check.status in texts:
            kind, text = texts[check.status]
            items.append(ExplanationItem(kind, text))

    if shared_terms:
        items.append(
            ExplanationItem("plus", f"Опыт перекликается с задачами: {', '.join(shared_terms)}")
        )
    items.append(explain_fsp(candidate))
    return items
