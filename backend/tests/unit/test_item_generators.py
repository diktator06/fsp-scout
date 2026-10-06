import contextlib
import io
import json
import shutil
import sqlite3
import subprocess
from collections import Counter
from random import Random

import pytest

from app.models.assessment import ResponseFormat
from app.services.assessment.item_generators import REGISTRY, generate_instance, instance_seed
from app.services.assessment.item_generators.base import (
    GeneratedItem,
    NodeCheck,
    PythonCheck,
    SqliteCheck,
)

FAMILIES = sorted(REGISTRY)
SEEDS = range(40)
CHECK_SEEDS = range(12)
NODE = shutil.which("node")


def _families_with_checks() -> list[str]:
    """Семейства, у которых генератор выдаёт исполнимую проверку ответа."""
    return [code for code in FAMILIES if REGISTRY[code].generate(Random(0)).check is not None]


def _normalize(value: object) -> str:
    """Сравнение вывода без учёта пробелов и переносов строк."""
    return " ".join(str(value).split())


def _expected(item: GeneratedItem) -> object:
    """Правильный ответ экземпляра: текст варианта или число."""
    return item.answer["text"] if item.answer["kind"] == "choice" else item.answer["value"]


def _matches(item: GeneratedItem, output: str) -> bool:
    """Совпадает ли фактический вывод проверки с ключом ответа."""
    if item.answer["kind"] == "choice":
        return _normalize(output) == _normalize(item.answer["text"])
    return abs(float(output) - float(item.answer["value"])) <= item.answer["tolerance"] + 1e-9


def _run_python(code: str) -> str:
    """Выполняет проверочный код генератора и возвращает напечатанное."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exec(code, {})
    return buffer.getvalue().strip()


def _run_sqlite(check: SqliteCheck) -> str:
    """Выполняет запрос на таблицах экземпляра во встроенной SQLite."""
    connection = sqlite3.connect(":memory:")
    for statement in check.setup:
        connection.execute(statement)
    return str(connection.execute(check.query).fetchone()[0])


def test_registry_covers_all_specializations_and_grades() -> None:
    """В банке есть семейства всех компетенций blueprint и всех четырёх номинальных грейдов."""
    grades = Counter(spec.nominal_grade for spec in REGISTRY.values())
    assert len(REGISTRY) >= 70
    assert set(grades) == {"intern", "junior", "middle", "senior"}
    assert min(grades.values()) >= 8


@pytest.mark.parametrize("code", FAMILIES)
def test_family_instances_are_deterministic_and_well_formed(code: str) -> None:
    """Экземпляр полностью задаётся seed, а вариант ответа — один из четырёх различных."""
    spec = REGISTRY[code]
    for seed in SEEDS:
        item = generate_instance(spec, seed)
        assert generate_instance(spec, seed) == item
        assert item.response_format is spec.response_format
        if item.response_format is ResponseFormat.SINGLE_CHOICE:
            assert len(item.options) == 4
            assert len(set(item.options)) == 4
            assert item.answer["correct"] in {"a", "b", "c", "d"}
            index = "abcd".index(item.answer["correct"])
            assert item.options[index] == item.answer["text"]
        else:
            assert item.answer["kind"] == "numeric"
            assert item.answer["tolerance"] >= 0


@pytest.mark.parametrize("code", FAMILIES)
def test_client_payload_never_contains_answer(code: str) -> None:
    """Данные для кандидата не содержат ключа ответа ни в каком виде."""
    item = generate_instance(REGISTRY[code], 7)
    payload = json.dumps(item.client_payload(), ensure_ascii=False)
    assert "answer" not in item.client_payload()
    assert "correct" not in payload
    assert "tolerance" not in payload


@pytest.mark.parametrize("code", FAMILIES)
def test_instances_vary_between_seeds(code: str) -> None:
    """Разные seed дают разные экземпляры: выученный ответ одного не подходит к другому."""
    payloads = {
        json.dumps(generate_instance(REGISTRY[code], seed).client_payload(), ensure_ascii=False)
        for seed in SEEDS
    }
    assert len(payloads) >= 4


@pytest.mark.parametrize("code", _families_with_checks())
def test_answer_key_matches_real_execution(code: str) -> None:
    """Ключ ответа совпадает с реальным выполнением кода, запроса или выражения.

    Эталон в генераторе вычисляется отдельной логикой, а здесь сверяется с
    настоящим интерпретатором. Это защита от ошибок в банке заданий.
    """
    for seed in CHECK_SEEDS:
        item = generate_instance(REGISTRY[code], seed)
        check = item.check
        if isinstance(check, PythonCheck):
            if "import pandas" in check.code:
                pytest.importorskip("pandas")
            output = _run_python(check.code)
        elif isinstance(check, SqliteCheck):
            output = _run_sqlite(check)
        elif isinstance(check, NodeCheck):
            if NODE is None:
                pytest.skip("Node.js не установлен")
            output = subprocess.run(
                [NODE, "-e", check.code], capture_output=True, text=True, timeout=20, check=True
            ).stdout.strip()
        else:
            continue
        assert _matches(item, output), (
            f"seed {seed}: ожидалось {_expected(item)!r}, получено {output!r}"
        )


def test_instance_seed_depends_on_secret_session_and_position() -> None:
    """Seed экземпляра нельзя предсказать без секрета и он различается по позициям и сессиям."""
    base = instance_seed("secret", "salt", 1, "py.list_slicing")
    assert base == instance_seed("secret", "salt", 1, "py.list_slicing")
    assert base != instance_seed("other", "salt", 1, "py.list_slicing")
    assert base != instance_seed("secret", "salt2", 1, "py.list_slicing")
    assert base != instance_seed("secret", "salt", 2, "py.list_slicing")
