from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ping_database(session: AsyncSession) -> bool:
    """Проверяет, что база отвечает на простейший запрос (используется в /health)."""
    result = await session.scalar(text("SELECT 1"))
    return bool(result == 1)
