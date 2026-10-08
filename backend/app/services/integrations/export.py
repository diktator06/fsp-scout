import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.schemas.integration import AtsCandidate

ExportFormat = Literal["csv", "json"]

EXPORT_COLUMNS = (
    "candidate_id",
    "full_name",
    "email",
    "phone",
    "telegram",
    "city",
    "specialization",
    "grade",
    "category",
    "grade_confirmed",
    "verified_score",
    "experience_years",
    "skills",
    "source",
    "source_id",
    "disclosed_at",
    "profile_url",
)


@dataclass(frozen=True, slots=True)
class ExportFile:
    """Готовый файл выгрузки."""

    filename: str
    media_type: str
    content: bytes


def render(candidates: list[AtsCandidate], fmt: ExportFormat, now: datetime) -> ExportFile:
    """Файл для импорта в ATS: CSV с BOM (открывается в Excel) или JSON."""
    stamp = now.strftime("%Y-%m-%d")
    if fmt == "json":
        document = {
            "exported_at": now.isoformat(),
            "count": len(candidates),
            "candidates": [item.model_dump(mode="json") for item in candidates],
        }
        return ExportFile(
            filename=f"scout-candidates-{stamp}.json",
            media_type="application/json",
            content=json.dumps(document, ensure_ascii=False, indent=2).encode(),
        )
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for item in candidates:
        row = item.model_dump(mode="json")
        row["skills"] = "; ".join(item.skills)
        row["grade_confirmed"] = "true" if item.grade_confirmed else "false"
        writer.writerow(row)
    return ExportFile(
        filename=f"scout-candidates-{stamp}.csv",
        media_type="text/csv; charset=utf-8",
        content=b"\xef\xbb\xbf" + buffer.getvalue().encode(),
    )
