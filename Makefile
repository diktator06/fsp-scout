# Скаут — частые команды разработки. Список целей: make help

COMPOSE := docker compose
KEYCLOAK_COMPOSE := $(COMPOSE) -f docker-compose.yml -f docker-compose.keycloak.yml
VPS_COMPOSE := $(COMPOSE) -f docker-compose.yml -f deploy/docker-compose.vps.yml --env-file deploy/vps.env
BACKEND := cd backend &&
FRONTEND := cd frontend &&
MOCK := cd fsp-registry-mock &&
EVAL_DATABASE_URL ?= postgresql+asyncpg://fsp:fsp@localhost:5432/fsp_scout_eval

.DEFAULT_GOAL := help
.PHONY: help up up-keycloak down-keycloak keycloak-smoke vps-up vps-down vps-logs vps-check down restart logs ps reset db install install-backend install-frontend install-mock \
        dev-backend dev-frontend dev-mock test test-backend test-frontend test-mock lint \
        lint-backend lint-frontend lint-mock style format migrate revision seed openapi simulate \
        eval-matching validate-assessment validation-report libraries load-stand load-test submission check

help: ## Показать список команд
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

up: ## Собрать и поднять весь стенд в фоне
	$(COMPOSE) up --build -d

up-keycloak: ## Поднять стенд с ФСП ID на полноценном Keycloak (порт 8081)
	$(KEYCLOAK_COMPOSE) up --build -d

down-keycloak: ## Остановить стенд с Keycloak (данные БД сохраняются)
	$(KEYCLOAK_COMPOSE) down

keycloak-smoke: ## Проверить живой стенд с Keycloak: OIDC, токены, claims, привязка и вход
	$(BACKEND) uv run python -m scripts.keycloak_smoke

vps-up: ## VPS: собрать и поднять стенд за Caddy с HTTPS (нужен deploy/vps.env)
	$(VPS_COMPOSE) up --build -d

vps-down: ## VPS: остановить стенд (данные и сертификаты сохраняются)
	$(VPS_COMPOSE) down

vps-logs: ## VPS: логи всех сервисов
	$(VPS_COMPOSE) logs -f --tail=200

vps-check: ## VPS: проверить развёрнутый стенд, make vps-check DOMAIN=scout.example.ru
	deploy/check.sh $(DOMAIN)

down: ## Остановить стенд (данные БД сохраняются)
	$(COMPOSE) down

restart: down up ## Перезапустить стенд

logs: ## Логи всех сервисов
	$(COMPOSE) logs -f --tail=200

ps: ## Состояние контейнеров
	$(COMPOSE) ps

reset: ## Полный сброс: удалить контейнеры и данные БД
	$(COMPOSE) down -v

db: ## Поднять PostgreSQL, Mailpit и эмулятор ФСП (для локальной разработки и тестов)
	$(COMPOSE) up -d db mailpit fsp-registry-mock

install: install-backend install-frontend install-mock ## Установить все зависимости

install-backend: ## Зависимости бэкенда (uv)
	$(BACKEND) uv sync

install-frontend: ## Зависимости фронтенда (npm)
	$(FRONTEND) npm ci

install-mock: ## Зависимости эмулятора ФСП (uv)
	$(MOCK) uv sync

dev-backend: db ## Бэкенд с автоперезагрузкой на http://localhost:8000
	$(BACKEND) uv run alembic upgrade head && uv run python -m app.seed && uv run uvicorn app.main:app --reload --port 8000

dev-frontend: ## Фронтенд (Vite) на http://localhost:5173, /api проксируется на :8000
	$(FRONTEND) npm run dev

dev-mock: ## Эмулятор ФСП ID и реестра на http://localhost:8090 без Docker
	$(MOCK) uv run uvicorn app.main:app --reload --port 8090

test: test-backend test-frontend test-mock ## Все тесты

test-backend: db ## Тесты бэкенда (нужен запущенный PostgreSQL)
	$(BACKEND) uv run pytest

test-frontend: ## Тесты фронтенда (vitest)
	$(FRONTEND) npm run test

test-mock: ## Тесты эмулятора ФСП
	$(MOCK) uv run pytest

lint: lint-backend lint-frontend lint-mock style ## Все линтеры и проверки типов

lint-backend: ## ruff + mypy
	$(BACKEND) uv run ruff check . && uv run ruff format --check . && uv run mypy

lint-frontend: ## eslint + tsc
	$(FRONTEND) npm run lint && npm run typecheck

lint-mock: ## ruff + mypy эмулятора ФСП
	$(MOCK) uv run ruff check . && uv run ruff format --check . && uv run mypy

style: ## Проверка правил комментариев и docstring
	python3 tools/check_code_style.py

format: ## Автоформатирование
	$(BACKEND) uv run ruff format . && uv run ruff check --fix .
	$(MOCK) uv run ruff format . && uv run ruff check --fix .
	$(FRONTEND) npm run format

migrate: ## Применить миграции к локальной БД
	$(BACKEND) uv run alembic upgrade head

revision: ## Новая миграция: make revision m="описание"
	$(BACKEND) uv run alembic revision --autogenerate -m "$(m)"

seed: ## Справочники, демо-аккаунты, демо-популяция и привязки ФСП (нужен эмулятор)
	$(BACKEND) uv run python -m app.seed && uv run python -m app.seed.population

openapi: ## Выгрузить OpenAPI, перегенерировать типы фронтенда и docs/API.md
	$(BACKEND) uv run python -m scripts.export_openapi
	$(FRONTEND) npm run gen:api
	python3 tools/api_reference.py

simulate: ## Симуляция адаптивного теста и отчёт в docs/validation
	$(BACKEND) uv run python -m evaluation.simulate_assessment

validate-assessment: ## Валидация теста: оценщики, разделяющая сила, утечки, списывание
	$(BACKEND) uv run python -m evaluation.assessment_validation

eval-matching: ## Оценка подбора на размеченных парах (P@10, nDCG@10, MRR) в отдельной базе
	$(BACKEND) DATABASE_URL=$(EVAL_DATABASE_URL) uv run python -m evaluation.matching_eval

validation-report: ## Собрать docs/VALIDATION.md из отчётов docs/validation
	$(BACKEND) uv run python -m evaluation.report

load-stand: ## Стенд для нагрузочного теста: 1050 кандидатов, лимиты частоты выключены
	$(COMPOSE) up --build -d
	$(COMPOSE) run --rm --no-deps --entrypoint python -e DEMO_POPULATION_PER_SPECIALIZATION=150 backend -m app.seed.population
	RATE_LIMIT_ENABLED=false $(COMPOSE) up -d backend

load-test: ## Нагрузочный тест по живому стенду (make load-stand) и docs/LOAD_TEST.md
	$(BACKEND) uv run python -m scripts.load_test

submission: ## Сопроводительная документация в PDF и DOCX из docs/SUBMISSION.md (нужен pandoc)
	pandoc docs/SUBMISSION.md --standalone --css style.css -o docs/submission/scout-documentation.html
	$(BACKEND) uv run python -c "import weasyprint; weasyprint.HTML('../docs/submission/scout-documentation.html').write_pdf('../docs/submission/scout-documentation.pdf')"
	pandoc docs/SUBMISSION.md -o docs/submission/scout-documentation.docx
	rm docs/submission/scout-documentation.html

libraries: ## Собрать docs/LIBRARIES.md из манифестов и lock-файлов
	$(BACKEND) uv run python ../tools/libraries.py

check: lint test ## Всё, что проверяет CI
