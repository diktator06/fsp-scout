import json
import re
import tomllib
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "docs" / "LIBRARIES.md"
PYTHON_PROJECTS = (("backend", "Бэкенд"), ("fsp-registry-mock", "Эмулятор ФСП ID и реестра"))
FRONTEND = ROOT / "frontend"
IMAGE_SOURCES = (
    "docker-compose.yml",
    "docker-compose.keycloak.yml",
    "deploy/docker-compose.vps.yml",
    "backend/Dockerfile",
    "frontend/Dockerfile",
    "fsp-registry-mock/Dockerfile",
)
REQUIREMENT_NAME = re.compile(r"^[A-Za-z0-9._-]+")
IMAGE_LINE = re.compile(r"^\s*(?:image:\s*|FROM\s+)(\S+)")

PURPOSES = {
    "fastapi": "HTTP API, OpenAPI и Swagger",
    "uvicorn": "ASGI-сервер",
    "sqlalchemy": "ORM, асинхронный доступ к PostgreSQL",
    "asyncpg": "Драйвер PostgreSQL",
    "alembic": "Миграции схемы",
    "pydantic": "Схемы и валидация данных",
    "pydantic-settings": "Настройки из переменных окружения",
    "argon2-cffi": "Хеширование паролей argon2id",
    "pyjwt": "JWT: access-токены, RS256 и JWKS для ФСП ID",
    "pgvector": "Колонка vector под эмбеддинги навыков (пока близость — по таблице связей)",
    "jinja2": "Шаблоны писем и PDF-профиля, страница входа эмулятора",
    "pyyaml": "Справочники и банк вакансий оценки в YAML",
    "numpy": "IRT: EAP, WLE, калибровка, симуляция",
    "weasyprint": "Выгрузка профиля кандидата в PDF",
    "httpx": "HTTP-клиент: ФСП ID, реестр, вебхуки ATS",
    "pypdf": "Извлечение текста из резюме в PDF",
    "python-multipart": "Загрузка файлов и формы",
    "pytest": "Тесты",
    "pytest-asyncio": "Асинхронные тесты",
    "ruff": "Линтер и форматтер",
    "mypy": "Проверка типов в строгом режиме",
    "types-pyyaml": "Типы для PyYAML",
    "pandas": "Тесты исполняют код заданий по pandas и сверяют ответ с ключом",
    "react": "UI",
    "react-dom": "UI",
    "react-router": "Маршрутизация",
    "@mantine/core": "Компоненты интерфейса",
    "@mantine/form": "Формы",
    "@mantine/hooks": "Хуки интерфейса",
    "@mantine/notifications": "Уведомления",
    "@tanstack/react-query": "Кеш и синхронизация запросов к API",
    "openapi-fetch": "Типизированный клиент API по OpenAPI",
    "@tabler/icons-react": "Иконки",
    "prism-react-renderer": "Подсветка кода в заданиях",
    "prismjs": "Грамматики подсветки (SQL, Python, YAML…)",
    "@fontsource/montserrat": "Шрифт интерфейса, офлайн",
    "@fontsource/jetbrains-mono": "Моноширинный шрифт, офлайн",
    "vite": "Сборка и dev-сервер",
    "@vitejs/plugin-react": "React для Vite",
    "typescript": "Типизация",
    "vitest": "Тесты",
    "@testing-library/react": "Тесты компонентов",
    "@testing-library/dom": "Тесты компонентов",
    "jsdom": "DOM в тестах",
    "eslint": "Линтер",
    "@eslint/js": "Правила eslint",
    "typescript-eslint": "Правила eslint для TypeScript",
    "eslint-plugin-react-hooks": "Правила хуков React",
    "eslint-plugin-react-refresh": "Правила Fast Refresh",
    "globals": "Глобальные имена для eslint",
    "prettier": "Форматтер",
    "openapi-typescript": "Генерация TS-типов из OpenAPI",
    "postcss": "CSS-конвейер",
    "postcss-preset-mantine": "CSS-функции Mantine",
    "postcss-simple-vars": "Переменные в CSS",
    "@types/node": "Типы Node.js",
    "@types/react": "Типы React",
    "@types/react-dom": "Типы React DOM",
}
IMAGE_PURPOSES = {
    "pgvector/pgvector": "PostgreSQL 16 с расширением pgvector",
    "axllent/mailpit": "Почтовый ящик стенда: письма подтверждения и уведомления",
    "quay.io/keycloak/keycloak": "ФСП ID на полноценном Keycloak (оверлей)",
    "caddy": "Обратный прокси с HTTPS на VPS (оверлей)",
    "python": "Базовый образ бэкенда и эмулятора",
    "node": "Сборка фронтенда и ассетов Swagger UI",
    "nginx": "Раздача фронтенда и прокси /api",
}


