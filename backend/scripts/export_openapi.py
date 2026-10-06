import json
from pathlib import Path

from app.main import app

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


def export_openapi(output_path: Path = OUTPUT_PATH) -> Path:
    """Сохраняет спецификацию OpenAPI в `docs/openapi.json`.

    Из этого файла генерируются типы фронтенда (`npm run gen:api`), и он же входит
    в сопроводительную документацию. Ключи сортируются, чтобы диффы в git были
    читаемыми.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    spec = app.openapi()
    output_path.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output_path


if __name__ == "__main__":
    print(f"OpenAPI сохранён в {export_openapi()}")
