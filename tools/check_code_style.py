import ast
import io
import re
import sys
import tokenize
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON_ROOTS = ("backend", "fsp-registry-mock", "tools")
TYPESCRIPT_ROOTS = ("frontend/src",)
SKIPPED_PARTS = frozenset({".venv", "node_modules", "__pycache__", "dist", "build", ".mypy_cache"})
GENERATED_FILES = frozenset({"schema.gen.ts"})

CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)
PYTHON_PRAGMA = re.compile(r"^#\s*(noqa|type:|pragma|fmt:|ruff:|mypy:|isort:)|^#!")
TS_PRAGMA = re.compile(
    r"(eslint-disable|eslint-enable|@ts-expect-error|@ts-ignore|prettier-ignore|^/// <reference)"
)
TS_COMMENT = re.compile(r"^(\s*)(//|/\*|\*)")


def iter_files(roots: tuple[str, ...], suffixes: tuple[str, ...]) -> Iterator[Path]:
    """Обходит исходники в указанных каталогах, пропуская зависимости, кеши и сгенерированные файлы."""
    for root in roots:
        base = ROOT / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if (
                path.suffix in suffixes
                and path.is_file()
                and not SKIPPED_PARTS.intersection(path.parts)
                and path.name not in GENERATED_FILES
            ):
                yield path


def _function_line_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    """Диапазоны строк тел всех функций и методов файла."""
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            body_start = node.body[0].lineno
            ranges.append((body_start, node.end_lineno or body_start))
    return ranges


def check_python_file(path: Path) -> list[str]:
    """Проверяет Python-файл на соблюдение правил документирования кода.

    Правила проекта:
    * у каждой функции и метода есть docstring на русском — первой строкой тела;
    * комментарии пишутся только внутри тел функций, а не над определениями
      и не на уровне модуля или класса (служебные pragma вроде `noqa` не в счёт);
    * текст комментариев — на русском.
    """
    relative = path.relative_to(ROOT)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    problems: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            docstring = ast.get_docstring(node)
            if not docstring:
                problems.append(f"{relative}:{node.lineno}: у функции «{node.name}» нет docstring")
            elif not CYRILLIC.search(docstring):
                problems.append(f"{relative}:{node.lineno}: docstring «{node.name}» не на русском")

    inside_functions = _function_line_ranges(tree)
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        line = token.start[0]
        text = token.string
        if PYTHON_PRAGMA.match(text) or "# noqa" in text:
            continue
        if not any(start <= line <= end for start, end in inside_functions):
            problems.append(f"{relative}:{line}: комментарий вне тела функции: {text[:60]}")
        elif not CYRILLIC.search(text):
            problems.append(f"{relative}:{line}: комментарий не на русском: {text[:60]}")
    return problems


def check_typescript_file(path: Path) -> list[str]:
    """Проверяет TypeScript-файл: комментарии только внутри функций и только на русском.

    Полноценного разбора TS здесь нет. Комментарий без отступа заведомо лежит
    на верхнем уровне модуля (над компонентом или функцией), такие и запрещаем.
    """
    relative = path.relative_to(ROOT)
    problems: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = TS_COMMENT.match(line)
        if not match or TS_PRAGMA.search(line):
            continue
        indent = match.group(1)
        if not indent:
            # Открывающая строка JSDoc без отступа — блок над функцией или компонентом.
            problems.append(f"{relative}:{number}: комментарий на верхнем уровне модуля")
        elif line.strip() in {"*/", "/**", "*"}:
            continue
        elif not CYRILLIC.search(line):
            problems.append(f"{relative}:{number}: комментарий не на русском: {line.strip()[:60]}")
    return problems


def main() -> int:
    """Запускает проверки по всему репозиторию и печатает найденные нарушения."""
    problems: list[str] = []
    for path in iter_files(PYTHON_ROOTS, (".py",)):
        problems.extend(check_python_file(path))
    for path in iter_files(TYPESCRIPT_ROOTS, (".ts", ".tsx")):
        problems.extend(check_typescript_file(path))

    if problems:
        print("Нарушены правила комментариев и docstring:")
        print("\n".join(f"  {problem}" for problem in problems))
        return 1
    print("Правила комментариев и docstring соблюдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
