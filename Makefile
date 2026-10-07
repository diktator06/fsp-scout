# Скаут — частые команды разработки. Список целей: make help

COMPOSE := docker compose
BACKEND := cd backend &&
FRONTEND := cd frontend &&

.DEFAULT_GOAL := help
.PHONY: help up down restart logs ps reset db install install-backend install-frontend \
        dev-backend dev-frontend test test-backend test-frontend lint lint-backend lint-frontend \
        style format migrate revision seed openapi simulate check

help: ## Показать список команд
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

up: ## Собрать и поднять весь стенд в фоне
	$(COMPOSE) up --build -d

down: ## Остановить стенд (данные БД сохраняются)
	$(COMPOSE) down

restart: down up ## Перезапустить стенд

logs: ## Логи всех сервисов
	$(COMPOSE) logs -f --tail=200

ps: ## Состояние контейнеров
	$(COMPOSE) ps

reset: ## Полный сброс: удалить контейнеры и данные БД
	$(COMPOSE) down -v

db: ## Поднять только PostgreSQL и Mailpit (для локальной разработки и тестов)
	$(COMPOSE) up -d db mailpit

install: install-backend install-frontend ## Установить зависимости бэкенда и фронтенда

install-backend: ## Зависимости бэкенда (uv)
	$(BACKEND) uv sync

install-frontend: ## Зависимости фронтенда (npm)
	$(FRONTEND) npm ci

dev-backend: db ## Бэкенд с автоперезагрузкой на http://localhost:8000
	$(BACKEND) uv run alembic upgrade head && uv run python -m app.seed && uv run uvicorn app.main:app --reload --port 8000

dev-frontend: ## Фронтенд (Vite) на http://localhost:5173, /api проксируется на :8000
	$(FRONTEND) npm run dev

test: test-backend test-frontend ## Все тесты

test-backend: db ## Тесты бэкенда (нужен запущенный PostgreSQL)
	$(BACKEND) uv run pytest

test-frontend: ## Тесты фронтенда (vitest)
	$(FRONTEND) npm run test

lint: lint-backend lint-frontend style ## Все линтеры и проверки типов

lint-backend: ## ruff + mypy
	$(BACKEND) uv run ruff check . && uv run ruff format --check . && uv run mypy

lint-frontend: ## eslint + tsc
	$(FRONTEND) npm run lint && npm run typecheck

style: ## Проверка правил комментариев и docstring
	python3 tools/check_code_style.py

format: ## Автоформатирование
	$(BACKEND) uv run ruff format . && uv run ruff check --fix .
	$(FRONTEND) npm run format

migrate: ## Применить миграции к локальной БД
	$(BACKEND) uv run alembic upgrade head

revision: ## Новая миграция: make revision m="описание"
	$(BACKEND) uv run alembic revision --autogenerate -m "$(m)"

seed: ## Наполнить справочники, демо-аккаунты и демо-популяцию
	$(BACKEND) uv run python -m app.seed && uv run python -m app.seed.population

openapi: ## Выгрузить OpenAPI и перегенерировать типы фронтенда
	$(BACKEND) uv run python -m scripts.export_openapi
	$(FRONTEND) npm run gen:api

simulate: ## Симуляция адаптивного теста и отчёт в docs/validation
	$(BACKEND) uv run python -m evaluation.simulate_assessment

check: lint test ## Всё, что проверяет CI
