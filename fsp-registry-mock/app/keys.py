import hashlib
from functools import lru_cache
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm


class SigningKey:
    """Ключ RS256 провайдера: подписывает токены и публикуется в JWKS.

    Ключ создаётся при старте процесса. После перезапуска эмулятора у ключа новый
    `kid`, и клиент обязан перечитать JWKS — так же ведёт себя Keycloak при ротации.
    """

    def __init__(self) -> None:
        """Генерирует пару RSA-2048 и вычисляет идентификатор ключа."""
        self._private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_der = self._private.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.kid = hashlib.sha256(public_der).hexdigest()[:16]

    def jwk(self) -> dict[str, Any]:
        """Публичная часть ключа в формате JWK."""
        data: dict[str, Any] = RSAAlgorithm.to_jwk(self._private.public_key(), as_dict=True)
        return {**data, "kid": self.kid, "use": "sig", "alg": "RS256"}

    def sign(self, claims: dict[str, Any]) -> str:
        """Подписывает набор claims."""
        return jwt.encode(claims, self._private, algorithm="RS256", headers={"kid": self.kid})

    def verify(self, token: str, audience: str, issuer: str) -> dict[str, Any]:
        """Проверяет подпись, срок, издателя и аудиторию токена."""
        claims: dict[str, Any] = jwt.decode(
            token,
            self._private.public_key(),
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
        )
        return claims


@lru_cache
def get_signing_key() -> SigningKey:
    """Ключ провайдера на всё время работы процесса."""
    return SigningKey()
