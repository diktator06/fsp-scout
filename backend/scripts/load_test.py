import argparse
import asyncio
import json
import os
import platform
import random
import re
import statistics
import subprocess
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

API = os.environ.get("LOAD_API", "http://localhost:8080/api/v1")
MAILPIT = os.environ.get("LOAD_MAILPIT", "http://localhost:8025")
DEMO_EMPLOYER = "employer@example.com"
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "ScoutDemo2026")
LOAD_PASSWORD = "LoadTest-2026"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VACANCIES_PATH = REPOSITORY_ROOT / "backend" / "evaluation" / "data" / "matching_vacancies.yaml"
REPORT_JSON = REPOSITORY_ROOT / "docs" / "validation" / "load_test.json"
REPORT_MD = REPOSITORY_ROOT / "docs" / "LOAD_TEST.md"
NEED_VACANCIES = (
    "backend-python-fintech",
    "frontend-react-ecom",
    "analytics-product-middle",
    "devops-middle",
)
EMPLOYER_ACTIONS = (
    ("shortlist", 30),
    ("refine", 10),
    ("bank", 30),
    ("card", 20),
    ("categories", 10),
)
RAMP_UP_SECONDS = 15.0
PROFILES = (
    ("working", "Рабочая нагрузка", (2.0, 6.0)),
    ("stress", "Стресс", (0.2, 0.6)),
)
P95_BUDGET_MS = {"read": 500.0, "write": 800.0}
ERROR_BUDGET = 0.01
TOKEN_IN_LINK = re.compile(r"token=([A-Za-z0-9_\-]+)")
TIMEOUT = httpx.Timeout(30.0)
WRITE_OPERATIONS = frozenset(
    {"register", "verify_email", "survey", "test_start", "test_answer", "refine"}
)


@dataclass
class Metrics:
    """Задержки по операциям и ошибки за прогон."""

    latencies: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    journeys: int = 0
    test_lengths: list[int] = field(default_factory=list)

    def record(self, name: str, started: float, response: httpx.Response | None) -> None:
        """Запоминает задержку; ответ 4xx/5xx или обрыв соединения — ошибка."""
        self.latencies[name].append((time.perf_counter() - started) * 1000)
        if response is None or response.status_code >= 400:
            self.errors[name] += 1


class RateLimited(RuntimeError):
    """Стенд ответил 429: нагрузка идёт с одного IP, лимиты нужно отключить."""


