# Библиотеки и образы

> Документ собирается командой `make libraries` из `pyproject.toml`, `uv.lock`,
> `package.json`, `package-lock.json` и Dockerfile — только то, что реально
> используется. Лицензии взяты из метаданных пакетов. Все зависимости — под открытыми
> лицензиями; проприетарных сервисов и внешних API (включая LLM) решение не использует.

## Бэкенд (Python, `backend`)

| Пакет | Версия | Лицензия | Зачем |
|---|---|---|---|
| `fastapi` | 0.142.2 | MIT | HTTP API, OpenAPI и Swagger |
| `uvicorn` | 0.54.0 | BSD-3-Clause | ASGI-сервер |
| `sqlalchemy` | 2.1.3 | MIT | ORM, асинхронный доступ к PostgreSQL |
| `asyncpg` | 0.31.0 | Apache-2.0 | Драйвер PostgreSQL |
| `alembic` | 1.20.0 | MIT | Миграции схемы |
| `pydantic` | 2.13.5 | MIT | Схемы и валидация данных |
| `pydantic-settings` | 2.15.0 | MIT | Настройки из переменных окружения |
| `argon2-cffi` | 25.1.0 | MIT | Хеширование паролей argon2id |
| `pyjwt` | 2.15.1 | MIT | JWT: access-токены, RS256 и JWKS для ФСП ID |
| `pgvector` | 0.5.0 | MIT | Колонка vector под эмбеддинги навыков (пока близость — по таблице связей) |
| `jinja2` | 3.1.6 | BSD | Шаблоны писем и PDF-профиля, страница входа эмулятора |
| `pyyaml` | 6.0.3 | MIT | Справочники и банк вакансий оценки в YAML |
| `numpy` | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | IRT: EAP, WLE, калибровка, симуляция |
| `weasyprint` | 70.0 | BSD | Выгрузка профиля кандидата в PDF |
| `httpx` | 0.28.1 | BSD | HTTP-клиент: ФСП ID, реестр, вебхуки ATS |
| `pypdf` | 6.19.0 | BSD-3-Clause | Извлечение текста из резюме в PDF |
| `python-multipart` | 0.0.32 | Apache-2.0 | Загрузка файлов и формы |

Для разработки и тестов:

| Пакет | Версия | Лицензия | Зачем |
|---|---|---|---|
| `pytest` | 9.1.1 | MIT | Тесты |
| `pytest-asyncio` | 1.4.0 | Apache-2.0 | Асинхронные тесты |
| `ruff` | 0.16.10 | MIT | Линтер и форматтер |
| `mypy` | 2.4.0 | MIT | Проверка типов в строгом режиме |
| `types-pyyaml` | 6.0.12.20260906 | Apache-2.0 | Типы для PyYAML |
| `pandas` | 3.0.6 | BSD | Тесты исполняют код заданий по pandas и сверяют ответ с ключом |

## Эмулятор ФСП ID и реестра (Python, `fsp-registry-mock`)

| Пакет | Версия | Лицензия | Зачем |
|---|---|---|---|
| `fastapi` | 0.142.2 | MIT | HTTP API, OpenAPI и Swagger |
| `uvicorn` | 0.54.0 | BSD-3-Clause | ASGI-сервер |
| `pyjwt` | 2.15.1 | MIT | JWT: access-токены, RS256 и JWKS для ФСП ID |
| `jinja2` | 3.1.6 | BSD | Шаблоны писем и PDF-профиля, страница входа эмулятора |
| `python-multipart` | 0.0.32 | Apache-2.0 | Загрузка файлов и формы |
| `pydantic-settings` | 2.15.0 | MIT | Настройки из переменных окружения |

Для разработки и тестов:

| Пакет | Версия | Лицензия | Зачем |
|---|---|---|---|
| `pytest` | 9.1.1 | MIT | Тесты |
| `pytest-asyncio` | 1.4.0 | Apache-2.0 | Асинхронные тесты |
| `httpx` | 0.28.1 | BSD | HTTP-клиент: ФСП ID, реестр, вебхуки ATS |
| `ruff` | 0.16.10 | MIT | Линтер и форматтер |
| `mypy` | 2.4.0 | MIT | Проверка типов в строгом режиме |

