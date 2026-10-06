from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def enum_values(enum_cls: type[StrEnum]) -> list[str]:
    """Значения перечисления в том виде, в котором они лежат в базе."""
    return [member.value for member in enum_cls]


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Тип PostgreSQL ENUM по Python-перечислению.

    В базу пишем `value` (`candidate`), а не имя члена (`CANDIDATE`): так данные читаемы
    в psql и не зависят от переименования констант в коде.
    """
    return SAEnum(enum_cls, name=name, values_callable=enum_values, validate_strings=True)