async def call(
    client: httpx.AsyncClient,
    metrics: Metrics,
    name: str,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response | None:
    """Запрос с замером времени; сетевую ошибку считаем ошибкой операции."""
    started = time.perf_counter()
    try:
        response = await client.request(method, url, **kwargs)
    except httpx.HTTPError:
        metrics.record(name, started, None)
        return None
    metrics.record(name, started, response)
    if response.status_code == 429:
        raise RateLimited(name)
    return response


@dataclass
class Setup:
    """Данные, общие для виртуальных пользователей."""

    employer_headers: dict[str, str]
    needs: list[str]
    specializations: list[dict[str, Any]]
    grades: dict[str, int]
    skills: dict[int, list[int]]
    bank_size: int


async def login(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    """Вход демо-работодателя: один токен на всех работодателей прогона."""
    response = await client.post(
        f"{API}/auth/login", json={"email": email, "password": DEMO_PASSWORD}
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def prepare(client: httpx.AsyncClient) -> Setup:
    """Потребности работодателя из размеченных вакансий и справочники для опроса."""
    headers = await login(client, DEMO_EMPLOYER)
    vacancies = {item["id"]: item for item in yaml.safe_load(VACANCIES_PATH.read_text())}
    needs = []
    for vacancy_id in NEED_VACANCIES:
        text = vacancies[vacancy_id]["text"]
        draft = (
            await client.post(f"{API}/employer/needs/parse", json={"text": text}, headers=headers)
        ).json()
        created = await client.post(
            f"{API}/employer/needs",
            json={
                "title": draft["title"],
                "raw_text": text,
                "team_description": "Команда продукта",
                "specialization_id": draft["specialization"]["id"],
                "grade_ids": [grade["id"] for grade in draft["grades"]],
                "skills": [
                    {"skill_id": item["skill"]["id"], "importance": item["importance"]}
                    for item in draft["skills"]
                ],
                "work_formats": draft["work_formats"] or ["remote"],
                "salary_from": draft["salary_from"],
                "salary_to": draft["salary_to"],
                "salary_gross": True,
            },
            headers=headers,
        )
        created.raise_for_status()
        needs.append(created.json()["id"])
    specializations = (await client.get(f"{API}/dictionaries/specializations")).json()
    grades = {
        item["code"]: item["id"] for item in (await client.get(f"{API}/dictionaries/grades")).json()
    }
    skills: dict[int, list[int]] = {}
    for specialization in specializations:
        found = (
            await client.get(
                f"{API}/dictionaries/skills",
                params={"specialization_id": specialization["id"], "limit": 8},
            )
        ).json()
        items = found["items"] if isinstance(found, dict) else found
        skills[specialization["id"]] = [item["id"] for item in items]
    bank = (
        await client.get(f"{API}/employer/candidates", params={"limit": 1}, headers=headers)
    ).json()
    return Setup(headers, needs, specializations, grades, skills, int(bank["total"]))


async def employer_user(
    client: httpx.AsyncClient,
    setup: Setup,
    metrics: Metrics,
    deadline: float,
    rng: random.Random,
    think: tuple[float, float],
) -> None:
    """Работодатель: подборки, уточнения, поиск по банку и карточки кандидатов."""
    names = [name for name, _ in EMPLOYER_ACTIONS]
    weights = [weight for _, weight in EMPLOYER_ACTIONS]
    seen: list[str] = []
    headers = setup.employer_headers
    await asyncio.sleep(rng.uniform(0, RAMP_UP_SECONDS))
    while time.monotonic() < deadline:
        action = rng.choices(names, weights)[0]
        need = rng.choice(setup.needs)
        if action == "shortlist":
            response = await call(
                client,
                metrics,
                "shortlist",
                "GET",
                f"{API}/employer/needs/{need}/shortlist",
                headers=headers,
            )
            if response is not None and response.status_code == 200:
                seen.extend(
                    entry["card"]["candidate_id"] for entry in response.json()["entries"][:5]
                )
        elif action == "refine":
            await call(
                client,
                metrics,
                "refine",
                "POST",
                f"{API}/employer/needs/{need}/shortlists",
                json={"confirmed_only": rng.random() < 0.5, "expand_grades": rng.random() < 0.3},
                headers=headers,
            )
        elif action == "bank":
            specialization = rng.choice(setup.specializations)["id"]
            response = await call(
                client,
                metrics,
                "bank",
                "GET",
                f"{API}/employer/candidates",
                params={
                    "specialization_id": specialization,
                    "limit": 20,
                    "offset": rng.randrange(0, 60),
                },
                headers=headers,
            )
            if response is not None and response.status_code == 200:
                seen.extend(item["card"]["candidate_id"] for item in response.json()["items"][:5])
        elif action == "card" and seen:
            await call(
                client,
                metrics,
                "card",
                "GET",
                f"{API}/employer/candidates/{rng.choice(seen[-50:])}",
                params={"need_id": need},
                headers=headers,
            )
        elif action == "categories":
            await call(
                client,
                metrics,
                "categories",
                "GET",
                f"{API}/employer/needs/{need}/categories",
                headers=headers,
            )
        await asyncio.sleep(rng.uniform(*think))


async def verification_token(client: httpx.AsyncClient, email: str) -> str | None:
    """Токен из письма в Mailpit — так же, как его получил бы человек."""
    for _ in range(50):
        search = await client.get(
            f"{MAILPIT}/api/v1/search", params={"query": f'to:"{email}"', "limit": 1}
        )
        messages = search.json().get("messages", [])
        if messages:
            message = await client.get(f"{MAILPIT}/api/v1/message/{messages[0]['ID']}")
            match = TOKEN_IN_LINK.search(message.json().get("Text", ""))
            return match.group(1) if match else None
        await asyncio.sleep(0.1)
    return None


async def candidate_journey(
    client: httpx.AsyncClient,
    setup: Setup,
    metrics: Metrics,
    rng: random.Random,
    run_id: str,
    think: tuple[float, float],
) -> None:
    """Новый кандидат: регистрация, письмо, подтверждение, опрос, полный тест, лента вакансий."""
    email = f"load.{run_id}.{uuid.uuid4().hex[:10]}@example.com"
    registered = await call(
        client,
        metrics,
        "register",
        "POST",
        f"{API}/auth/register",
        json={
            "email": email,
            "password": LOAD_PASSWORD,
            "role": "candidate",
            "accept_personal_data_processing": True,
        },
    )
    if registered is None or registered.status_code >= 400:
        return
    token = await verification_token(client, email)
    if token is None:
        metrics.errors["mail"] += 1
        return
    verified = await call(
        client, metrics, "verify_email", "POST", f"{API}/auth/verify-email", json={"token": token}
    )
    if verified is None or verified.status_code >= 400:
        return
    headers = {"Authorization": f"Bearer {verified.json()['access_token']}"}
    specialization = rng.choice(setup.specializations)["id"]
    grade = rng.choice(["junior", "middle", "senior"])
    survey = await call(
        client,
        metrics,
        "survey",
        "POST",
        f"{API}/assessment/surveys",
        json={
            "specialization_id": specialization,
            "claimed_grade_id": setup.grades[grade],
            "primary_skill_ids": setup.skills[specialization][:5],
            "experience_years": rng.uniform(1, 8),
            "work_formats": ["remote"],
        },
        headers=headers,
    )
    if survey is None or survey.status_code >= 400:
        return
    session = await call(
        client,
        metrics,
        "test_start",
        "POST",
        f"{API}/assessment/sessions",
        json={"target_grade_id": setup.grades[grade], "mode": "full"},
        headers=headers,
    )
    if session is None or session.status_code >= 400:
        return
    view = session.json()
    answered = 0
    while view["status"] == "in_progress" and view.get("current_item"):
        item = view["current_item"]
        options = item.get("options") or []
        answer = rng.choice(options)["key"] if options else str(rng.randint(0, 20))
        await asyncio.sleep(rng.uniform(*think))
        response = await call(
            client,
            metrics,
            "test_answer",
            "POST",
            f"{API}/assessment/sessions/{view['id']}/answers",
            json={"item_id": item["id"], "answer": answer},
            headers=headers,
        )
        if response is None or response.status_code >= 400:
            return
        view = response.json()
        answered += 1
    metrics.test_lengths.append(answered)
    await call(client, metrics, "vacancies_feed", "GET", f"{API}/vacancies", headers=headers)
    await call(
        client, metrics, "candidate_status", "GET", f"{API}/candidates/me/status", headers=headers
    )
    metrics.journeys += 1


async def candidate_user(
    client: httpx.AsyncClient,
    setup: Setup,
    metrics: Metrics,
    deadline: float,
    rng: random.Random,
    run_id: str,
    think: tuple[float, float],
) -> None:
    """Поток новых кандидатов: путь повторяется, пока не кончится время."""
    await asyncio.sleep(rng.uniform(0, RAMP_UP_SECONDS))
    while time.monotonic() < deadline:
        await candidate_journey(client, setup, metrics, rng, run_id, think)


def docker_stats() -> list[dict[str, str]]:
    """Снимок потребления контейнеров стенда (если Docker доступен с хоста)."""
    try:
        output = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    return [
        {"name": row["Name"], "cpu": row["CPUPerc"], "memory": row["MemUsage"]}
        for row in rows
        if row["Name"].startswith("fsp-scout-") and not row["Name"].startswith("fsp-scout-vps")
    ]


def percentile(values: list[float], share: float) -> float:
    """Перцентиль по ближайшему рангу."""
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(share * (len(ordered) - 1))))
    return ordered[index]


def summarize(metrics: Metrics, elapsed: float) -> dict[str, Any]:
    """Сводка по операциям: число, ошибки, p50/p95/p99 и бюджет p95."""
    operations: dict[str, dict[str, Any]] = {}
    for name, values in sorted(metrics.latencies.items()):
        kind = "write" if name in WRITE_OPERATIONS else "read"
        p95 = percentile(values, 0.95)
        operations[name] = {
            "kind": kind,
            "count": len(values),
            "errors": metrics.errors.get(name, 0),
            "p50_ms": round(percentile(values, 0.50), 1),
            "p95_ms": round(p95, 1),
            "p99_ms": round(percentile(values, 0.99), 1),
            "max_ms": round(max(values), 1),
            "within_budget": p95 <= P95_BUDGET_MS[kind],
        }
    total = sum(item["count"] for item in operations.values())
    errors = sum(metrics.errors.values())
    every = [value for values in metrics.latencies.values() for value in values]
    return {
        "requests": total,
        "errors": errors,
        "error_rate": round(errors / total, 4) if total else 0.0,
        "throughput_rps": round(total / elapsed, 1) if elapsed else 0.0,
        "p50_ms": round(percentile(every, 0.5), 1) if every else 0.0,
        "p95_ms": round(percentile(every, 0.95), 1) if every else 0.0,
        "operations": operations,
        "candidate_journeys": metrics.journeys,
        "mean_test_length": round(statistics.mean(metrics.test_lengths), 1)
        if metrics.test_lengths
        else 0.0,
    }


OPERATION_TITLES = {
    "shortlist": "Подборка по потребности",
    "refine": "Уточнение подборки (новая версия)",
    "bank": "Поиск по банку кандидатов",
    "card": "Карточка кандидата с баллом",
    "categories": "Рекомендованные категории и рынок",
    "register": "Регистрация",
    "verify_email": "Подтверждение email",
    "survey": "Опрос",
    "test_start": "Старт адаптивного теста",
    "test_answer": "Ответ на задание и выбор следующего",
    "vacancies_feed": "Лента вакансий по баллу",
    "candidate_status": "Статус кандидата",
}


def ru(value: float, digits: int = 1) -> str:
    """Число с десятичной запятой, как в остальной документации."""
    return f"{value:.{digits}f}".replace(".", ",")


def plural(count: int, one: str, few: str, many: str) -> str:
    """Существительное после числа: 1 кандидат, 2 кандидата, 5 кандидатов."""
    if 11 <= count % 100 <= 14:
        return many
    if count % 10 == 1:
        return one
    return few if 2 <= count % 10 <= 4 else many


def within_budget(summary: dict[str, Any]) -> bool:
    """Ошибок не больше 1 % и p95 каждой операции в бюджете."""
    operations: dict[str, dict[str, Any]] = summary["operations"]
    return summary["error_rate"] <= ERROR_BUDGET and all(
        bool(item["within_budget"]) for item in operations.values()
    )


def markdown(report: dict[str, Any]) -> str:
    """Документ LOAD_TEST.md из отчёта по двум профилям."""
    profiles: list[dict[str, Any]] = report["profiles"]
    working, stress = profiles[0], profiles[1]
    budgets = f"чтение — {P95_BUDGET_MS['read']:.0f} мс, запись — {P95_BUDGET_MS['write']:.0f} мс"
    summary_rows = []
    for profile in profiles:
        summary = profile["summary"]
        summary_rows.append(
            f"| {profile['title']} | {ru(profile['think'][0])}–{ru(profile['think'][1])} с | "
            f"{summary['requests']} | {ru(summary['throughput_rps'])} | "
            f"{summary['errors']} ({ru(summary['error_rate'] * 100, 2)} %) | "
            f"{summary['p50_ms']:.0f} / {summary['p95_ms']:.0f} | "
            f"{summary['candidate_journeys']} |"
        )
    names = list(working["summary"]["operations"])
    operation_rows = []
    for name in names:
        first = working["summary"]["operations"][name]
        second = stress["summary"]["operations"].get(name, {})
        operation_rows.append(
            f"| {OPERATION_TITLES.get(name, name)} | {first['count']} | "
            f"{first['p50_ms']:.0f} | {first['p95_ms']:.0f} | "
            f"{'да' if first['within_budget'] else '**нет**'} | "
            f"{second.get('p50_ms', 0):.0f} | {second.get('p95_ms', 0):.0f} |"
        )
    stats_rows = (
        "\n".join(
            f"| {row['name']} | {row['cpu']} | {row['memory']} |" for row in stress["docker_stats"]
        )
        or "| — | — | — |"
    )
    verdict = "бюджеты выдержаны" if within_budget(working["summary"]) else "есть превышения"
    bank = (
        f"{report['bank_size']} "
        f"{plural(report['bank_size'], 'кандидат', 'кандидата', 'кандидатов')}"
    )
    return f"""# Нагрузочный тест

> Документ собирается командой `make load-test` по живому стенду; исходные числа —
> [validation/load_test.json](validation/load_test.json).

{report["virtual_users"]} одновременных пользователей: {report["employers"]} работодателей строят и
уточняют подборки, ищут по банку и открывают карточки; {report["candidates"]} потоков новых
кандидатов проходят путь от регистрации до конца адаптивного теста. Из 1050 синтетических
кандидатов опубликованы и ищут работу {report["bank_size"]} — это и есть банк. Два профиля по
{report["duration_s"]:.0f} с:
рабочая нагрузка — люди читают экран между действиями, стресс — действия почти без пауз.

**Рабочая нагрузка: {verdict}** (бюджет p95: {budgets}, ошибок — не больше 1 %).

| Профиль | Пауза | Запросов | Запросов/с | Ошибок | p50 / p95, мс | Кандидатов прошли тест |
|---|---|---:|---:|---:|---:|---:|
{chr(10).join(summary_rows)}

## По операциям

Время — в миллисекундах, от клиента через nginx до ответа API.

| Операция | Запросов | p50 | p95 | В бюджете | p50 стресс | p95 стресс |
|---|---:|---:|---:|---|---:|---:|
{chr(10).join(operation_rows)}

## Ресурсы под стрессом

Снимок `docker stats` в середине стресс-профиля. Лимиты памяти заданы в `docker-compose.yml`.

| Контейнер | CPU | Память |
|---|---:|---:|
{stats_rows}

## Что изменили по итогам первого прогона

Первый прогон (один процесс API, без пауз между действиями) дал 19 запросов/с при p50 ≈ 2 с:
бэкенд упёрся в одно ядро, и даже лёгкие запросы ждали в очереди. Профилирование показало три
причины, все исправлены:

- русский стеммер текстовой близости вызывался ~100 тыс. раз на запрос рекомендованных
  категорий, а тексты кандидатов токенизировались по 2–3 раза — теперь стемминг кешируется, а
  токены и векторы считаются один раз за запрос: категории 231 → 111 мс, подборка 62 → 47 мс;
- проверка пароля argon2id шла в цикле событий и останавливала все запросы процесса на время
  входа и регистрации — теперь в отдельном потоке, не больше двух хешей одновременно на процесс
  (каждый занимает 64 МБ и несколько ядер);
- API работал одним процессом — теперь `WEB_CONCURRENCY` воркеров (по умолчанию 2; на сервере —
  по числу ядер, около 200 МБ памяти на процесс).

Второй прогон, уже с двумя процессами, нашёл проблему стабильности: под стрессом процесс
PostgreSQL убивал OOM-killer (лимит контейнера 256 МБ при `shared_buffers` 128 МБ и до 40
соединений), база уходила в восстановление, и 7,7 % запросов падали. Лимит базы поднят до
512 МБ; числа ниже — после исправления.

## Условия и ограничения

- Машина: {report["host"]}; стенд — `docker compose` на этой же машине, вместе с генератором
  нагрузки.
- Пользователи подключаются равномерно за первые 15 секунд, затем работают до конца профиля.
- Работодатели делят один демо-аккаунт и четыре потребности из размеченных вакансий
  (`evaluation/data/matching_vacancies.yaml`).
- Кандидаты регистрируются, достают ссылку из письма через API Mailpit, подтверждают email,
  проходят опрос и полный тест (12–20 заданий), отвечая случайно.
- Стенд для прогона поднимается с `RATE_LIMIT_ENABLED=false`: все виртуальные пользователи
  приходят с одного IP, и защита от перебора иначе ограничила бы регистрацию десятью в час.
- Поиск по банку без фильтра специализации (весь банк, {bank}) занимает около 300 мс:
  для сортировки по индексу профиля загружается весь пул. При росте банка это первое место для
  оптимизации — индекс профиля стоит хранить, а не считать на лету.

## Как воспроизвести

```bash
make load-stand   # стенд с 1050 кандидатами и выключенными лимитами, ~5 минут на наполнение
make load-test    # два профиля и этот документ, ~7 минут
make reset && make up   # вернуть обычный стенд
```
"""


async def run_profile(
    client: httpx.AsyncClient,
    setup: Setup,
    employers: int,
    candidates: int,
    duration: float,
    think: tuple[float, float],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Один профиль: параллельные пользователи и снимок ресурсов в середине."""
    run_id = datetime.now(UTC).strftime("%H%M%S")
    metrics = Metrics()
    deadline = time.monotonic() + duration
    started = time.monotonic()
    tasks = [
        employer_user(client, setup, metrics, deadline, random.Random(index), think)
        for index in range(employers)
    ] + [
        candidate_user(client, setup, metrics, deadline, random.Random(1000 + index), run_id, think)
        for index in range(candidates)
    ]
    gathered = asyncio.gather(*tasks)
    await asyncio.sleep(duration / 2)
    stats = await asyncio.to_thread(docker_stats)
    await gathered
    return summarize(metrics, time.monotonic() - started), stats


async def run(employers: int, candidates: int, duration: float) -> dict[str, Any]:
    """Прогон: подготовка, затем профили по очереди."""
    limits = httpx.Limits(max_connections=employers + candidates + 10)
    profiles = []
    async with httpx.AsyncClient(timeout=TIMEOUT, limits=limits) as client:
        setup = await prepare(client)
        print(f"Банк: {setup.bank_size} кандидатов, потребностей: {len(setup.needs)}")
        for key, title, think in PROFILES:
            summary, stats = await run_profile(
                client, setup, employers, candidates, duration, think
            )
            print(
                f"{title}: {summary['requests']} запросов, {summary['throughput_rps']} rps, "
                f"ошибок {summary['error_rate'] * 100:.2f} %, "
                f"p50 {summary['p50_ms']} мс, p95 {summary['p95_ms']} мс"
            )
            profiles.append(
                {
                    "key": key,
                    "title": title,
                    "think": list(think),
                    "summary": summary,
                    "docker_stats": stats,
                }
            )
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "host": (
            f"{platform.machine()}, {os.cpu_count()} ядер, {platform.system()} {platform.release()}"
        ),
        "virtual_users": employers + candidates,
        "employers": employers,
        "candidates": candidates,
        "duration_s": duration,
        "bank_size": setup.bank_size,
        "profiles": profiles,
    }


def main() -> None:
    """Запуск из командной строки: make load-test."""
    parser = argparse.ArgumentParser(description="Нагрузочный тест стенда «Скаута»")
    parser.add_argument("--employers", type=int, default=30)
    parser.add_argument("--candidates", type=int, default=20)
    parser.add_argument("--duration", type=float, default=150.0)
    args = parser.parse_args()
    try:
        report = asyncio.run(run(args.employers, args.candidates, args.duration))
    except RateLimited as error:
        raise SystemExit(
            f"Стенд ответил 429 на «{error}». Поднимите его для нагрузки: make load-stand"
        ) from error
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    REPORT_MD.write_text(markdown(report))
    for profile in report["profiles"]:
        print(profile["title"])
        for name, item in profile["summary"]["operations"].items():
            print(
                f"  {name:18} n={item['count']:5} p50={item['p50_ms']:7.1f} "
                f"p95={item['p95_ms']:7.1f}"
            )


if __name__ == "__main__":
    main()
