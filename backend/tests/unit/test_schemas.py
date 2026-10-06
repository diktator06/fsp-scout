import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.dictionary import SkillCreate, SpecializationCreate


def _registration(**overrides: object) -> dict[str, object]:
    """Корректные данные регистрации с возможностью переопределить поля."""
    data: dict[str, object] = {
        "email": "Ivan.Petrov@Example.com",
        "password": "Sk0ut-2026",
        "role": "candidate",
        "accept_personal_data_processing": True,
    }
    data.update(overrides)
    return data


def test_registration_normalizes_email_to_lowercase() -> None:
    """Email приводится к нижнему регистру: адреса сравниваются без учёта регистра."""
    assert RegisterRequest(**_registration()).email == "ivan.petrov@example.com"  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("password", "expected_message"),
    [
        ("short1", "at least 8"),
        ("onlyletters", "хотя бы одну букву и одну цифру"),
        ("1234567890", "хотя бы одну букву и одну цифру"),
        (" Spaced-pass1", "пробелом"),
    ],
)
def test_registration_rejects_weak_passwords(password: str, expected_message: str) -> None:
    """Слишком короткие пароли, пароли без букв или цифр и с пробелами по краям отклоняются."""
    with pytest.raises(ValidationError) as error:
        RegisterRequest(**_registration(password=password))  # type: ignore[arg-type]
    assert expected_message in str(error.value)


def test_registration_requires_personal_data_consent() -> None:
    """Без согласия на обработку ПДн регистрация невозможна."""
    with pytest.raises(ValidationError) as error:
        RegisterRequest(**_registration(accept_personal_data_processing=False))  # type: ignore[arg-type]
    assert "согласие" in str(error.value)


def test_methodist_cannot_self_register() -> None:
    """Роль методиста недоступна при самостоятельной регистрации."""
    with pytest.raises(ValidationError):
        RegisterRequest(**_registration(role="methodist"))  # type: ignore[arg-type]


def test_login_normalizes_email() -> None:
    """При входе email нормализуется так же, как при регистрации."""
    assert LoginRequest(email=" HR@Example.COM ", password="x").email == "hr@example.com"


def test_skill_aliases_are_deduplicated_case_insensitively() -> None:
    """Пустые и повторяющиеся алиасы навыка отбрасываются."""
    skill = SkillCreate(
        slug="fastapi",
        name="FastAPI",
        kind="framework",
        aliases=["ФастАПИ", "фастапи", " ", "fast api"],
    )
    assert skill.aliases == ["ФастАПИ", "fast api"]


@pytest.mark.parametrize("code", ["Backend", "1backend", "back-end", "b"])
def test_specialization_code_must_be_snake_case(code: str) -> None:
    """Код специализации — латиница в нижнем регистре и подчёркивания."""
    with pytest.raises(ValidationError):
        SpecializationCreate(code=code, name="Название")
