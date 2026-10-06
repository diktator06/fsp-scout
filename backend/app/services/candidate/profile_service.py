import secrets
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainValidationError, PermissionDeniedError
from app.crud import (
    assessment_session_crud,
    candidate_profile_crud,
    candidate_skill_crud,
    consent_crud,
    education_crud,
    privacy_settings_crud,
    skill_lookup_crud,
    survey_crud,
    work_experience_crud,
)
from app.models.candidate import CandidateProfile
from app.models.consent import ConsentType
from app.models.user import User, UserRole
from app.schemas.candidate import (
    CandidateProfileRead,
    CandidateProfileUpdate,
    CandidateSkillRead,
    CandidateStatusRead,
    ConsentsRead,
    EducationRead,
    OnboardingStep,
    PrivacySettingsRead,
    PrivacySettingsUpdate,
    WorkExperienceRead,
)
from app.schemas.dictionary import CategoryRead, SkillRead
from app.services.consents import BANK_PUBLICATION_POLICY_VERSION

_ALIAS_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ALIAS_LENGTH = 4


def profile_completeness(profile: CandidateProfile, skills: int, experiences: int) -> int:
    """Заполненность профиля в процентах по семи понятным критериям."""
    checks = [
        bool(profile.full_name),
        bool(profile.city),
        len(profile.about.strip()) >= 50,
        profile.experience_years is not None,
        skills >= 3,
        bool(profile.work_formats),
        experiences >= 1,
    ]
    return round(100 * sum(checks) / len(checks))


def is_profile_completed(profile: CandidateProfile) -> bool:
    """Минимум для перехода к опросу: имя, опыт и формат работы."""
    return (
        bool(profile.full_name)
        and profile.experience_years is not None
        and bool(profile.work_formats)
    )


def _generate_alias() -> str:
    """Псевдоним вида A7F3: короткий, без похожих символов (I/1, O/0) и без ПДн."""
    return "".join(secrets.choice(_ALIAS_ALPHABET) for _ in range(_ALIAS_LENGTH))


