from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"


@lru_cache
def _environment() -> Environment:
    """Окружение Jinja2 для писем: автоэкранирование HTML и ошибка на неизвестной переменной."""
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_email(template_name: str, **context: Any) -> tuple[str, str]:
    """Рендерит текстовую и HTML-версии письма из пары шаблонов `<имя>.txt` и `<имя>.html`.

    Текстовая версия обязательна: часть почтовых клиентов и фильтров смотрит только на неё.
    """
    env = _environment()
    text_body = env.get_template(f"{template_name}.txt").render(**context)
    html_body = env.get_template(f"{template_name}.html").render(**context)
    return text_body, html_body
