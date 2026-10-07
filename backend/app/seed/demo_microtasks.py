import logging
import math
import uuid
from datetime import UTC, datetime, timedelta
from random import Random

from app.core.config import Settings
from app.crud import (
    candidate_profile_crud,
    microtask_crud,
    recruiter_crud,
    specialization_crud,
    user_crud,
)
from app.models.microtask import MicroTaskKind
from app.schemas.microtask import GradeRequest, MicroTaskCreate
from app.seed.demo_population import (
    DEMO_EMPLOYER_EMAIL,
    SessionFactory,
    SimulatedClock,
    load_population_data,
)
from app.services.microtasks.candidate_service import CandidateTaskService
from app.services.microtasks.employer_service import EmployerTaskService

logger = logging.getLogger(__name__)

MICROTASK_SEED = 2028
HISTORY_SHARE = 0.5
APPROACH_ANSWER = (
    "Разобью задачу на шаги, начну с измерений и самых дешёвых гипотез, "
    "затем закреплю решение тестами и мониторингом."
)


def _probability(theta: float) -> float:
    """Вероятность хорошего ответа растёт со способностью — как в тесте."""
    return 1 / (1 + math.exp(-1.3 * (theta + 0.2)))


async def seed_demo_microtasks(session_factory: SessionFactory, settings: Settings) -> str:
    """Задачи демо-компании и история их решения синтетическими кандидатами.

    История проходит через настоящие сервисы с часами в прошлом: «решить» проверяет
    система, «подход» оценивает работодатель. Поэтому у части кандидатов есть фактор
    M с правдоподобной давностью, а у остальных — нейтральное «задач пока не было».
    """
    data = load_population_data()["demo_company"].get("microtasks", [])
    rng = Random(MICROTASK_SEED)
    async with session_factory() as session:
        employer = await user_crud.get_by_email(session, DEMO_EMPLOYER_EMAIL)
        recruiter = await recruiter_crud.get_by_user_id(session, employer.id) if employer else None
        if employer is None or recruiter is None:
            return "демо-компании нет — микрозадачи пропущены"
        if await microtask_crud.list_for_company(session, recruiter.company_id):
            return "микрозадачи демо-компании уже есть"
        specializations = {
            item.code: item.id for item in await specialization_crud.list_all(session)
        }
        employer_service = EmployerTaskService(session)
        tasks_by_spec: dict[str, list[uuid.UUID]] = {}
        for item in data:
            created = await employer_service.create(
                employer,
                MicroTaskCreate(
                    kind=MicroTaskKind(item["kind"]),
                    title=item["title"],
                    statement=item["statement"],
                    specialization_id=specializations[item["specialization"]],
                    answer_value=item.get("answer_value"),
                    answer_tolerance=item.get("answer_tolerance", 0.0),
                    rubric=item.get("rubric", ""),
                ),
            )
            tasks_by_spec.setdefault(item["specialization"], []).append(created.id)

        graded = 0
        now = datetime.now(UTC)
        for code, task_ids in tasks_by_spec.items():
            candidates = await candidate_profile_crud.list_with_theta_by_email_prefix(
                session, f"demo.{code.replace('_', '-')}."
            )
            tested = [item for item in candidates if item[2] is not None]
            for profile, user, theta in rng.sample(tested, k=round(len(tested) * HISTORY_SHARE)):
                for task_id in rng.sample(task_ids, k=rng.randint(1, len(task_ids))):
                    task = await microtask_crud.get(session, task_id)
                    assert task is not None
                    clock = SimulatedClock(now - timedelta(days=rng.uniform(3, 150)))
                    candidate_service = CandidateTaskService(session, settings, clock=clock)
                    assignment = await candidate_service.assign(profile.id, task)
                    await session.commit()
                    clock.advance(rng.uniform(600, 7200))
                    good = rng.random() < _probability(theta or 0.0)
                    if task.kind is MicroTaskKind.SOLVE:
                        expected = float(task.answer_key["value"])
                        answer = str(expected if good else expected + 7)
                        await candidate_service.submit(user, assignment.id, answer)
                    else:
                        await candidate_service.submit(user, assignment.id, APPROACH_ANSWER)
                        clock.advance(rng.uniform(3600, 86400))
                        rating = rng.choice((4, 5)) if good else rng.choice((2, 3))
                        await EmployerTaskService(session, clock=clock).grade(
                            employer,
                            assignment.id,
                            GradeRequest(rating=rating, feedback="Спасибо за разбор"),
                        )
                    graded += 1
    return f"микрозадач +{len(data)}, оценённых решений +{graded}"
