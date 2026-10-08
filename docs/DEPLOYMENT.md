# Развёртывание на VPS

Главный способ запуска «Скаута» — локальный: `docker compose up --build`, без настройки и без
интернета после сборки (см. [README](../README.md)). Этот документ — для случая, когда стенд нужно
держать доступным жюри по адресу в интернете на всё время оценки (ответ организаторов E10).

На сервере работает тот же `docker-compose.yml`, поверх него — оверлей
[deploy/docker-compose.vps.yml](../deploy/docker-compose.vps.yml) с Caddy. Код и образы те же,
что на ноутбуке.

## Что меняет оверлей

| Что | Локально | На VPS |
|---|---|---|
| Вход снаружи | Порты 8080, 8090 на хосте | Только Caddy: 80 и 443. Остальные порты закрыты (`ports: !reset []`) |
| HTTPS | Нет | Сертификаты Let's Encrypt, выпуск и продление автоматически, HTTP → HTTPS (308), HSTS |
| Приложение | http://localhost:8080 | `https://DOMAIN` |
| ФСП ID (эмулятор) | http://localhost:8090 | `https://fsp.DOMAIN` — issuer и redirect URI пересобираются из домена |
| Mailpit | http://localhost:8025 | `https://mail.DOMAIN` за паролем: письма подтверждения видят только жюри |
| Режим бэкенда | `APP_ENV=local` | `APP_ENV=production`: refresh-cookie с флагом `Secure`, вебхуки ATS только на HTTPS |
| Секреты | Значения по умолчанию | Обязательны: без `JWT_SECRET`, `ASSESSMENT_SECRET`, `FSP_CLIENT_SECRET`, `POSTGRES_PASSWORD` стенд не стартует, а бэкенд в production отказывается работать с секретами из репозитория |

Число процессов API задаёт `WEB_CONCURRENCY` (по умолчанию 2). Подбор и тест упираются в CPU,
поэтому на сервере ставьте его по числу ядер; каждый процесс занимает около 200 МБ — при четырёх
и больше поднимите лимит памяти бэкенда в `docker-compose.yml`. Каждый процесс держит до 20
соединений с базой: при `max_connections=100` в PostgreSQL безопасно до четырёх процессов, а
памяти базе нужно не меньше 512 МБ — при 256 МБ нагрузочный тест довёл её до OOM-killer.

`ASSESSMENT_SECRET` — ключ HMAC, из которого получается seed каждого экземпляра задания. Значение
по умолчанию лежит в репозитории; зная его, можно заранее вычислить задания любой сессии. Поэтому
в production бэкенд не стартует без собственного секрета.

## Что нужно

- VPS с Linux: 2 vCPU и 2 ГБ памяти достаточно (лимиты контейнеров в сумме около 1,4 ГБ, GPU не
  нужен). Нагрузочный тест — в [LOAD_TEST.md](LOAD_TEST.md).
- Docker Engine с Compose v2.24 или новее (нужен `!reset` в оверлее).
- Домен и три A-записи на IP сервера: `DOMAIN`, `fsp.DOMAIN`, `mail.DOMAIN`.
- Открытые порты 80 и 443: через 80 Let's Encrypt проверяет владение доменом.

## Пять шагов

```bash
git clone <репозиторий> scout && cd scout
cp deploy/vps.env.example deploy/vps.env
```

Заполните `deploy/vps.env`. Секреты — каждый своей командой:

```bash
openssl rand -hex 32
```

Хеш пароля Mailpit для жюри (в файле — в одинарных кавычках):

```bash
docker run --rm caddy:2.10-alpine caddy hash-password --plaintext 'пароль-для-жюри'
```

Запуск и проверка:

```bash
make vps-up
```

```bash
make vps-check DOMAIN=scout.example.ru
```

Первый старт занимает 1–2 минуты: бэкенд применяет миграции и создаёт демо-популяцию, Caddy
получает сертификаты. `make vps-check` проверяет API и базу, редирект на HTTPS, HSTS, маршруты
SPA, issuer ФСП ID на своём домене и пароль на Mailpit.

| Команда | Что делает |
|---|---|
| `make vps-up` | Собрать и поднять стенд (то же, что `docker compose -f docker-compose.yml -f deploy/docker-compose.vps.yml --env-file deploy/vps.env up --build -d`) |
| `make vps-logs` | Логи всех сервисов |
| `make vps-down` | Остановить; база и сертификаты сохраняются в томах |
| `make vps-check DOMAIN=…` | Проверка снаружи |

## Обновление и резервная копия

```bash
git pull && make vps-up
```

Миграции применяются при старте бэкенда. Копия базы:

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.vps.yml --env-file deploy/vps.env exec -T db pg_dump -U fsp fsp_scout > scout-$(date +%F).sql
```

## Проверить оверлей у себя

Оверлей проверяется без сервера и домена: Caddy сам выпускает локальный сертификат для имён
`*.localhost`. Отдельное имя проекта не трогает основной стенд.

```bash
cp deploy/vps.env.example deploy/vps.env   # DOMAIN=scout.localhost, секреты — любые длинные строки
docker compose -p fsp-scout-vps -f docker-compose.yml -f deploy/docker-compose.vps.yml --env-file deploy/vps.env up --build -d
deploy/check.sh scout.localhost --local
docker compose -p fsp-scout-vps -f docker-compose.yml -f deploy/docker-compose.vps.yml --env-file deploy/vps.env down -v
```

Так оверлей и проверялся перед сдачей: все шесть проверок `check.sh` проходят, бэкенд стартует в
production, refresh-cookie выдаётся с `Secure; HttpOnly; SameSite=strict`.

## Если что-то пошло не так

| Симптом | Причина и решение |
|---|---|
| `Задайте … в deploy/vps.env` при запуске | Не заполнена обязательная переменная — Compose называет какая |
| Caddy пишет `challenge failed` | A-записи ещё не обновились или закрыт порт 80. Проверьте `dig +short DOMAIN` и файрвол |
| Вход через ФСП ID возвращает ошибку redirect_uri | `DOMAIN` в `vps.env` не совпадает с адресом в браузере |
| Mailpit не принимает пароль | В хеше есть `$`: значение должно быть в одинарных кавычках |
| Бэкенд перезапускается | `make vps-logs`: в production он не стартует с dev-секретами — это защита, а не сбой |

## Что дальше для настоящего продакшена

Оверлей рассчитан на стенд для жюри. Для работы с реальными людьми понадобятся: настоящий ФСП ID
вместо эмулятора (меняются только `FSP_PUBLIC_URL`, `FSP_CLIENT_ID`, `FSP_CLIENT_SECRET`, см.
[FSP_INTEGRATION.md](FSP_INTEGRATION.md)), SMTP-сервис вместо Mailpit, отключение демо-данных
(`SEED_DEMO_USERS=false`), размещение в российском облаке (152-ФЗ, локализация ПДн) и регулярные
резервные копии базы вне сервера.
