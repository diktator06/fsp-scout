#!/bin/sh
# Точка входа контейнера бэкенда: миграции, справочники и демо-данные, затем API.
set -eu

echo "Применяю миграции…"
alembic upgrade head

echo "Наполняю справочники…"
python -m app.seed

echo "Запускаю API на :8000"
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --proxy-headers \
  --forwarded-allow-ips="*" \
  --no-server-header
