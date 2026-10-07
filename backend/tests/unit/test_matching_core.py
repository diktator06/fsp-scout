import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import InvitationStateError
from app.models.candidate import SkillSource
from app.models.dictionary import SkillKind
from app.models.invitation import InvitationStatus
from app.services.invitations.state_machine import Actor, can_transition, ensure_transition
from app.services.matching.cards import mask_pii
from app.services.matching.category_recommender import (
    CategoryTarget,
    category_targets,
    market_slices,
)
from app.services.matching.explanations import explain_match
from app.services.matching.facts import AssessmentFact, CandidateFacts, NeedFacts, SkillFact
from app.services.matching.match_scoring import (
    ADJACENT_GRADE_FACTOR,
    UNCONFIRMED_FACTOR,
    salary_fit,
    score_match,
    score_skills,
)
from app.services.matching.need_parser import CatalogGrade, CatalogSkill, parse_need_text
from app.services.matching.text_similarity import TfidfIndex, stem, tokenize
from app.services.matching.verified_score import compute_verified_score, peer_percentile

NOW = datetime(2026, 10, 7, tzinfo=UTC)

CATALOG = [
    CatalogSkill(
        1, "python", "Python", SkillKind.LANGUAGE, ("питон", "py"), {"backend": 0.9, "ml": 0.9}
    ),
    CatalogSkill(2, "fastapi", "FastAPI", SkillKind.FRAMEWORK, ("фастапи",), {"backend": 0.65}),
    CatalogSkill(
        3,
        "postgresql",
        "PostgreSQL",
        SkillKind.DATABASE,
        ("постгрес", "postgres"),
        {"backend": 0.8},
    ),
    CatalogSkill(4, "kafka", "Kafka", SkillKind.TOOL, (), {"backend": 0.5}),
    CatalogSkill(5, "react", "React", SkillKind.FRAMEWORK, (), {"frontend": 0.9}),
    CatalogSkill(6, "react-native", "React Native", SkillKind.FRAMEWORK, (), {"mobile": 0.7}),
    CatalogSkill(7, "go", "Go", SkillKind.LANGUAGE, ("golang",), {"backend": 0.7}),
    CatalogSkill(8, "django", "Django", SkillKind.FRAMEWORK, (), {"backend": 0.7}),
    CatalogSkill(9, "communication", "Коммуникация", SkillKind.SOFT, (), {}),
]
GRADES = [
    CatalogGrade(1, "intern", 1),
    CatalogGrade(2, "junior", 2),
    CatalogGrade(3, "middle", 3),
    CatalogGrade(4, "senior", 4),
]


def _need(**overrides: object) -> NeedFacts:
    """Потребность «Python-бэкенд, Middle» с возможностью переопределить поля."""
    values: dict[str, object] = {
        "specialization_id": 1,
        "grade_ranks": frozenset({3}),
        "must": frozenset({1, 2, 3}),
        "nice": frozenset({4}),
        "salary_from": 230_000,
        "salary_to": 320_000,
        "salary_gross": True,
        "work_formats": frozenset({"remote"}),
        "city": "Москва",
        "text": "Платёжный шлюз, эквайринг, биллинг",
    }
    values.update(overrides)
    return NeedFacts(**values)  # type: ignore[arg-type]


def _candidate(**overrides: object) -> CandidateFacts:
    """Подтверждённый Backend Middle со стеком Python + FastAPI + PostgreSQL."""
    facts = CandidateFacts(
        candidate_id=uuid.uuid4(),
        alias="A7F3",
        specialization_id=1,
        grade_id=3,
        grade_rank=3,
        confirmed=True,
        skills={
            1: SkillFact(1, "python", "Python", True, SkillSource.TEST, 4),
            2: SkillFact(2, "fastapi", "FastAPI", False, SkillSource.SURVEY, 4),
            3: SkillFact(3, "postgresql", "PostgreSQL", False, SkillSource.PROFILE, 3),
        },
        test=AssessmentFact(
            uuid.uuid4(), theta=0.9, se=0.35, finished_at=NOW - timedelta(days=30), express=False
        ),
        salary_expectation=260_000,
        salary_gross=True,
        salary_visible=True,
        work_formats=frozenset({"remote"}),
        city="Казань",
        city_visible=True,
        completeness=80,
        email_verified=True,
        text="Платёжные сервисы: эквайринг и биллинг",
    )
    for key, value in overrides.items():
        setattr(facts, key, value)
    return facts


