import argparse
import asyncio
import json
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from random import Random
from statistics import mean, pstdev
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.crud.candidate_search import PoolQuery
from app.models.matching import SkillImportance
from app.services.matching.candidate_pool import CandidatePoolService, PoolMember
from app.services.matching.engine import MatchingContext, MatchingEngine, ScoredMember, SkillCatalog
from app.services.matching.match_scoring import MATCH_WEIGHTS
from app.services.matching.need_parser import CatalogGrade, ParsedNeed, parse_need_text
from app.services.matching.verified_score import VerifiedScore
from evaluation import database
from evaluation.bm25 import Bm25Index
from evaluation.metrics import (
    PARTIAL,
    bootstrap_interval,
    ideal_precision_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from evaluation.population import EVALUATION_SEED, describe, generate_population
from evaluation.relevance import CandidateTruth, VacancyTruth, relevance, to_gross

DATA_PATH = Path(__file__).resolve().parent / "data" / "matching_vacancies.yaml"
REPORT_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "validation" / "matching_evaluation.json"
)
TOP_K = 10
RECALL_K = 50
DEFAULT_PER_SPECIALIZATION = 60
DEFAULT_REPLICATIONS = 3
FOLDS = 3
FIT_CEILING = 2
INFLATED_OVERCLAIM = 0.5
INFLATED_UNDERCLAIM = 0.1
WEIGHT_STEP = 0.05
WEIGHT_BOUNDS = {
    "skills": (0.2, 0.45),
    "verified": (0.1, 0.4),
    "semantic": (0.05, 0.2),
    "conditions": (0.1, 0.35),
}

SYSTEMS: dict[str, tuple[str, str]] = {
    "scout": (
        "«Скаут»",
        "Текст вакансии → разбор → жёсткие фильтры по категории → балл соответствия",
    ),
    "scout_reviewed": (
        "«Скаут», потребность выверена",
        "Поля потребности из разметки: качество ранжирования без ошибок разбора текста",
    ),
    "scout_expanded": (
        "«Скаут» с соседними грейдами",
        "Переключатель подборки «соседние грейды» включён всегда, а не только при нехватке",
    ),
    "keyword": (
        "Ключевые слова (BM25)",
        "Поиск по самоописанию кандидата по всей базе, как в классических базах резюме",
    ),
    "keyword_filters": (
        "Ключевые слова + фильтры самоописания",
        "BM25 среди кандидатов с заявленными специализацией и грейдом из вакансии",
    ),
}
ABLATIONS: dict[str, tuple[str, str]] = {
    "no_test": (
        "Без теста",
        "Категория и навыки только со слов кандидата: фильтр по заявленному грейду, "
        "навыки не подтверждены, в индексе профиля нет фактора теста",
    ),
    "no_test_inflated": (
        "Без теста, грейд завышает половина",
        "То же, но заявленный грейд завышает каждый второй: на платформе, где грейд "
        "решает попадание в выдачу, у самоописания появляется стимул врать",
    ),
    "no_autofill": (
        "Без автодополнения",
        "Пул строго из грейдов вакансии, даже если кандидатов меньше десяти (как до match-1.1)",
    ),
    "no_verified": ("Без индекса профиля", "Вес индекса подтверждённого профиля обнулён"),
    "no_fsp": ("Без ФСП", "Индекс профиля пересчитан без фактора достижений ФСП"),
    "no_semantic": ("Без текстовой близости", "Вес TF-IDF близости описаний обнулён"),
    "no_conditions": ("Без условий", "Вес вилки, формата и города обнулён"),
    "skills_only": ("Только навыки", "Ранжирование только по покрытию стека"),
}
METRICS = (
    "precision_at_10",
    "precision_partial_at_10",
    "ndcg_at_10",
    "ndcg_fit_at_10",
    "mrr",
    "recall_at_50",
)