class CandidateProfileService:
    """Профиль кандидата: анкета, приватность, согласия и статус онбординга."""

    def __init__(self, session: AsyncSession) -> None:
        """Получает сессию БД."""
        self._session = session

    async def ensure_profile(self, user: User, *, for_update: bool = False) -> CandidateProfile:
        """Профиль кандидата; при первом обращении создаётся вместе с настройками приватности.

        Транзакцию не фиксирует: метод вызывают и другие сценарии (опрос, тест),
        которые фиксируют свои изменения вместе с созданием профиля.
        """
        if user.role is not UserRole.CANDIDATE:
            raise PermissionDeniedError("Профиль кандидата доступен только кандидатам")
        profile = await candidate_profile_crud.get_by_user_id(
            self._session, user.id, for_update=for_update
        )
        if profile is not None:
            return profile

        alias = _generate_alias()
        while await candidate_profile_crud.alias_taken(self._session, alias):
            alias = _generate_alias()
        created = await candidate_profile_crud.create(
            self._session, {"user_id": user.id, "public_alias": alias}
        )
        await privacy_settings_crud.get_or_create(self._session, created.id)
        reloaded = await candidate_profile_crud.get_by_user_id(
            self._session, user.id, for_update=for_update
        )
        if reloaded is None:
            raise RuntimeError("Профиль не найден сразу после создания")
        return reloaded

    async def get_view(self, user: User) -> CandidateProfileRead:
        """Профиль целиком: анкета, навыки, опыт, образование и категория."""
        profile = await self.ensure_profile(user)
        await self._session.commit()
        return await self._build_view(user, profile)

    async def update(self, user: User, payload: CandidateProfileUpdate) -> CandidateProfileRead:
        """Сохраняет анкету целиком.

        Категорию и подтверждённые навыки анкета изменить не может: их выставляет
        только тест. Неизвестные навыки отклоняются списком, чтобы форма могла
        подсветить конкретные позиции.
        """
        profile = await self.ensure_profile(user, for_update=True)
        skill_ids = [item.skill_id for item in payload.skills]
        missing = sorted(
            set(skill_ids) - await skill_lookup_crud.existing_ids(self._session, skill_ids)
        )
        if missing:
            raise DomainValidationError(
                "Указаны несуществующие навыки", details={"skill_ids": missing}
            )

        await candidate_profile_crud.update(
            self._session,
            profile,
            payload.model_dump(exclude={"skills", "experiences", "educations"}),
        )
        await candidate_skill_crud.replace_declared(
            self._session, profile.id, {item.skill_id: item.self_level for item in payload.skills}
        )
        await work_experience_crud.replace_all(
            self._session, profile.id, [item.model_dump() for item in payload.experiences]
        )
        await education_crud.replace_all(
            self._session, profile.id, [item.model_dump() for item in payload.educations]
        )
        await self._session.commit()
        return await self._build_view(user, profile)

    async def get_privacy(self, user: User) -> PrivacySettingsRead:
        """Текущие настройки приватности."""
        profile = await self.ensure_profile(user)
        settings = await privacy_settings_crud.get_or_create(self._session, profile.id)
        await self._session.commit()
        return PrivacySettingsRead.model_validate(settings)

    async def update_privacy(
        self, user: User, payload: PrivacySettingsUpdate
    ) -> PrivacySettingsRead:
        """Меняет настройки видимости полей и раскрываемые каналы связи."""
        profile = await self.ensure_profile(user)
        settings = await privacy_settings_crud.get_or_create(self._session, profile.id)
        await privacy_settings_crud.update(self._session, settings, payload)
        await self._session.commit()
        return PrivacySettingsRead.model_validate(settings)

    async def get_consents(self, user: User) -> ConsentsRead:
        """Действующие согласия кандидата."""
        processing = await consent_crud.active(
            self._session, user.id, ConsentType.PERSONAL_DATA_PROCESSING
        )
        publication = await consent_crud.active(
            self._session, user.id, ConsentType.BANK_PUBLICATION
        )
        return ConsentsRead(
            personal_data_processing=processing is not None,
            bank_publication=publication is not None,
            bank_publication_granted_at=publication.granted_at if publication else None,
        )

    async def set_bank_publication(
        self, user: User, granted: bool, ip_address: str | None
    ) -> ConsentsRead:
        """Даёт или отзывает согласие на публикацию профиля в банке кандидатов.

        Отзыв действует сразу: банк работодателя фильтрует кандидатов по действующему
        согласию, так что профиль исчезнет из выдачи при следующем запросе.
        """
        await self.ensure_profile(user)
        active = await consent_crud.active(self._session, user.id, ConsentType.BANK_PUBLICATION)
        if granted and active is None:
            await consent_crud.grant(
                self._session,
                user_id=user.id,
                consent_type=ConsentType.BANK_PUBLICATION,
                document_version=BANK_PUBLICATION_POLICY_VERSION,
                ip_address=ip_address,
            )
        elif not granted and active is not None:
            await consent_crud.revoke_active(
                self._session, user.id, ConsentType.BANK_PUBLICATION, datetime.now(UTC)
            )
        await self._session.commit()
        return await self.get_consents(user)

    async def status(self, user: User) -> CandidateStatusRead:
        """Шаг онбординга: профиль → опрос → выбор грейда → тест → готово."""
        profile = await self.ensure_profile(user)
        await self._session.commit()
        survey = await survey_crud.latest_for_candidate(self._session, profile.id)
        active = await assessment_session_crud.active_for_candidate(self._session, profile.id)
        consents = await self.get_consents(user)
        skills = await candidate_skill_crud.list_with_skills(self._session, profile.id)
        experiences = await work_experience_crud.list_for_candidate(self._session, profile.id)

        completed = is_profile_completed(profile)
        step: OnboardingStep
        if not completed:
            step = "profile"
        elif survey is None:
            step = "survey"
        elif active is not None:
            step = "test"
        elif profile.current_category is None:
            step = "grade"
        else:
            step = "done"
        return CandidateStatusRead(
            onboarding_step=step,
            profile_completed=completed,
            survey_completed=survey is not None,
            category=CategoryRead.model_validate(profile.current_category)
            if profile.current_category
            else None,
            active_session_id=active.id if active else None,
            bank_published=consents.bank_publication,
            completeness=profile_completeness(profile, len(skills), len(experiences)),
        )

    async def _build_view(self, user: User, profile: CandidateProfile) -> CandidateProfileRead:
        """Собирает представление профиля из связанных таблиц."""
        refreshed = await candidate_profile_crud.get_by_user_id(self._session, user.id)
        current = refreshed or profile
        skills = await candidate_skill_crud.list_with_skills(self._session, current.id)
        experiences = await work_experience_crud.list_for_candidate(self._session, current.id)
        educations = await education_crud.list_for_candidate(self._session, current.id)
        return CandidateProfileRead(
            id=current.id,
            email=user.email,
            public_alias=current.public_alias,
            full_name=current.full_name,
            phone=current.phone,
            telegram=current.telegram,
            city=current.city,
            about=current.about,
            experience_years=current.experience_years,
            team_roles=current.team_roles,
            soft_skills=current.soft_skills,
            work_formats=current.work_formats,
            relocation_ready=current.relocation_ready,
            salary_expectation_from=current.salary_expectation_from,
            search_status=current.search_status,
            category=CategoryRead.model_validate(current.current_category)
            if current.current_category
            else None,
            grade_assigned_at=current.grade_assigned_at,
            skills=[
                CandidateSkillRead(
                    skill=SkillRead.model_validate(skill),
                    self_level=link.self_level,
                    source=link.source,
                    is_verified=link.is_verified,
                    verified_at=link.verified_at,
                )
                for link, skill in skills
            ],
            experiences=[WorkExperienceRead.model_validate(item) for item in experiences],
            educations=[EducationRead.model_validate(item) for item in educations],
            completeness=profile_completeness(current, len(skills), len(experiences)),
            updated_at=current.updated_at,
        )
