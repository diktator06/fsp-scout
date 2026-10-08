import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from app.core.exceptions import UnsafeWebhookUrlError

_BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}


def _is_public(address: str) -> bool:
    """Адрес из интернета: не локальный, не частный, не служебный."""
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def ensure_public_destination(url: str, *, allow_private: bool, require_https: bool) -> None:
    """Защита от SSRF: вебхук не должен стучаться во внутреннюю сеть платформы.

    Иначе работодатель мог бы указать адрес вроде `http://db:5432` или облачного
    сервиса метаданных и через журнал доставок читать ответы внутренних систем.
    Имя разрешается в IP прямо перед отправкой, а не только при сохранении: так не
    срабатывает подмена DNS-записи после проверки. Для локального стенда проверку
    можно выключить настройкой `WEBHOOK_ALLOW_PRIVATE_URLS`.
    """
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise UnsafeWebhookUrlError("Нужен адрес вида https://ats.example.com/hooks/scout")
    if require_https and parts.scheme != "https":
        raise UnsafeWebhookUrlError("Получатель должен принимать запросы по HTTPS")
    if allow_private:
        return
    host = parts.hostname.lower()
    if host in _BLOCKED_HOSTS or host.endswith((".local", ".internal", ".localhost")):
        raise UnsafeWebhookUrlError()
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM
        )
    except OSError as error:
        raise UnsafeWebhookUrlError("Не удалось найти адрес получателя в DNS") from error
    addresses = {str(info[4][0]) for info in infos}
    if not addresses or not all(_is_public(address) for address in addresses):
        raise UnsafeWebhookUrlError()
