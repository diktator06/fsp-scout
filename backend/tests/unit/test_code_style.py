import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_comment_and_docstring_rules_are_respected() -> None:
    """В репозитории соблюдены правила документирования кода.

    Docstring на русском есть у каждой функции, висячих комментариев нет.
    """
    result = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "tools" / "check_code_style.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