## Фронтенд (TypeScript, `frontend`)

| Пакет | Версия | Лицензия | Зачем |
|---|---|---|---|
| `@fontsource/jetbrains-mono` | 5.3.0 | OFL-1.1 | Моноширинный шрифт, офлайн |
| `@fontsource/montserrat` | 5.3.0 | OFL-1.1 | Шрифт интерфейса, офлайн |
| `@mantine/core` | 9.7.1 | MIT | Компоненты интерфейса |
| `@mantine/form` | 9.7.1 | MIT | Формы |
| `@mantine/hooks` | 9.7.1 | MIT | Хуки интерфейса |
| `@mantine/notifications` | 9.7.1 | MIT | Уведомления |
| `@tabler/icons-react` | 3.49.0 | MIT | Иконки |
| `@tanstack/react-query` | 5.104.1 | MIT | Кеш и синхронизация запросов к API |
| `openapi-fetch` | 0.17.0 | MIT | Типизированный клиент API по OpenAPI |
| `prism-react-renderer` | 2.4.1 | MIT | Подсветка кода в заданиях |
| `prismjs` | 1.30.0 | MIT | Грамматики подсветки (SQL, Python, YAML…) |
| `react` | 19.3.0 | MIT | UI |
| `react-dom` | 19.3.0 | MIT | UI |
| `react-router` | 8.4.0 | MIT | Маршрутизация |

Для сборки, разработки и тестов:

| Пакет | Версия | Лицензия | Зачем |
|---|---|---|---|
| `@eslint/js` | 10.0.1 | MIT | Правила eslint |
| `@testing-library/dom` | 10.4.2 | MIT | Тесты компонентов |
| `@testing-library/react` | 16.3.3 | MIT | Тесты компонентов |
| `@types/node` | 26.6.4 | MIT | Типы Node.js |
| `@types/react` | 19.3.0 | MIT | Типы React |
| `@types/react-dom` | 19.3.0 | MIT | Типы React DOM |
| `@vitejs/plugin-react` | 6.1.2 | MIT | React для Vite |
| `eslint` | 10.12.0 | MIT | Линтер |
| `eslint-plugin-react-hooks` | 7.1.1 | MIT | Правила хуков React |
| `eslint-plugin-react-refresh` | 0.5.7 | MIT | Правила Fast Refresh |
| `globals` | 17.13.0 | MIT | Глобальные имена для eslint |
| `jsdom` | 29.1.1 | MIT | DOM в тестах |
| `openapi-typescript` | 7.13.0 | MIT | Генерация TS-типов из OpenAPI |
| `postcss` | 8.5.29 | MIT | CSS-конвейер |
| `postcss-preset-mantine` | 1.18.0 | MIT | CSS-функции Mantine |
| `postcss-simple-vars` | 7.0.1 | MIT | Переменные в CSS |
| `prettier` | 3.9.9 | MIT | Форматтер |
| `typescript` | 5.9.3 | Apache-2.0 | Типизация |
| `typescript-eslint` | 8.71.1 | MIT | Правила eslint для TypeScript |
| `vite` | 8.3.3 | MIT | Сборка и dev-сервер |
| `vitest` | 5.0.3 | MIT | Тесты |

## Образы Docker

| Образ | Зачем | Где задан |
|---|---|---|
| `axllent/mailpit:v1.31` | Почтовый ящик стенда: письма подтверждения и уведомления | `docker-compose.yml` |
| `caddy:2.10-alpine` | Обратный прокси с HTTPS на VPS (оверлей) | `deploy/docker-compose.vps.yml` |
| `nginx:1.31-alpine` | Раздача фронтенда и прокси /api | `frontend/Dockerfile` |
| `node:24-alpine` | Сборка фронтенда и ассетов Swagger UI | `backend/Dockerfile` |
| `pgvector/pgvector:0.8.7-pg16-trixie` | PostgreSQL 16 с расширением pgvector | `docker-compose.yml` |
| `python:3.13-slim` | Базовый образ бэкенда и эмулятора | `backend/Dockerfile` |
| `quay.io/keycloak/keycloak:26.4` | ФСП ID на полноценном Keycloak (оверлей) | `docker-compose.keycloak.yml` |
