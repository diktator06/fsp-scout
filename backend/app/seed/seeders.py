import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import hash_password
from app.crud import (
    category_crud,
    consent_crud,
    grade_crud,
    industry_crud,
    skill_crud,
    specialization_crud,
    specialization_skill_crud,
    user_crud,
)
from app.models.consent import ConsentType
from app.models.dictionary import Grade, Specialization
from app.models.user import UserRole
from app.services.consents import PERSONAL_DATA_POLICY_VERSION
from app.services.dictionary_service import build_category_code, build_category_title

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"

DEMO_ACCOUNTS: tuple[tuple[str, UserRole], ...] = (
    ("candidate@example.com", UserRole.CANDIDATE),
    ("employer@example.com", UserRole.EMPLOYER),
    ("methodist@example.com", UserRole.METHODIST),
)


@dataclass
class SeedReport:
    """Сколько записей создано и обновлено по каждому справочнику."""

    created: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)

    def count(self, entity: str, *, created: bool) -> None:
        """Учитывает одну созданную или обновлённую запись."""
        bucket = self.created if created else self.updated
        bucket[entity] = bucket.get(entity, 0) + 1

    def summary(self) -> str:
        """Строка для лога: «specializations +7/~0, …»."""
        entities = sorted(set(self.created) | set(self.updated))
        return ", ".join(
            f"{name} +{self.created.get(name, 0)}/~{self.updated.get(name, 0)}" for name in entities
        )


def load_records(file_name: str) -> list[dict[str, Any]]:
    """Читает YAML-файл со списком записей справочника."""
    with (DATA_DIR / file_name).open(encoding="utf-8") as stream:
        records = yaml.safe_load(stream) or []
    if not isinstance(records, list):
        raise ValueError(f"{file_name}: ожидается список записей")
    return records


async def _upsert_by_code(
    session: AsyncSession,
    crud: Any,
    records: list[dict[str, Any]],
    entity: str,
    report: SeedReport,
) -> None:
    """Создаёт или обновляет записи справочника, сопоставляя их по полю `code`.

    Сидирование идемпотентно: повторный запуск при каждом старте контейнера
    подтягивает правки из YAML и ничего не дублирует.
    """
    for record in records:
        existing = await crud.get_by_code(session, record["code"])
        if existing is None:
            await crud.create(session, record)
            report.count(entity, created=True)
        else:
            changes = {
                key: value for key, value in record.items() if getattr(existing, key) != value
            }
            if changes:
                await crud.update(session, existing, changes)
                report.count(entity, created=False)


async def _ensure_categories(session: AsyncSession, report: SeedReport) -> None:
    """Гарантирует категорию для каждой пары «специализация × грейд».

    Порог `theta_cut` берётся из грейда только при создании. Позже его может уточнить
    калибровка, и затирать откалиброванное значение сидом нельзя.
    """
    specializations: list[Specialization] = list(await specialization_crud.list_all(session))
    grades: list[Grade] = list(await grade_crud.list_all(session))
    for specialization in specializations:
        for grade in grades:
            title = build_category_title(specialization, grade)
            category = await category_crud.get_by_pair(session, specialization.id, grade.id)
            if category is None:
                await category_crud.create(
                    session,
                    {
                        "specialization_id": specialization.id,
                        "grade_id": grade.id,
                        "code": build_category_code(specialization, grade),
                        "title": title,
                        "theta_cut": grade.default_theta_cut,
                    },
                )
                report.count("categories", created=True)
            elif category.title != title:
                await category_crud.update(session, category, {"title": title})
                report.count("categories", created=False)


async def _upsert_skills(session: AsyncSession, report: SeedReport) -> None:
    """Создаёт или обновляет навыки и их связи со специализациями."""
    spec_ids = {spec.code: spec.id for spec in await specialization_crud.list_all(session)}
    for record in load_records("skills.yaml"):
        weights_by_code: dict[str, float] = record.pop("specializations", {}) or {}
        unknown = set(weights_by_code) - set(spec_ids)
        if unknown:
            raise ValueError(f"Навык {record['slug']}: неизвестные специализации {sorted(unknown)}")

        skill = await skill_crud.get_by_slug(session, record["slug"])
        if skill is None:
            skill = await skill_crud.create(session, record)
            report.count("skills", created=True)
        else:
            changes = {key: value for key, value in record.items() if getattr(skill, key) != value}
            if changes:
                await skill_crud.update(session, skill, changes)
                report.count("skills", created=False)

        await specialization_skill_crud.replace_for_skill(
            session,
            skill.id,
            {spec_ids[code]: float(weight) for code, weight in weights_by_code.items()},
        )


async def seed_reference_data(session: AsyncSession) -> SeedReport:
    """Наполняет справочники из YAML-файлов `app/seed/data`. Транзакцию не фиксирует."""
    report = SeedReport()
    await _upsert_by_code(
        session, industry_crud, load_records("industries.yaml"), "industries", report
    )
    await _upsert_by_code(
        session,
        specialization_crud,
        load_records("specializations.yaml"),
        "specializations",
        report,
    )
    await _upsert_by_code(session, grade_crud, load_records("grades.yaml"), "grades", report)
    await _ensure_categories(session, report)
    await _upsert_skills(session, report)
    return report


async def seed_demo_accounts(session: AsyncSession, settings: Settings, report: SeedReport) -> None:
    """Создаёт подтверждённые демо-аккаунты всех трёх ролей, если их ещё нет.

    Пароль тестовый и берётся из настроек (`DEMO_PASSWORD`). Существующие аккаунты
    не трогаем, чтобы не сбрасывать пароль, который пользователь мог сменить.
    """
    now = datetime.now(UTC)
    password_hash = hash_password(settings.demo_password)
    for email, role in DEMO_ACCOUNTS:
        if await user_crud.get_by_email(session, email):
            continue
        user = await user_crud.create_local(
            session,
            email=email,
            password_hash=password_hash,
            role=role,
            is_email_verified=True,
            verified_at=now,
        )
        await consent_crud.grant(
            session,
            user_id=user.id,
            consent_type=ConsentType.PERSONAL_DATA_PROCESSING,
            document_version=PERSONAL_DATA_POLICY_VERSION,
            ip_address=None,
        )
        report.count("demo_users", created=True)
