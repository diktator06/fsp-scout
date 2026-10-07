# Эмулятор ФСП ID и реестра достижений для демо-стенда «Скаута».
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

COPY app ./app
# Код во владении root и доступен процессу только на чтение. Ключ подписи живёт в памяти
# и создаётся заново при каждом старте: бэкенд перечитывает JWKS по незнакомому kid.
RUN useradd --system --uid 10002 --home-dir /app fsp
USER fsp

EXPOSE 8090
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=2)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090", "--no-server-header", "--proxy-headers"]