class TestNeedParser:
    """Разбор свободного текста потребности."""

    TEXT = (
        "Python-разработчик (Middle) в команду платежей\n"
        "Требования: Питон, FastAPI, постгрес, опыт от 3 лет.\n"
        "Будет плюсом: Kafka, Docker.\n"
        "Удалённо или гибрид, офис в Москве. Вилка 230–320 тыс. ₽ на руки."
    )

    def test_extracts_structure_with_evidence(self) -> None:
        """Специализация, грейд, навыки по важности, формат, город и вилка с обоснованием."""
        parsed = parse_need_text(self.TEXT, CATALOG, GRADES)
        importance = {item.skill_id: item.importance for item in parsed.skills}
        assert parsed.specialization_code == "backend"
        assert parsed.grade_codes == ["middle"]
        assert parsed.experience_years_min == 3
        assert importance == {1: "must", 2: "must", 3: "must", 4: "nice"}
        assert set(parsed.work_formats) == {"remote", "hybrid"}
        assert parsed.city == "Москва"
        assert (parsed.salary_from, parsed.salary_to, parsed.salary_gross) == (
            230_000,
            320_000,
            False,
        )
        assert parsed.title == "Python-разработчик (Middle) в команду платежей"
        assert "salary" in parsed.evidence and "grades" in parsed.evidence

    def test_grade_from_experience_and_masking_of_overlaps(self) -> None:
        """Грейд выводится из стажа; «React Native» не засчитывается как ещё и React."""
        parsed = parse_need_text(
            "Мобильный разработчик на React Native, опыт от 5 лет", CATALOG, GRADES
        )
        assert [item.skill_id for item in parsed.skills] == [6]
        assert parsed.grade_codes == ["senior"]

    def test_short_names_are_case_sensitive(self) -> None:
        """«Go» — язык, а английское «go» в тексте — нет."""
        assert {
            s.skill_id for s in parse_need_text("Пишем на Go и Postgres", CATALOG, GRADES).skills
        } == {7, 3}
        assert parse_need_text("We go live every week, удалённо", CATALOG, GRADES).skills == []

    def test_nice_marker_scope_inside_sentence(self) -> None:
        """«Желательно» действует от своего места до конца фразы, а не на всю строку."""
        parsed = parse_need_text(
            "Ищем бэкендера уровня мидл в команду лояльности. Нужны питон, FastAPI и постгрес, "
            "желательно Kafka. Удалённо, до 280 тыс. на руки, от 200 тыс.",
            CATALOG,
            GRADES,
        )
        importance = {item.skill_id: item.importance for item in parsed.skills}
        assert importance == {1: "must", 2: "must", 3: "must", 4: "nice"}
        assert parsed.title == "Ищем бэкендера уровня мидл в команду лояльности"
        assert (parsed.salary_from, parsed.salary_to, parsed.salary_gross) == (
            200_000,
            280_000,
            False,
        )
        trailing = parse_need_text(
            "Python и FastAPI обязательны, Kafka будет плюсом.", CATALOG, GRADES
        )
        assert {item.skill_id: item.importance for item in trailing.skills} == {
            1: "must",
            2: "must",
            4: "nice",
        }
        assert (
            parse_need_text("Требования: Python. Желательно Kafka.", CATALOG, GRADES).title is None
        )

    def test_office_location_is_not_a_format_for_hybrid(self) -> None:
        """«Гибрид, офис в Казани» — один формат и город, а не офис плюс гибрид."""
        parsed = parse_need_text("Гибрид, офис в Казани. Python.", CATALOG, GRADES)
        assert parsed.work_formats == ["hybrid"]
        assert parsed.city == "Казань"

    def test_salary_formats(self) -> None:
        """Разные записи вилки сводятся к рублям."""
        cases = {
            "Зарплата от 200 000 до 280 000 ₽": (200_000, 280_000),
            "Вилка 180k–250k gross": (180_000, 250_000),
            "Оклад до 300 тыс.": (None, 300_000),
        }
        for text, expected in cases.items():
            parsed = parse_need_text(text, CATALOG, GRADES)
            assert (parsed.salary_from, parsed.salary_to) == expected, text


