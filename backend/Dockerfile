# Статика Swagger UI 5 из npm: документация API должна открываться без доступа к CDN.
FROM node:24-alpine AS swagger-assets
WORKDIR /assets
RUN npm pack swagger-ui-dist@5.33.1 --silent \
 && tar -xzf swagger-ui-dist-*.tgz \
 && mkdir -p /swagger \
 && cp package/swagger-ui-bundle.js package/swagger-ui.css package/favicon-32x32.png /swagger/

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    XDG_CACHE_HOME=/tmp/.cache \
    PATH="/app/.venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /app

# WeasyPrint рисует PDF-профиль через Pango и HarfBuzz. DejaVu — запасной шрифт на
# случай символов, которых нет во встроенном Montserrat.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

# Зависимости ставятся отдельным слоем: при правке кода они берутся из кеша сборки.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
COPY --from=swagger-assets /swagger ./static/swagger
# Код и зависимости остаются во владении root и доступны приложению только на чтение.
# Заодно не нужен chown -R: он скопировал бы весь .venv в ещё один слой образа.
RUN useradd --system --uid 10001 --home-dir /app scout
USER scout

EXPOSE 8000
ENTRYPOINT ["sh", "scripts/entrypoint.sh"]