def normalize(name: str) -> str:
    """Имя пакета по PEP 503: регистр и разделители не важны."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_names(requirements: list[str]) -> list[str]:
    """Имена пакетов из строк зависимостей pyproject, без версий и extras."""
    names = []
    for requirement in requirements:
        match = REQUIREMENT_NAME.match(requirement)
        if match:
            names.append(normalize(match.group(0)))
    return names


def locked_versions(project: Path) -> dict[str, str]:
    """Точные версии из uv.lock — то, что реально ставится в образ."""
    lock = tomllib.loads((project / "uv.lock").read_text(encoding="utf-8"))
    return {normalize(item["name"]): item["version"] for item in lock.get("package", [])}


def python_license(name: str) -> str:
    """Лицензия из метаданных пакета: сначала SPDX-выражение, затем классификаторы."""
    try:
        meta = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return "—"
    expression = meta.get("License-Expression")
    if expression:
        return expression
    classifiers = [
        value.split("::")[-1].strip()
        for value in meta.get_all("Classifier") or []
        if value.startswith("License ::") and "OSI Approved" not in value.split("::")[-1]
    ]
    if classifiers:
        return ", ".join(classifiers).replace(" License", "")
    short = (meta.get("License") or "").strip().splitlines()
    return short[0][:40] if short and short[0] else "—"


def python_rows(directory: str) -> tuple[list[list[str]], list[list[str]]]:
    """Прямые зависимости проекта: рабочие и для разработки."""
    project = ROOT / directory
    config = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    versions = locked_versions(project)

    def rows(names: list[str]) -> list[list[str]]:
        """Строка таблицы на пакет."""
        return [
            [f"`{name}`", versions.get(name, "—"), python_license(name), PURPOSES.get(name, "—")]
            for name in names
        ]

    runtime = requirement_names(config["project"]["dependencies"])
    development = [
        name
        for name in requirement_names(config.get("dependency-groups", {}).get("dev", []))
        if name not in runtime
    ]
    return rows(runtime), rows(development)


def frontend_rows() -> tuple[list[list[str]], list[list[str]]]:
    """Прямые зависимости фронтенда с версиями и лицензиями из package-lock.json."""
    manifest = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((FRONTEND / "package-lock.json").read_text(encoding="utf-8"))["packages"]

    def rows(names: dict[str, str]) -> list[list[str]]:
        """Строка таблицы на пакет."""
        result = []
        for name in sorted(names):
            entry = lock.get(f"node_modules/{name}", {})
            result.append(
                [
                    f"`{name}`",
                    entry.get("version", "—"),
                    entry.get("license", "—"),
                    PURPOSES.get(name, "—"),
                ]
            )
        return result

    return rows(manifest.get("dependencies", {})), rows(manifest.get("devDependencies", {}))


def image_rows() -> list[list[str]]:
    """Образы Docker из compose-файлов и Dockerfile."""
    images: dict[str, str] = {}
    for source in IMAGE_SOURCES:
        for line in (ROOT / source).read_text(encoding="utf-8").splitlines():
            match = IMAGE_LINE.match(line)
            if match:
                images.setdefault(match.group(1), source)
    rows = []
    for image, source in sorted(images.items()):
        repository = image.rsplit(":", 1)[0]
        rows.append([f"`{image}`", IMAGE_PURPOSES.get(repository, "—"), f"`{source}`"])
    return rows


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    """Таблица Markdown."""
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def build() -> str:
    """Собирает документ из манифестов и lock-файлов."""
    header = ["Пакет", "Версия", "Лицензия", "Зачем"]
    lines = [
        "# Библиотеки и образы",
        "",
        "> Документ собирается командой `make libraries` из `pyproject.toml`, `uv.lock`,",
        "> `package.json`, `package-lock.json` и Dockerfile — только то, что реально",
        "> используется. Лицензии взяты из метаданных пакетов. Все зависимости — под открытыми",
        "> лицензиями; проприетарных сервисов и внешних API (включая LLM) решение не использует.",
        "",
    ]
    for directory, title in PYTHON_PROJECTS:
        runtime, development = python_rows(directory)
        lines += [f"## {title} (Python, `{directory}`)", "", *table(header, runtime), ""]
        if development:
            lines += ["Для разработки и тестов:", "", *table(header, development), ""]
    runtime, development = frontend_rows()
    lines += ["## Фронтенд (TypeScript, `frontend`)", "", *table(header, runtime), ""]
    lines += ["Для сборки, разработки и тестов:", "", *table(header, development), ""]
    lines += [
        "## Образы Docker",
        "",
        *table(["Образ", "Зачем", "Где задан"], image_rows()),
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    """Записывает docs/LIBRARIES.md."""
    REPORT_PATH.write_text(build(), encoding="utf-8")
    print(f"Записан {REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
