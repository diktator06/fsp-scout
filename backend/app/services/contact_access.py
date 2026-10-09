import uuid
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import audit_log_crud, contact_disclosure_crud
from app.models.candidate import CandidateProfile, ContactChannel, PrivacySettings
from app.models.invitation import ContactDisclosure, DisclosureReason
from app.schemas.cards import DisclosedContacts


class ContactAccessPolicy:
    """Единственная точка, через которую работодатель получает контакты кандидата.

    Право на контакты даёт только запись `contact_disclosures`. Она появляется, когда
    кандидат принимает приглашение или сам откликается. Каждое раскрытие пишется в
    журнал аудита (152-ФЗ, docs/MATCHING.md, раздел 7).
    """

    def __init__(self, session: AsyncSession) -> None:
        """Получает сессию БД."""
        self._session = session

    async def disclosure(
        self, company_id: uuid.UUID, candidate_id: uuid.UUID
    ) -> ContactDisclosure | None:
        """Раскрытие контактов кандидата этой компании, если оно было."""
        return await contact_disclosure_crud.get_for_pair(self._session, company_id, candidate_id)

    async def disclosures(
        self, company_id: uuid.UUID, candidate_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, ContactDisclosure]:
        """Раскрытия для пачки кандидатов (для меток в выдаче)."""
        return await contact_disclosure_crud.disclosed_candidates(
            self._session, company_id, candidate_ids
        )

    async def disclose(
        self,
        *,
        company_id: uuid.UUID,
        candidate_id: uuid.UUID,
        reason: DisclosureReason,
        source_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> ContactDisclosure:
        """Открывает контакты кандидата компании. Повторное раскрытие ничего не меняет.

        Транзакцию не фиксирует: раскрытие происходит в одной транзакции с принятием
        приглашения, иначе возможен статус «принято» без доступа к контактам.
        """
        existing = await self.disclosure(company_id, candidate_id)
        if existing is not None:
            return existing
        disclosure = await contact_disclosure_crud.create(
            self._session,
            {
                "company_id": company_id,
                "candidate_id": candidate_id,
                "reason": reason,
                "source_id": source_id,
            },
        )
        await audit_log_crud.record(
            self._session,
            actor_user_id=actor_user_id,
            action="contacts_disclosed",
            entity_type="candidate_profile",
            entity_id=candidate_id,
            meta={
                "company_id": str(company_id),
                "reason": reason.value,
                "source_id": str(source_id),
            },
        )
        return disclosure

    @staticmethod
    def contacts(
        disclosure: ContactDisclosure | None,
        profile: CandidateProfile,
        email: str,
        privacy: PrivacySettings | None,
    ) -> DisclosedContacts | None:
        """Контакты для работодателя: только при раскрытии и только разрешённые каналы.

        ФИО раскрывается вместе с любым каналом связи: без имени контакт бесполезен.
        """
        if disclosure is None:
            return None
        channels = set(privacy.revealed_channels if privacy else [])
        return DisclosedContacts(
            full_name=profile.full_name,
            email=email if ContactChannel.EMAIL.value in channels else None,
            phone=profile.phone if ContactChannel.PHONE.value in channels else None,
            telegram=profile.telegram if ContactChannel.TELEGRAM.value in channels else None,
            disclosed_at=disclosure.disclosed_at,
            reason=disclosure.reason,
        )