class TestTextSimilarity:
    """Офлайновая смысловая близость."""

    def test_stemming_and_synonyms(self) -> None:
        """Формы слова совпадают, алиасы навыков сводятся к одному токену."""
        assert stem("платёжного") == stem("платёжные") == stem("платёжный")
        assert tokenize("Пишу на питоне и Python", {"питоне": "python"}) == [
            "пиш",
            "python",
            "python",
        ]

    def test_related_texts_are_closer(self) -> None:
        """Тексты про платежи ближе друг к другу, чем к тексту про игры."""
        docs = [
            "эквайринг и биллинг платежей",
            "игровой матчмейкинг и лидерборды",
            "платёжный шлюз и эквайринг",
        ]
        index = TfidfIndex(docs)
        assert index.similarity(docs[0], docs[2]) > index.similarity(docs[0], docs[1])
        assert index.similarity("", docs[0]) == 0.0
        assert "эквайринг" in index.shared_terms(docs[2], docs[0])


class TestVerifiedScore:
    """Индекс подтверждённого профиля."""

    def test_percentile_uses_band_when_peers_are_few(self) -> None:
        """Пока коллег мало, перцентиль считается по полосе категории."""
        assert peer_percentile(0.8, [], (0.4, 1.2)) == pytest.approx(0.5)
        assert peer_percentile(1.0, [0.1 * i for i in range(10)], (0.4, 1.2)) == pytest.approx(1.0)

    def test_components_and_decay(self) -> None:
        """Свежий точный тест весит больше старого; без теста индекс ниже."""
        fresh = compute_verified_score(_candidate(), [], (0.4, 1.2), NOW)
        old_test = AssessmentFact(
            uuid.uuid4(), theta=0.9, se=0.35, finished_at=NOW - timedelta(days=730), express=False
        )
        old = compute_verified_score(_candidate(test=old_test), [], (0.4, 1.2), NOW)
        untested = compute_verified_score(
            _candidate(confirmed=False, test=None), [], (0.4, 1.2), NOW
        )
        assert fresh.total > old.total > untested.total
        assert {c.key for c in fresh.components} == {"test", "micro_tasks", "fsp", "profile"}
        assert next(c for c in fresh.components if c.key == "fsp").value == 0.0


class TestMatchScoring:
    """Балл соответствия потребности."""

    def test_skill_credits_and_related(self) -> None:
        """Подтверждённый — 1, заявленный типичный — 0,7, родственный — 0,5 × похожесть."""
        candidate = _candidate(
            skills={
                1: SkillFact(1, "python", "Python", True, SkillSource.TEST, 4),
                8: SkillFact(8, "django", "Django", False, SkillSource.SURVEY, 4),
                3: SkillFact(3, "postgresql", "PostgreSQL", False, SkillSource.SURVEY, 3),
            }
        )
        value, matches = score_skills(_need(), candidate, {1: 0.9, 3: 0.8, 8: 0.7}, {2: {8: 0.6}})
        statuses = {m.skill_id: (m.status, m.credit) for m in matches}
        assert statuses[1] == ("verified", 1.0)
        assert statuses[2] == ("related", 0.3)
        assert statuses[3] == ("declared", 0.7)
        assert statuses[4] == ("missing", 0.0)
        assert value == pytest.approx((2 * 1.0 + 2 * 0.3 + 2 * 0.7) / 7)

    def test_salary_compares_gross_with_net(self) -> None:
        """Ожидания «на руки» переводятся в гросс перед сравнением с вилкой."""
        need = _need(salary_to=300_000)
        assert (
            salary_fit(need, _candidate(salary_expectation=260_000, salary_gross=False)).status
            == "ok"
        )
        assert (
            salary_fit(need, _candidate(salary_expectation=300_000, salary_gross=False)).status
            == "partial"
        )
        assert salary_fit(need, _candidate(salary_expectation=500_000)).status == "mismatch"
        assert salary_fit(need, _candidate(salary_visible=False)).status == "unknown"

    def test_penalties_for_unconfirmed_and_adjacent_grade(self) -> None:
        """Неподтверждённый грейд и соседний грейд опускают кандидата в выдаче."""
        kwargs = {"verified_score": 60.0, "semantic": 0.4, "typical_weights": {}, "relations": {}}
        base = score_match(_need(), _candidate(), **kwargs)
        unconfirmed = score_match(_need(), _candidate(confirmed=False), **kwargs)
        adjacent = score_match(_need(), _candidate(grade_rank=2), **kwargs)
        assert unconfirmed.score == pytest.approx(base.score * UNCONFIRMED_FACTOR, abs=1e-4)
        assert adjacent.score == pytest.approx(base.score * ADJACENT_GRADE_FACTOR, abs=1e-4)
        assert set(base.components) == {"skills", "verified", "semantic", "conditions"}

    def test_explanation_does_not_reveal_hidden_salary(self) -> None:
        """Скрытые ожидания не попадают ни в балл, ни в текст объяснения."""
        candidate = _candidate(salary_visible=False, salary_expectation=999_999)
        result = score_match(
            _need(),
            candidate,
            verified_score=50,
            semantic=0.3,
            typical_weights={1: 0.9},
            relations={},
        )
        score = compute_verified_score(candidate, [], (0.4, 1.2), NOW)
        texts = [
            item.text
            for item in explain_match(
                result,
                candidate,
                score,
                skill_names={1: "Python", 2: "FastAPI", 3: "PostgreSQL", 4: "Kafka"},
                category_title="Backend · Middle",
                grade_name="Middle",
            )
        ]
        assert "Зарплатные ожидания не указаны или скрыты" in texts
        assert not any("999" in text for text in texts)
        assert any(text.startswith("Закрывает 3 из 3 обязательных") for text in texts)