@dataclass(frozen=True, slots=True)
class EvaluationVacancy:
    """Вакансия набора: текст для разбора и экспертная разметка."""

    vacancy_id: str
    text: str
    specialization: str
    grades: tuple[str, ...]
    must: tuple[str, ...]
    nice: tuple[str, ...]
    salary_from: int
    salary_to: int
    gross: bool
    work_formats: tuple[str, ...]
    city: str | None


@dataclass(frozen=True, slots=True)
class NeedFields:
    """Поля потребности для движка подбора — как их сохранил бы работодатель."""

    specialization_id: int
    grade_ids: list[int]
    skills: list[tuple[int, SkillImportance]]
    salary_from: int
    salary_to: int
    salary_gross: bool
    work_formats: list[str]
    city: str | None


@dataclass(frozen=True, slots=True)
class TuningCase:
    """Вакансия для подбора весов: фолд, оценённый пул и разметка."""

    fold: int
    scored: list[ScoredMember]
    grades: dict[str, int]


@dataclass
class Replication:
    """Результат одного прогона популяции."""

    seed: int
    truths: list[CandidateTruth]
    visible: int = 0
    per_vacancy: list[dict[str, Any]] = field(default_factory=list)
    latencies: list[float] = field(default_factory=list)
    cases: list[TuningCase] = field(default_factory=list)


def load_vacancies(path: Path = DATA_PATH) -> list[EvaluationVacancy]:
    """Набор вакансий с разметкой из YAML."""
    with path.open(encoding="utf-8") as stream:
        records: list[dict[str, Any]] = yaml.safe_load(stream)
    return [
        EvaluationVacancy(
            vacancy_id=record["id"],
            text=" ".join(record["text"].split()),
            specialization=record["truth"]["specialization"],
            grades=tuple(record["truth"]["grades"]),
            must=tuple(record["truth"]["must"]),
            nice=tuple(record["truth"]["nice"]),
            salary_from=record["truth"]["salary"][0],
            salary_to=record["truth"]["salary"][1],
            gross=record["truth"]["gross"],
            work_formats=tuple(record["truth"]["work_formats"]),
            city=record["truth"]["city"],
        )
        for record in records
    ]


