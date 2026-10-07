import asyncio
import logging
import time

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionFactory, engine
from app.seed.demo_fsp import seed_demo_fsp_links
from app.seed.demo_population import seed_demo_population
from app.seed.demo_vacancies import seed_demo_vacancies

logger = logging.getLogger("app.seed")


async def main() -> None:
    """Наполняет стенд демо-популяцией, если это разрешено настройками.

    Отдельный шаг после справочников: около сотни кандидатов проходят тест настоящим
    сервисом оценки, это занимает 15–30 секунд при первом старте стенда. Затем часть
    из них привязывается к участникам эмулятора ФСП ID и получает их достижения.
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    if not (settings.seed_demo_users and settings.seed_demo_population):
        logger.info("Демо-популяция отключена настройками")
        return
    started = time.monotonic()
    summary = await seed_demo_population(SessionFactory, settings)
    logger.info("Демо-популяция: %s за %.0f с", summary, time.monotonic() - started)
    started = time.monotonic()
    fsp_summary = await seed_demo_fsp_links(SessionFactory, settings)
    logger.info("ФСП в демо-данных: %s за %.0f с", fsp_summary, time.monotonic() - started)
    vacancies_summary = await seed_demo_vacancies(SessionFactory, settings)
    await engine.dispose()
    logger.info("Вакансии в демо-данных: %s", vacancies_summary)


if __name__ == "__main__":
    asyncio.run(main())