class TestCategoryRecommender:
    """Рекомендованные категории."""

    def test_targets_and_slices(self) -> None:
        """Целевой грейд, соседние и смежная специализация; медиана только при n ≥ 3."""
        targets = category_targets(
            _need(), "backend", [(1, 1), (2, 2), (3, 3), (4, 4)], {"backend": 1, "devops": 6}
        )
        relations = {(t.specialization_id, t.grade_rank): t.relation for t in targets}
        assert relations == {
            (1, 3): "target",
            (1, 2): "adjacent_grade",
            (1, 4): "adjacent_grade",
            (6, 3): "adjacent_specialization",
        }
        pool = [
            (_candidate(salary_expectation=amount), 0.7) for amount in (200_000, 260_000, 400_000)
        ]
        target_slice = market_slices(_need(), [CategoryTarget(1, 3, 3, "target")], pool)[0]
        assert (
            target_slice.candidates,
            target_slice.strong_matches,
            target_slice.median_expectation,
        ) == (3, 3, 260_000)
        assert target_slice.within_budget is True
        small = market_slices(_need(), [CategoryTarget(1, 3, 3, "target")], pool[:2])[0]
        assert small.median_expectation is None


class TestInvitationStateMachine:
    """Автомат статусов приглашения."""

    def test_transitions_by_actor(self) -> None:
        """Каждый переход разрешён только своей стороне."""
        assert can_transition(InvitationStatus.SENT, InvitationStatus.VIEWED, Actor.CANDIDATE)
        assert can_transition(InvitationStatus.VIEWED, InvitationStatus.ACCEPTED, Actor.CANDIDATE)
        assert not can_transition(InvitationStatus.SENT, InvitationStatus.ACCEPTED, Actor.CANDIDATE)
        assert not can_transition(
            InvitationStatus.VIEWED, InvitationStatus.ACCEPTED, Actor.EMPLOYER
        )
        assert not can_transition(
            InvitationStatus.ACCEPTED, InvitationStatus.WITHDRAWN, Actor.EMPLOYER
        )
        with pytest.raises(InvitationStateError, match="уже принято"):
            ensure_transition(InvitationStatus.ACCEPTED, InvitationStatus.DECLINED, Actor.CANDIDATE)


def test_mask_pii_hides_contacts() -> None:
    """Контакты в свободном тексте скрываются, обычный текст остаётся."""
    text = (
        "Пишите ivan@mail.ru или @ivan_dev, звоните +7 (999) 123-45-67, "
        "сайт https://ivan.dev. Стаж 5 лет."
    )
    masked = mask_pii(text)
    assert "ivan@mail.ru" not in masked and "@ivan_dev" not in masked
    assert "123-45-67" not in masked and "ivan.dev" not in masked
    assert "Стаж 5 лет" in masked
