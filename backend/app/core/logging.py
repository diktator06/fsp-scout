import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Настраивает формат логов приложения.

    Персональные данные (email, телефоны, тексты резюме) в логи не пишем: это одно
    из требований 152-ФЗ. Поэтому в сообщениях сервисов фигурируют только
    идентификаторы.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
