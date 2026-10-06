from random import Random

from app.models.assessment import ResponseFormat
from app.services.assessment.item_generators.base import GeneratedItem, family, single_choice

_CHOICE = ResponseFormat.SINGLE_CHOICE

_BASIC_SCENARIOS = (
    ("POST /api/orders успешно создал заказ и вернул его в теле ответа", "201 Created"),
    ("GET /api/orders/{id} запросил заказ, которого в базе нет", "404 Not Found"),
    ("GET /api/orders вернул список заказов", "200 OK"),
    ("DELETE /api/orders/{id} удалил заказ, тело ответа пустое", "204 No Content"),
    ("Обработчик упал с необработанным исключением", "500 Internal Server Error"),
    (
        "Страница навсегда переехала на новый адрес, клиент должен запомнить новый URL",
        "301 Moved Permanently",
    ),
)

_ADVANCED_SCENARIOS = (
    ("Запрос без заголовка Authorization к закрытому эндпоинту", "401 Unauthorized"),
    ("Пользователь вошёл, но пытается удалить чужой заказ", "403 Forbidden"),
    ("Регистрация с email, который уже занят другим аккаунтом", "409 Conflict"),
    (
        "Тело запроса — корректный JSON, но дата окончания раньше даты начала",
        "422 Unprocessable Content",
    ),
    ("Клиент превысил лимит 100 запросов в минуту", "429 Too Many Requests"),
    (
        "PUT с заголовком If-Match, ETag которого уже не совпадает с текущей версией",
        "412 Precondition Failed",
    ),
    ("На эндпоинт, который принимает только GET, пришёл POST", "405 Method Not Allowed"),
)


def _status_item(
    rng: Random, scenarios: tuple[tuple[str, str], ...], close: tuple[str, ...]
) -> GeneratedItem:
    """Задание «какой код ответа вернуть»; дистракторы берутся из близких по смыслу кодов."""
    scenario, correct = rng.choice(scenarios)
    pool = [status for status in close if status != correct]
    rng.shuffle(pool)
    return single_choice(
        rng,
        prompt=f"Какой HTTP-статус должен вернуть сервис?\n\n{scenario}.",
        correct=correct,
        distractors=pool,
    )


@family(
    "http.status_basic",
    title="Базовые коды ответа HTTP",
    competency="http_api",
    grade="intern",
    response_format=_CHOICE,
    time_limit=60,
    discrimination=1.0,
)
def status_basic(rng: Random) -> GeneratedItem:
    """Успешные ответы, «не найдено», ошибка сервера и редирект."""
    close = (*tuple(status for _, status in _BASIC_SCENARIOS), "400 Bad Request", "302 Found")
    return _status_item(rng, _BASIC_SCENARIOS, close)


@family(
    "http.status_advanced",
    title="Коды ошибок клиента: 401, 403, 409, 422, 429",
    competency="http_api",
    grade="middle",
    response_format=_CHOICE,
    time_limit=75,
    discrimination=1.4,
    difficulty_offset=-0.3,
)
def status_advanced(rng: Random) -> GeneratedItem:
    """Тонкие различия ошибок клиента: аутентификация против авторизации, конфликт, валидация."""
    close = (*tuple(status for _, status in _ADVANCED_SCENARIOS), "400 Bad Request")
    return _status_item(rng, _ADVANCED_SCENARIOS, close)


_IDEMPOTENT = ("GET", "PUT", "DELETE", "HEAD", "OPTIONS")


@family(
    "http.idempotency",
    title="Идемпотентность HTTP-методов",
    competency="http_api",
    grade="junior",
    response_format=_CHOICE,
    time_limit=60,
    discrimination=1.1,
)
def idempotency(rng: Random) -> GeneratedItem:
    """Повтор идемпотентного запроса не меняет состояние сверх первого вызова."""
    return single_choice(
        rng,
        prompt=(
            "Клиент мог не получить ответ из-за обрыва сети и повторяет запрос. Повтор какого "
            "метода по семантике HTTP (RFC 9110) может создать ещё один ресурс?"
        ),
        correct="POST",
        distractors=rng.sample(_IDEMPOTENT, 4),
    )


_CACHE_OPTIONS = (
    "Ответ возьмётся из кеша браузера, запроса к серверу не будет",
    "Браузер отправит условный запрос с If-None-Match; если ресурс не менялся, сервер ответит 304",
    "Браузер отправит обычный запрос и получит 200 с полным телом",
    "Запрос завершится ошибкой: срок кеширования истёк",
)


@family(
    "http.cache_freshness",
    title="Кеширование: Cache-Control и ETag",
    competency="http_api",
    grade="senior",
    response_format=_CHOICE,
    time_limit=120,
    discrimination=1.3,
    difficulty_offset=-0.3,
)
def cache_freshness(rng: Random) -> GeneratedItem:
    """Свежий ответ берётся из кеша; устаревший или no-cache требует ревалидации по ETag."""
    max_age = rng.choice([60, 120, 300, 600, 3600])
    variant = rng.choice(["fresh", "stale", "no_cache"])
    if variant == "fresh":
        elapsed = rng.randint(5, max_age - 5)
        header = f"Cache-Control: max-age={max_age}"
        correct = _CACHE_OPTIONS[0]
    elif variant == "stale":
        elapsed = max_age + rng.randint(5, max_age)
        header = f"Cache-Control: max-age={max_age}"
        correct = _CACHE_OPTIONS[1]
    else:
        elapsed = rng.randint(5, 60)
        header = "Cache-Control: no-cache"
        correct = _CACHE_OPTIONS[1]
    etag = f'"{rng.randrange(16**6):06x}"'
    return single_choice(
        rng,
        prompt=(
            "Браузер получил ответ на GET /api/catalog с заголовками ниже. Через "
            f"{elapsed} с страница снова запрашивает тот же адрес. Что произойдёт?"
        ),
        code=f"HTTP/1.1 200 OK\n{header}\nETag: {etag}\nContent-Type: application/json",
        code_language="http",
        correct=correct,
        distractors=[option for option in _CACHE_OPTIONS if option != correct],
        params={"variant": variant, "elapsed": elapsed},
    )
