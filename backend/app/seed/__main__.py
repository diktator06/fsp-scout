import asyncio
import logging

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionFactory, engine
from app.seed.seeders import seed_demo_accounts, seed_reference_data

logger = logging.getLogger("app.seed")


async def main() -> None:
    """Наполняет справочники и демо-аккаунты одной транзакцией: либо всё, либо ничего."""
    settings = get_settings()
    configure_logging(settings.log_level)
    async with SessionFactory() as session:
        report = await seed_reference_data(session)
        if settings.seed_demo_users:
            await seed_demo_accounts(session, settings, report)
        await session.commit()
    logger.info("Сидирование завершено: %s", report.summary() or "изменений нет")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
