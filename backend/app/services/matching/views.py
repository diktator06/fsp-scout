from collections.abc import Mapping, Sequence
from typing import Any

from app.schemas.cards import ScoreComponentRead
from app.schemas.matching import ExplanationItemRead, MatchRead, SkillBrief, SkillMatchRead
from app.services.matching.explanations import ExplanationItem
from app.services.matching.match_scoring import MATCH_LABELS, MATCH_WEIGHTS, MatchResult


def match_snapshot(result: MatchResult, explanation: Sequence[ExplanationItem]) -> dict[str, Any]:
    """Снимок балла для хранения в версии подборки: выдачу можно показать как была."""
    return {
        "score": result.score,
        "components": result.components,
        "penalties": [code for code, _ in result.penalties],
        "skills": [
            {
                "skill_id": match.skill_id,
                "importance": match.importance,
                "status": match.status,
                "via_skill_id": match.via_skill_id,
            }
            for match in result.skills
        ],
        "explanation": [{"kind": item.kind, "text": item.text} for item in explanation],
    }


def match_read(snapshot: Mapping[str, Any], skill_names: Mapping[int, str]) -> MatchRead:
    """Снимок балла в форму ответа API: баллы 0–100 и вклад каждого фактора."""
    components = snapshot["components"]
    return MatchRead(
        score=round(100 * float(snapshot["score"]), 1),
        components=[
            ScoreComponentRead(
                key=key,
                label=MATCH_LABELS[key],
                value=float(components.get(key, 0.0)),
                weight=weight,
                contribution=round(100 * weight * float(components.get(key, 0.0)), 1),
            )
            for key, weight in MATCH_WEIGHTS.items()
        ],
        penalties=list(snapshot.get("penalties", [])),
        skills=[
            SkillMatchRead(
                skill=SkillBrief(id=item["skill_id"], name=skill_names.get(item["skill_id"], "?")),
                importance=item["importance"],
                status=item["status"],
                via=SkillBrief(
                    id=item["via_skill_id"], name=skill_names.get(item["via_skill_id"], "?")
                )
                if item.get("via_skill_id") is not None
                else None,
            )
            for item in snapshot.get("skills", [])
        ],
        explanation=[ExplanationItemRead(**item) for item in snapshot.get("explanation", [])],
    )
