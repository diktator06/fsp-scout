#!/bin/sh
# Точка входа контейнера бэкенда: миграции, справочники и демо-данные, затем API.
set -eu

echo "Применяю миграции…"
alembic upgrade head

echo "Наполняю справочники…"
python -m app.seed

echo "Создаю демо-популяцию (кандидаты проходят тест настоящим сервисом оценки)…"
python -m app.seed.population

# Подбор и тест упираются в CPU, а один процесс Python занимает одно ядро. Несколько
# воркеров делят нагрузку; фоновая отправка вебхуков в каждом из них безопасна —
# outbox забирает события через SKIP LOCKED.
echo "Запускаю API на :8000, воркеров: ${WEB_CONCURRENCY:-2}"
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers "${WEB_CONCURRENCY:-2}" \
  --proxy-headers \
  --forwarded-allow-ips="*" \
  --no-server-header
