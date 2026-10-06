from pydantic import BaseModel, Field, field_validator

from app.models.dictionary import SkillKind
from app.schemas.common import ORMModel

_CODE_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"
_SLUG_PATTERN = r"^[a-z0-9][a-z0-9+#._-]{0,63}$"
MAX_SKILL_ALIASES = 20


def clean_aliases(values: list[str]) -> list[str]:
    """Чистит список алиасов: обрезает пробелы, убирает пустые и дубли без учёта регистра."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        alias = raw.strip()
        key = alias.casefold()
        if alias and key not in seen:
            seen.add(key)
            result.append(alias)
    return result


class IndustryRead(ORMModel):
    """Отрасль."""

    id: int
    code: str
    name: str


class SpecializationBrief(ORMModel):
    """Краткие сведения о специализации внутри других объектов."""

    id: int
    code: str
    name: str


class SpecializationRead(SpecializationBrief):
    """Специализация."""

    description: str
    sort_order: int


class SpecializationCreate(BaseModel):
    """Новая специализация. Категории для всех грейдов создаются автоматически."""

    code: str = Field(pattern=_CODE_PATTERN, examples=["gamedev"])
    name: str = Field(min_length=2, max_length=128, examples=["Разработка игр"])
    description: str = Field(default="", max_length=2000)
    sort_order: int = Field(default=100, ge=0, le=1000)


class SpecializationUpdate(BaseModel):
    """Изменение специализации. Код неизменяем: на него ссылаются категории и задания."""

    name: str | None = Field(default=None, min_length=2, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = Field(default=None, ge=0, le=1000)


class GradeBrief(ORMModel):
    """Краткие сведения о грейде."""

    id: int
    code: str
    name: str
    rank: int


class GradeRead(GradeBrief):
    """Грейд с пояснением и порогом по шкале способностей."""

    experience_hint: str
    description: str
    default_theta_cut: float


class CategoryRead(ORMModel):
    """Категория кандидатов: специализация × грейд."""

    id: int
    code: str
    title: str
    theta_cut: float
    specialization: SpecializationBrief
    grade: GradeBrief


class SkillRead(ORMModel):
    """Навык справочника."""

    id: int
    slug: str
    name: str
    kind: SkillKind
    aliases: list[str]


class SkillCreate(BaseModel):
    """Новый навык."""

    slug: str = Field(pattern=_SLUG_PATTERN, examples=["fastapi"])
    name: str = Field(min_length=1, max_length=128, examples=["FastAPI"])
    kind: SkillKind
    aliases: list[str] = Field(default_factory=list, max_length=MAX_SKILL_ALIASES)
    specialization_ids: list[int] = Field(
        default_factory=list, description="Специализации, для которых навык типичен"
    )

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, value: list[str]) -> list[str]:
        """Убирает пустые и повторяющиеся алиасы."""
        return clean_aliases(value)


class SkillUpdate(BaseModel):
    """Изменение навыка. Slug неизменяем: по нему навыки ищутся в резюме и вакансиях."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    kind: SkillKind | None = None
    aliases: list[str] | None = Field(default=None, max_length=MAX_SKILL_ALIASES)

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, value: list[str] | None) -> list[str] | None:
        """Убирает пустые и повторяющиеся алиасы."""
        return clean_aliases(value) if value is not None else None