class Directory:
    """Соответствия кодов, slug и идентификаторов из справочника подбора."""

    def __init__(self, catalog: SkillCatalog) -> None:
        """Собирает словари из каталога движка."""
        self.skill_ids = {skill.slug: skill.id for skill in catalog.skills}
        self.skill_slugs = {skill.id: skill.slug for skill in catalog.skills}
        self.specialization_ids = catalog.specialization_ids
        self.grade_ids = {grade.code: grade.id for grade in catalog.grades}
        self.grade_ranks = {grade.code: grade.rank for grade in catalog.grades}
        self.rank_by_grade_id = {grade.id: grade.rank for grade in catalog.grades}
        self.grade_id_by_rank = {grade.rank: grade.id for grade in catalog.grades}
        self.catalog_grades = [
            CatalogGrade(id=grade.id, code=grade.code, rank=grade.rank) for grade in catalog.grades
        ]

    def truth(self, vacancy: EvaluationVacancy) -> VacancyTruth:
        """Разметка вакансии в форме для правила релевантности."""
        return VacancyTruth(
            vacancy_id=vacancy.vacancy_id,
            specialization=vacancy.specialization,
            grade_ranks=frozenset(self.grade_ranks[code] for code in vacancy.grades),
            must=frozenset(vacancy.must),
            nice=frozenset(vacancy.nice),
            salary_to_gross=to_gross(vacancy.salary_to, vacancy.gross),
            work_formats=frozenset(vacancy.work_formats),
            city=vacancy.city,
        )

    def reviewed_need(self, vacancy: EvaluationVacancy) -> NeedFields:
        """Потребность по разметке — как если бы работодатель выверил каждое поле."""
        return NeedFields(
            specialization_id=self.specialization_ids[vacancy.specialization],
            grade_ids=[self.grade_ids[code] for code in vacancy.grades],
            skills=[(self.skill_ids[slug], SkillImportance.MUST) for slug in vacancy.must]
            + [(self.skill_ids[slug], SkillImportance.NICE) for slug in vacancy.nice],
            salary_from=vacancy.salary_from,
            salary_to=vacancy.salary_to,
            salary_gross=vacancy.gross,
            work_formats=list(vacancy.work_formats),
            city=vacancy.city,
        )

    def parsed_need(
        self, parsed: ParsedNeed, vacancy: EvaluationVacancy
    ) -> tuple[NeedFields, dict[str, Any]]:
        """Потребность из разбора текста и оценка разбора по разметке.

        Специализацию, грейды и вилку интерфейс не даёт сохранить пустыми: если разбор
        их не нашёл, работодатель заполняет их сам. Здесь они берутся из разметки, а
        каждый такой случай записывается в отчёт.
        """
        filled: list[str] = []
        specialization_id = self.specialization_ids.get(parsed.specialization_code or "")
        if specialization_id is None:
            specialization_id = self.specialization_ids[vacancy.specialization]
            filled.append("specialization")
        grade_ids = [self.grade_ids[code] for code in parsed.grade_codes if code in self.grade_ids]
        if not grade_ids:
            grade_ids = [self.grade_ids[code] for code in vacancy.grades]
            filled.append("grades")
        salary_from, salary_to = parsed.salary_from, parsed.salary_to
        if salary_from is None or salary_to is None:
            salary_from = salary_from or vacancy.salary_from
            salary_to = salary_to or vacancy.salary_to
            filled.append("salary")
        skills = [(item.skill_id, SkillImportance(item.importance)) for item in parsed.skills]
        found_must = {
            self.skill_slugs[skill_id] for skill_id, kind in skills if kind is SkillImportance.MUST
        }
        found_all = {self.skill_slugs[skill_id] for skill_id, _ in skills}
        truth_must, truth_all = set(vacancy.must), set(vacancy.must) | set(vacancy.nice)
        quality = {
            "specialization_correct": parsed.specialization_code == vacancy.specialization,
            "grades_exact": set(parsed.grade_codes) == set(vacancy.grades),
            "must_recall": round(len(found_must & truth_must) / len(truth_must), 4),
            "must_precision": (
                round(len(found_must & truth_must) / len(found_must), 4) if found_must else 0.0
            ),
            "skills_recall": round(len(found_all & truth_all) / len(truth_all), 4),
            "salary_exact": (parsed.salary_from, parsed.salary_to)
            == (vacancy.salary_from, vacancy.salary_to),
            "gross_correct": parsed.salary_gross == vacancy.gross,
            "formats_exact": set(parsed.work_formats) == set(vacancy.work_formats),
            "city_correct": (parsed.city or None) == vacancy.city,
            "filled_by_employer": filled,
        }
        return (
            NeedFields(
                specialization_id=specialization_id,
                grade_ids=grade_ids,
                skills=skills,
                salary_from=salary_from,
                salary_to=salary_to,
                salary_gross=parsed.salary_gross if parsed.salary_gross is not None else True,
                work_formats=list(parsed.work_formats),
                city=parsed.city,
            ),
            quality,
        )


def measure(ranking: Sequence[str], grades: Mapping[str, int]) -> dict[str, float]:
    """Метрики одной выдачи.

    Бинарные метрики (P@10, MRR, R@50) считают релевантными только полностью
    подходящих кандидатов (уровень 2 и 3); P@10 с частичным совпадением дан рядом для
    прозрачности. nDCG@10 учитывает соответствие и силу кандидата (0–3), nDCG@10 по
    соответствию — без уровня «силён».
    """
    fit = {key: min(grade, FIT_CEILING) for key, grade in grades.items()}
    return {
        "precision_at_10": precision_at_k(ranking, grades, TOP_K),
        "precision_partial_at_10": precision_at_k(ranking, grades, TOP_K, PARTIAL),
        "ndcg_at_10": ndcg_at_k(ranking, grades, TOP_K),
        "ndcg_fit_at_10": ndcg_at_k(ranking, fit, TOP_K),
        "mrr": reciprocal_rank(ranking, grades),
        "recall_at_50": recall_at_k(ranking, grades, RECALL_K),
    }


