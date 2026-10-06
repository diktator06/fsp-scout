from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AccountDisabledError, InvalidTokenError, PermissionDeniedError
from app.core.security import decode_access_token
from app.crud import user_crud
from app.models.user import User, UserRole


async def resolve_user_by_access_token(
    session: AsyncSession, access_token: str, settings: Settings
) -> User:
    """Находит пользователя по access-токену и проверяет, что он ещё может работать.

    Роль берём из базы, а не из токена. Если методист отзовёт права, они пропадут
    сразу, а не через 15 минут, когда истечёт токен.
    """
    claims = decode_access_token(access_token, settings)
    user = await user_crud.get(session, claims.user_id)
    if user is None:
        raise InvalidTokenError()
    if not user.is_active:
        raise AccountDisabledError()
    return user


def ensure_role(user: User, allowed: frozenset[UserRole]) -> User:
    """Проверяет, что роль пользователя входит в разрешённый набор."""
    if user.role not in allowed:
        raise PermissionDeniedError(
            details={"required_roles": sorted(role.value for role in allowed)}
        )
    return user
