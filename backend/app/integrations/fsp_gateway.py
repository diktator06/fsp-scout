from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.integrations.fsp_id import FspIdClient
from app.integrations.fsp_registry import FspRegistryClient


@dataclass(frozen=True, slots=True)
class FspGateway:
    """Точка доступа к внешней системе ФСП: вход по ФСП ID и реестр достижений."""

    identity: FspIdClient
    registry: FspRegistryClient


def build_fsp_gateway(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> FspGateway:
    """Собирает клиентов ФСП ID и реестра по настройкам (в тестах — с подменённым транспортом)."""
    identity = FspIdClient(settings, transport)
    return FspGateway(
        identity=identity, registry=FspRegistryClient(settings.fsp_registry_base_url, identity)
    )