def vps_without(score: VerifiedScore, dropped: Iterable[str]) -> float:
    """Индекс профиля 0..1 без части факторов; веса оставшихся нормируются."""
    removed = set(dropped)
    kept = [item for item in score.components if item.key not in removed]
    weight = sum(item.weight for item in kept)
    return sum(item.value * item.weight for item in kept) / weight if weight else 0.0


def rerank(
    scored: Sequence[ScoredMember],
    weights: Mapping[str, float],
    *,
    dropped_vps: Iterable[str] = (),
) -> list[str]:
    """Пересчёт выдачи с другими весами из тех же компонент боевой формулы.

    Компоненты и понижающие множители берутся из результата движка как есть, меняются
    только веса — так абляция показывает вклад фактора, а не другой реализации.
    """
    total = sum(weights.values())
    removed = tuple(dropped_vps)

    def value(item: ScoredMember) -> float:
        """Балл кандидата при изменённых весах."""
        components = dict(item.result.components)
        if removed:
            components["verified"] = vps_without(item.member.score, removed)
        score = sum(weights[key] * components[key] for key in weights) / total
        for _, factor in item.result.penalties:
            score *= factor
        return score

    return [str(item.member.candidate_id) for item in sorted(scored, key=value, reverse=True)]


def without_test(member: PoolMember, claimed_rank: int, claimed_grade_id: int) -> PoolMember:
    """Кандидат так, как его видела бы платформа без теста: только самоописание."""
    facts = replace(
        member.facts,
        skills={key: replace(fact, verified=False) for key, fact in member.facts.skills.items()},
        confirmed=True,
        grade_id=claimed_grade_id,
        grade_rank=claimed_rank,
        test=None,
    )
    score = VerifiedScore(
        total=round(100 * vps_without(member.score, ["test"]), 1),
        components=member.score.components,
        test_percentile=None,
    )
    return replace(member, facts=facts, score=score)


def inflated_claim(candidate_id: str, true_rank: int, max_rank: int) -> int:
    """Заявленный грейд при сильном стимуле завышать: каждый второй ставит себе ступень выше."""
    roll = Random(f"inflate:{candidate_id}").random()
    if roll < INFLATED_OVERCLAIM and true_rank < max_rank:
        return true_rank + 1
    if roll < INFLATED_OVERCLAIM + INFLATED_UNDERCLAIM and true_rank > 1:
        return true_rank - 1
    return true_rank


def self_description(member: PoolMember) -> str:
    """Самоописание для поиска по ключевым словам: о себе, опыт и заявленные навыки."""
    skills = " ".join(fact.name for fact in member.facts.skills.values())
    return f"{member.facts.text} {skills}"


def weight_grid() -> list[dict[str, float]]:
    """Сетка весов формулы соответствия с шагом 0,05 в продуктовых границах; сумма — 1.

    Границы не дают одному фактору забрать всю выдачу: на синтетической разметке без
    них оптимум уходит в крайность (60 % веса на условия), а это свойство разметки,
    а не рынка.
    """
    steps = [round(index * WEIGHT_STEP, 2) for index in range(int(1 / WEIGHT_STEP) + 1)]

    def within(key: str) -> list[float]:
        """Значения веса в его границах."""
        low, high = WEIGHT_BOUNDS[key]
        return [value for value in steps if low <= value <= high]

    grid = []
    low, high = WEIGHT_BOUNDS["conditions"]
    for skills in within("skills"):
        for verified in within("verified"):
            for semantic in within("semantic"):
                conditions = round(1.0 - skills - verified - semantic, 2)
                if low <= conditions <= high:
                    grid.append(
                        {
                            "skills": skills,
                            "verified": verified,
                            "semantic": semantic,
                            "conditions": conditions,
                        }
                    )
    return grid


