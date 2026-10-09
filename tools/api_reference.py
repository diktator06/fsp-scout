import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "docs" / "openapi.json"
REPORT_PATH = ROOT / "docs" / "API.md"
METHODS = ("get", "post", "put", "patch", "delete")
ROLE_BY_TAG = {
    "system": "все",
    "auth": "все",
    "dictionaries": "все; изменение — методист",
    "account": "любая роль",
    "notifications": "любая роль",
    "trust": "кандидат",
    "assessment": "кандидат",
    "moderation": "методист",
    "integrations": "работодатель",
}
ROLE_BY_PREFIX = {"candidate": "кандидат", "employer": "работодатель", "methodist": "методист"}


def role(tag: str) -> str:
    """Кому доступна группа методов."""
    return ROLE_BY_TAG.get(tag) or ROLE_BY_PREFIX.get(tag.split(":")[0], "—")


def errors(operation: dict[str, Any]) -> str:
    """Коды ошибок метода через запятую."""
    codes = sorted(code for code in operation.get("responses", {}) if code[0] in "45")
    return ", ".join(codes) or "—"


def cell(text: str) -> str:
    """Текст для ячейки таблицы Markdown."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def build(spec: dict[str, Any]) -> str:
    """Справочник API: вход, формат ошибок, группы методов с таблицами."""
    descriptions = {tag["name"]: tag.get("description", "") for tag in spec.get("tags", [])}
    groups: dict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
    for path, operations in spec["paths"].items():
        for method in METHODS:
            if method in operations:
                operation = operations[method]
                tag = (operation.get("tags") or ["прочее"])[0]
                groups[tag].append((method.upper(), path, operation))
    total = sum(len(items) for items in groups.values())
    order = [tag for tag in descriptions if tag in groups] + sorted(
        tag for tag in groups if tag not in descriptions
    )
    lines = [
        "# API «Скаута»",
        "",
        "> Документ собирается командой `make openapi` из [openapi.json](openapi.json) — "
        "той же спецификации, что отдаёт Swagger UI на стенде (`/api/docs`). "
        "Правка вручную будет перезаписана.",
        "",
        f"{spec['info']['title']} {spec['info']['version']}: {total} методов в "
        f"{len(order)} группах, OpenAPI {spec['openapi']}. Базовый путь — `/api/v1`, "
        "формат — JSON в UTF-8.",
        "",
        "## Вход и роли",
        "",
        "- `POST /api/v1/auth/login` возвращает access-токен (JWT, 15 минут) и ставит "
        "refresh-токен в httpOnly-cookie с путём `/api/v1/auth`. Access-токен передаётся в "
        "заголовке `Authorization: Bearer <token>`; `POST /api/v1/auth/refresh` выдаёт новый и "
        "ротирует cookie, повтор старого refresh-токена отзывает всю цепочку.",
        "- Claims access-токена совместимы с Keycloak: роль — в `realm_access.roles` "
        "(`candidate`, `employer`, `methodist`). Метод чужой роли отвечает 403.",
        "- Вход через ФСП ID — `POST /api/v1/auth/fsp/start` и `/auth/fsp/callback` "
        "(OIDC Authorization Code + PKCE), подробнее — [FSP_INTEGRATION.md](FSP_INTEGRATION.md).",
        "- Вход, регистрация, выгрузка и песочница ATS ограничены по частоте: 429 с "
        "`details.retry_after_seconds`.",
        "",
        "## Ошибки",
        "",
        "Все ошибки — в едином формате; по `code` клиент выбирает реакцию, `message` можно "
        "показывать пользователю, `details` уточняет поле или лимит.",
        "",
        "```json",
        '{"error": {"code": "email_already_registered", '
        '"message": "Пользователь с таким email уже зарегистрирован", "details": {}}}',
        "```",
        "",
        "| Статус | Когда |",
        "|---|---|",
        "| 400 | Некорректный запрос, например чужой или просроченный `state` ФСП ID |",
        "| 401 | Нет токена или он недействителен |",
        "| 403 | Роль не та или действие запрещено уровнем доверия компании |",
        "| 404 | Объект не найден или принадлежит другому пользователю |",
        "| 409 | Конфликт с состоянием: повторное приглашение, ФСП ID уже привязан и т. п. |",
        "| 422 | Ошибка валидации; `details` содержит поля |",
        "| 429 | Превышен лимит запросов |",
        "| 503 | Недоступен внешний сервис (ФСП ID, реестр) |",
        "",
        "## Группы методов",
        "",
        "| Группа | Кому | Методов | О чём |",
        "|---|---|---:|---|",
    ]
    for tag in order:
        lines.append(
            f"| [{tag}](#{anchor(tag)}) | {role(tag)} | {len(groups[tag])} "
            f"| {cell(descriptions.get(tag, ''))} |"
        )
    for tag in order:
        lines += ["", f"## {tag}", ""]
        if descriptions.get(tag):
            lines += [cell(descriptions[tag]), ""]
        lines += ["| Метод | Путь | Что делает | Вход | Ошибки |", "|---|---|---|---|---|"]
        for method, path, operation in groups[tag]:
            secured = "да" if operation.get("security") else "нет"
            lines.append(
                f"| {method} | `{path}` | {cell(operation.get('summary', ''))} | {secured} "
                f"| {errors(operation)} |"
            )
    return "\n".join(lines) + "\n"


def anchor(tag: str) -> str:
    """Якорь заголовка так, как его строит GitHub."""
    return "".join(char for char in tag.lower().replace(" ", "-") if char.isalnum() or char in "-_")


def main() -> None:
    """Читает спецификацию и пишет docs/API.md."""
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    REPORT_PATH.write_text(build(spec), encoding="utf-8")
    print(f"{REPORT_PATH.relative_to(ROOT)}: {sum(1 for _ in REPORT_PATH.open())} строк")


if __name__ == "__main__":
    main()