def tune_weights(cases: Sequence[TuningCase]) -> dict[str, Any]:
    """Подбор весов на размеченных парах с кросс-валидацией по вакансиям.

    В каждом фолде по одной вакансии каждой специализации. Веса подбираются по nDCG@10
    на двух фолдах и проверяются на третьем, которого подбор не видел; среднее по
    фолдам — честная оценка того, что даст подбор весов на новых вакансиях.
    """
    grid = weight_grid()

    def quality(weights: Mapping[str, float], subset: Sequence[TuningCase]) -> dict[str, float]:
        """Средние nDCG@10 и P@10 выдачи с данными весами."""
        values = [measure(rerank(case.scored, weights), case.grades) for case in subset]
        return {
            "ndcg_at_10": mean(value["ndcg_at_10"] for value in values),
            "precision_at_10": mean(value["precision_at_10"] for value in values),
        }

    folds: list[dict[str, Any]] = []
    for fold in range(FOLDS):
        train = [case for case in cases if case.fold != fold]
        test = [case for case in cases if case.fold == fold]
        best = max(grid, key=lambda weights: quality(weights, train)["ndcg_at_10"])
        folds.append(
            {
                "fold": fold,
                "weights": best,
                "tuned": {key: round(value, 4) for key, value in quality(best, test).items()},
                "current": {
                    key: round(value, 4) for key, value in quality(MATCH_WEIGHTS, test).items()
                },
            }
        )
    selected = max(grid, key=lambda weights: quality(weights, cases)["ndcg_at_10"])
    return {
        "objective": "ndcg_at_10",
        "bounds": WEIGHT_BOUNDS,
        "grid_size": len(grid),
        "folds": folds,
        "cv_tuned": {
            metric: round(mean(item["tuned"][metric] for item in folds), 4)
            for metric in ("ndcg_at_10", "precision_at_10")
        },
        "cv_current": {
            metric: round(mean(item["current"][metric] for item in folds), 4)
            for metric in ("ndcg_at_10", "precision_at_10")
        },
        "current_weights": dict(MATCH_WEIGHTS),
        "selected_weights": selected,
    }


class MatchingEvaluation:
    """Прогон набора вакансий через боевой подбор, бейзлайны и абляции."""

    def __init__(self, session: AsyncSession) -> None:
        """Получает сессию базы оценки."""
        self._session = session
        self._engine = MatchingEngine(session)
        self._pool = CandidatePoolService(session)

    async def _context(self, need: NeedFields, vacancy: EvaluationVacancy) -> MatchingContext:
        """Контекст подбора из полей потребности."""
        return await self._engine.build_context(
            specialization_id=need.specialization_id,
            grade_ids=need.grade_ids,
            skills=need.skills,
            salary_from=need.salary_from,
            salary_to=need.salary_to,
            salary_gross=need.salary_gross,
            work_formats=need.work_formats,
            city=need.city,
            texts=(vacancy.text,),
        )

    async def _shortlist(
        self,
        need: NeedFields,
        context: MatchingContext,
        *,
        expand: bool = False,
        autofill: bool = True,
    ) -> list[ScoredMember]:
        """Та же последовательность, что в ShortlistService.build: пул, затем балл.

        Без автодополнения пул строго из грейдов потребности — так было до match-1.1.
        """
        if autofill:
            selection = await self._engine.select_pool(
                self._pool, need.specialization_id, need.grade_ids, expand=expand
            )
            return await self._engine.score(context, selection.members)
        grade_ids = await self._engine.grade_filter(need.grade_ids, expand=expand)
        members = await self._pool.load(
            PoolQuery(specialization_ids=[need.specialization_id], grade_ids=grade_ids)
        )
        return await self._engine.score(context, members)

    async def run(
        self, replication: Replication, vacancies: Sequence[EvaluationVacancy]
    ) -> Replication:
        """Считает выдачи всех систем по всем вакансиям одного прогона популяции."""
        catalog = await self._engine.catalog()
        directory = Directory(catalog)
        truth_by_id = {truth.candidate_id: truth for truth in replication.truths}
        visible = [
            member
            for member in await self._pool.load(PoolQuery())
            if member.candidate_id in truth_by_id
        ]
        replication.visible = len(visible)
        keyword = Bm25Index(
            {str(member.candidate_id): self_description(member) for member in visible},
            catalog.synonyms,
        )
        max_rank = max(directory.rank_by_grade_id.values())
        for index, vacancy in enumerate(vacancies):
            truth = directory.truth(vacancy)
            grades = {
                str(member.candidate_id): relevance(truth, truth_by_id[member.candidate_id])
                for member in visible
            }
            parsed = parse_need_text(vacancy.text, catalog.skills, directory.catalog_grades)
            need, quality = directory.parsed_need(parsed, vacancy)
            context = await self._context(need, vacancy)
            started = time.perf_counter()
            scored = await self._shortlist(need, context)
            replication.latencies.append((time.perf_counter() - started) * 1000)
            reviewed = directory.reviewed_need(vacancy)
            reviewed_scored = await self._shortlist(
                reviewed, await self._context(reviewed, vacancy)
            )
            need_ranks = {directory.rank_by_grade_id[grade_id] for grade_id in need.grade_ids}
            expanded = await self._shortlist(need, context, expand=True)
            exact_only = await self._shortlist(need, context, autofill=False)
            same_specialization = [
                member
                for member in visible
                if member.row.claimed_specialization_id == need.specialization_id
            ]
            claimed = [
                member
                for member in same_specialization
                if directory.rank_by_grade_id.get(member.row.claimed_grade_id or 0) in need_ranks
            ]
            untested = await self._engine.score(
                context,
                [
                    without_test(
                        member,
                        directory.rank_by_grade_id[member.row.claimed_grade_id or 0],
                        member.row.claimed_grade_id or 0,
                    )
                    for member in claimed
                ],
            )
            inflated = []
            for member in same_specialization:
                claim = inflated_claim(
                    str(member.candidate_id), truth_by_id[member.candidate_id].grade_rank, max_rank
                )
                if claim in need_ranks:
                    inflated.append(without_test(member, claim, directory.grade_id_by_rank[claim]))
            untested_inflated = await self._engine.score(context, inflated)
            replication.cases.append(TuningCase(fold=index % FOLDS, scored=scored, grades=grades))
            no_weight = dict.fromkeys(MATCH_WEIGHTS, 0.0)
            rankings = {
                "scout": [str(item.member.candidate_id) for item in scored],
                "scout_reviewed": [str(item.member.candidate_id) for item in reviewed_scored],
                "scout_expanded": [str(item.member.candidate_id) for item in expanded],
                "keyword": keyword.rank(vacancy.text),
                "keyword_filters": keyword.rank(
                    vacancy.text, [str(member.candidate_id) for member in claimed]
                ),
                "no_test": [str(item.member.candidate_id) for item in untested],
                "no_test_inflated": [str(item.member.candidate_id) for item in untested_inflated],
                "no_autofill": [str(item.member.candidate_id) for item in exact_only],
                "no_verified": rerank(scored, {**MATCH_WEIGHTS, "verified": 0.0}),
                "no_fsp": rerank(scored, MATCH_WEIGHTS, dropped_vps=["fsp"]),
                "no_semantic": rerank(scored, {**MATCH_WEIGHTS, "semantic": 0.0}),
                "no_conditions": rerank(scored, {**MATCH_WEIGHTS, "conditions": 0.0}),
                "skills_only": rerank(scored, {**no_weight, "skills": 1.0}),
            }
            replication.per_vacancy.append(
                {
                    "id": vacancy.vacancy_id,
                    "relevant": sum(1 for grade in grades.values() if grade >= 2),
                    "partially_relevant": sum(1 for grade in grades.values() if grade == 1),
                    "strong": sum(1 for grade in grades.values() if grade == 3),
                    "pool_after_filters": len(scored),
                    "ideal_precision_at_10": ideal_precision_at_k(grades, TOP_K),
                    "parsing": quality,
                    "metrics": {
                        name: measure(ranking, grades) for name, ranking in rankings.items()
                    },
                }
            )
        return replication


def aggregate(replications: Sequence[Replication]) -> dict[str, Any]:
    """Сводный отчёт по всем прогонам популяции.

    Метрика вакансии усредняется по прогонам, затем по вакансиям; интервал —
    бутстреп по вакансиям. Разброс между прогонами показывает, насколько цифры
    зависят от случайности самой популяции и тестов.
    """
    count = len(replications[0].per_vacancy)

    def vacancy_means(name: str, metric: str) -> list[float]:
        """Метрика системы по каждой вакансии, усреднённая по прогонам."""
        return [
            mean(run.per_vacancy[index]["metrics"][name][metric] for run in replications)
            for index in range(count)
        ]

    def block(names: Mapping[str, tuple[str, str]], *, paired: bool = False) -> dict[str, Any]:
        """Средние метрики группы систем с интервалами и разбросом между прогонами.

        Для абляций дополнительно считается парная разница со «Скаутом» по тем же
        вакансиям и популяциям: разброс между прогонами у обеих систем общий и в
        разнице сокращается, поэтому её интервал заметно уже интервалов самих метрик.
        """
        result = {}
        for name, (title, description) in names.items():
            entry: dict[str, Any] = {"title": title, "description": description}
            for metric in METRICS:
                values = vacancy_means(name, metric)
                per_run = [
                    mean(item["metrics"][name][metric] for item in run.per_vacancy)
                    for run in replications
                ]
                entry[metric] = {
                    "mean": round(mean(values), 4),
                    "ci95": list(bootstrap_interval(values)),
                    "replication_sd": round(pstdev(per_run), 4),
                }
                if paired:
                    differences = [
                        value - reference
                        for value, reference in zip(
                            values, vacancy_means("scout", metric), strict=True
                        )
                    ]
                    entry[metric]["delta_vs_scout"] = round(mean(differences), 4)
                    entry[metric]["delta_ci95"] = list(bootstrap_interval(differences))
            result[name] = entry
        return result

    systems = block(SYSTEMS)

    def gain(baseline: str, metric: str) -> float:
        """Относительный прирост «Скаута» к бейзлайну."""
        base = systems[baseline][metric]["mean"]
        return round((systems["scout"][metric]["mean"] - base) / base, 4) if base else 0.0

    parsing = [item["parsing"] for item in replications[0].per_vacancy]
    latencies = sorted(value for run in replications for value in run.latencies)

    def share(key: str) -> float:
        """Доля вакансий, где поле разобрано верно."""
        return round(mean(1.0 if item[key] else 0.0 for item in parsing), 4)

    def per_vacancy(index: int) -> dict[str, Any]:
        """Сводка одной вакансии по всем прогонам."""
        first = replications[0].per_vacancy[index]
        return {
            "id": first["id"],
            "relevant": round(mean(run.per_vacancy[index]["relevant"] for run in replications), 1),
            "pool_after_filters": round(
                mean(run.per_vacancy[index]["pool_after_filters"] for run in replications), 1
            ),
            "metrics": {
                name: {
                    metric: round(
                        mean(
                            run.per_vacancy[index]["metrics"][name][metric] for run in replications
                        ),
                        4,
                    )
                    for metric in ("precision_at_10", "ndcg_at_10")
                }
                for name in ("scout", "keyword", "keyword_filters")
            },
        }

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "vacancies": count,
        "replications": len(replications),
        "population": describe(list(replications[0].truths), [run.seed for run in replications]),
        "visible_candidates_per_replication": [run.visible for run in replications],
        "top_k": TOP_K,
        "recall_k": RECALL_K,
        "relevance_rule": relevance.__doc__,
        "mean_ideal_precision_at_10": round(
            mean(item["ideal_precision_at_10"] for run in replications for item in run.per_vacancy),
            4,
        ),
        "systems": systems,
        "ablations": block(ABLATIONS, paired=True),
        "gain_vs_keyword": {metric: gain("keyword", metric) for metric in METRICS},
        "gain_vs_keyword_filters": {metric: gain("keyword_filters", metric) for metric in METRICS},
        "parsing": {
            "specialization_accuracy": share("specialization_correct"),
            "grades_exact": share("grades_exact"),
            "must_recall": round(mean(item["must_recall"] for item in parsing), 4),
            "must_precision": round(mean(item["must_precision"] for item in parsing), 4),
            "skills_recall": round(mean(item["skills_recall"] for item in parsing), 4),
            "salary_exact": share("salary_exact"),
            "gross_correct": share("gross_correct"),
            "formats_exact": share("formats_exact"),
            "city_correct": share("city_correct"),
            "vacancies_needing_manual_fields": sum(
                1 for item in parsing if item["filled_by_employer"]
            ),
        },
        "shortlist_latency_ms": {
            "mean": round(mean(latencies), 1),
            "p95": round(latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))], 1),
        },
        "weight_tuning": tune_weights([case for run in replications for case in run.cases]),
        "per_vacancy": [per_vacancy(index) for index in range(count)],
    }


async def evaluate(per_specialization: int, replications: int) -> dict[str, Any]:
    """Полный прогон: на каждый повтор — чистая база, справочники, популяция и подбор."""
    settings = get_settings()
    database.ensure_evaluation_database(settings.database_url)
    vacancies = load_vacancies()
    runs = []
    for number in range(replications):
        seed = EVALUATION_SEED + number
        await database.recreate_database(settings.database_url)
        await asyncio.to_thread(database.migrate)
        await database.seed_dictionaries(settings.database_url)
        engine = create_async_engine(settings.database_url, pool_size=8)
        factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        started = time.perf_counter()
        truths = await generate_population(factory, settings, per_specialization, seed)
        print(
            f"Прогон {number + 1}/{replications}: {len(truths)} кандидатов "
            f"за {time.perf_counter() - started:.0f} с"
        )
        async with factory() as session:
            runs.append(
                await MatchingEvaluation(session).run(
                    Replication(seed=seed, truths=truths), vacancies
                )
            )
        await engine.dispose()
    return aggregate(runs)


def main() -> None:
    """Запуск из командной строки: отчёт сохраняется в docs/validation."""
    parser = argparse.ArgumentParser(description="Оценка качества подбора на размеченных парах")
    parser.add_argument("--per-specialization", type=int, default=DEFAULT_PER_SPECIALIZATION)
    parser.add_argument("--replications", type=int, default=DEFAULT_REPLICATIONS)
    parser.add_argument("--output", type=Path, default=REPORT_PATH)
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.per_specialization, args.replications))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    for name, values in {**report["systems"], **report["ablations"]}.items():
        print(
            f"{values['title']:<38} P@10 {values['precision_at_10']['mean']:.3f} "
            f"(частично {values['precision_partial_at_10']['mean']:.3f})  "
            f"nDCG@10 {values['ndcg_at_10']['mean']:.3f}  MRR {values['mrr']['mean']:.3f}  "
            f"R@50 {values['recall_at_50']['mean']:.3f}  ({name})"
        )
    tuning = report["weight_tuning"]
    current, tuned = tuning["cv_current"], tuning["cv_tuned"]
    print(
        f"Подбор весов, кросс-валидация: nDCG@10 {current['ndcg_at_10']:.3f} → "
        f"{tuned['ndcg_at_10']:.3f}; P@10 {current['precision_at_10']:.3f} → "
        f"{tuned['precision_at_10']:.3f}; веса {tuning['selected_weights']}"
    )
    print(f"Отчёт: {args.output}")


if __name__ == "__main__":
    main()
