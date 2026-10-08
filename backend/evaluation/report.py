import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.assessment.item_generators import REGISTRY

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VALIDATION_DIR = REPOSITORY_ROOT / "docs" / "validation"
REPORT_PATH = REPOSITORY_ROOT / "docs" / "VALIDATION.md"
MATCHING_REPORT = "matching_evaluation.json"
MATCHING_BASELINE = "matching_evaluation_match-1.0.json"
ASSESSMENT_REPORT = "assessment_validation.json"
SIMULATION_REPORT = "assessment_simulation.json"

METRIC_TITLES = {
    "precision_at_10": "P@10 строго",
    "precision_partial_at_10": "P@10 частично",
    "ndcg_at_10": "nDCG@10",
    "ndcg_fit_at_10": "nDCG@10 без силы",
    "mrr": "MRR",
    "recall_at_50": "R@50",
}
SPECIALIZATION_TITLES = {
    "backend": "Backend",
    "frontend": "Frontend",
    "data_analytics": "Аналитика данных",
    "ml": "ML",
    "qa": "QA",
    "devops": "DevOps",
    "mobile": "Mobile",
}
GRADE_TITLES = {"intern": "Intern", "junior": "Junior", "middle": "Middle", "senior": "Senior"}
HEADLINE_SYSTEMS = ("scout", "keyword", "keyword_filters")


def number(value: float | None, digits: int = 3) -> str:
    """Число с десятичной запятой, как в остальной документации."""
    if value is None:
        return "—"
    return f"{value:.{digits}f}".replace(".", ",").replace("-", "−")


def plural(count: int, one: str, few: str, many: str) -> str:
    """Существительное после числа: 1 вакансия, 3 вакансии, 21 вакансия, 25 вакансий."""
    tail = count % 100
    if 11 <= tail <= 14:
        return many
    if count % 10 == 1:
        return one
    if 2 <= count % 10 <= 4:
        return few
    return many


def percent_range(values: Sequence[float]) -> str:
    """Диапазон долей: «62–67 %»."""
    low, high = min(values) * 100, max(values) * 100
    if round(low) == round(high):
        return f"{low:.0f}\u00a0%"
    return f"{low:.0f}–{high:.0f}\u00a0%"


def sentence_tail(text: str) -> str:
    """Описание после тире — со строчной буквы, если это не аббревиатура."""
    if len(text) > 1 and text[1].islower():
        return text[0].lower() + text[1:]
    return text


def percent(value: float | None, digits: int = 0) -> str:
    """Доля в процентах с неразрывным пробелом перед знаком."""
    if value is None:
        return "—"
    return f"{value * 100:.{digits}f}".replace(".", ",") + " %"


def signed(value: float, digits: int = 2) -> str:
    """Смещение со знаком: минус — занижение, плюс — завышение."""
    text = number(abs(value), digits)
    return f"−{text}" if value < 0 else f"+{text}"


def table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    """Таблица Markdown: первая колонка выровнена влево, остальные — вправо."""
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join([":---"] + ["---:"] * (len(header) - 1)) + "|")
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def load(name: str) -> Any:
    """Читает JSON-отчёт; без него раздел не собрать — подсказываем команду."""
    path = VALIDATION_DIR / name
    if not path.exists():
        raise SystemExit(f"Нет отчёта {path}. Запустите `make eval-matching validate-assessment`.")
    return json.loads(path.read_text(encoding="utf-8"))


def metric_cell(entry: Mapping[str, Any]) -> str:
    """Среднее по вакансиям и 95-процентный бутстреп-интервал."""
    low, high = entry["ci95"]
    return f"{number(entry['mean'])} [{number(low, 2)}–{number(high, 2)}]"


def systems_table(groups: Mapping[str, Mapping[str, Any]], metrics: Sequence[str]) -> list[str]:
    """Сравнение систем или абляций по выбранным метрикам."""
    rows = [
        [group["title"], *(metric_cell(group[metric]) for metric in metrics)]
        for group in groups.values()
    ]
    return table(["Система", *(METRIC_TITLES[metric] for metric in metrics)], rows)


def headline(
    matching: Mapping[str, Any],
    simulation: Sequence[Mapping[str, Any]],
    assessment: Mapping[str, Any],
) -> list[str]:
    """Главные цифры в начале документа — то, что спросят на защите."""
    scenario = assessment["person_fit"]["scenario"]
    leak = next(
        item
        for item in assessment["leaks"]["pooled"]
        if item["budget"] == scenario["budget"]
        and item["template_advantage"] == scenario["template_advantage"]
    )
    honest = assessment["leaks"]["honest"]
    systems = matching["systems"]
    scout, keyword, filtered = (systems[key] for key in HEADLINE_SYSTEMS)
    full = [row for row in simulation if row["mode"] == "full"]
    kappa = [row["retest_grade_kappa_weighted"] for row in full]
    exact = [row["grade_exact"] for row in full]
    within = [row["grade_within_one"] for row in full]
    return [
        "## Коротко",
        "",
        f"- **Подбор.** nDCG@10 «Скаута» — {number(scout['ndcg_at_10']['mean'])} против "
        f"{number(keyword['ndcg_at_10']['mean'])} у поиска по ключевым словам (BM25) и "
        f"{number(filtered['ndcg_at_10']['mean'])} у BM25 с фильтрами самоописания; MRR — "
        f"{number(scout['mrr']['mean'])} против {number(keyword['mrr']['mean'])} и "
        f"{number(filtered['mrr']['mean'])}.",
        f"- **Тест.** При повторном прохождении грейд совпадает со взвешенной каппой "
        f"{number(min(kappa), 2)}–{number(max(kappa), 2)}, точный грейд — "
        f"{percent_range(exact)}, ±1 ступень — {percent_range(within)}.",
        f"- **Утечки.** Если в сеть утекли {leak['budget']} самых частых "
        f"{plural(leak['budget'], 'задание', 'задания', 'заданий')}, фиксированный тест "
        f"завышает грейд {percent(leak['fixed_test_inflation'])} кандидатов, адаптивный тест "
        f"с уникальными экземплярами — {percent(leak['scout_cat_inflation'])} (при честном "
        f"прохождении — {percent(honest['fixed_test'])} и {percent(honest['scout_cat'])}).",
        "- **По итогам проверки изменили продукт:** итоговая оценка теста — WLE вместо EAP, "
        "веса балла соответствия — `match-1.1`, подборка добирает соседние грейды, если "
        "точного грейда меньше десяти кандидатов.",
        "",
    ]


def matching_setup(matching: Mapping[str, Any]) -> list[str]:
    """Постановка эксперимента: данные, шум самоописания, разметка, метрики."""
    population = matching["population"]
    noise = population["noise"]
    visible = matching["visible_candidates_per_replication"]
    return [
        "## 1. Подбор",
        "",
        "### 1.1 Постановка",
        "",
        f"- **Вакансии.** {matching['vacancies']} "
        f"{plural(matching['vacancies'], 'текст', 'текста', 'текстов')} (по три на каждую из семи "
        "специализаций), у каждой — экспертная разметка: специализация, грейды, обязательные "
        "и желательные навыки, вилка, формат, город "
        "(`backend/evaluation/data/matching_vacancies.yaml`).",
        f"- **Кандидаты.** {population['candidates']} синтетических людей на прогон, "
        f"{matching['replications']} независимых "
        f"{plural(matching['replications'], 'прогон', 'прогона', 'прогонов')} (зёрна "
        f"{', '.join(str(seed) for seed in population['seeds'])}). Каждый создаётся настоящими "
        "сервисами платформы: анкета, согласия, опрос, адаптивный тест, привязка ФСП. В банке "
        f"видно {min(visible)}–{max(visible)} человек — остальные скрыты или не ищут работу.",
        "- **Скрытая истина.** У кандидата есть истинные θ, грейд, навыки, ожидания и формат. "
        "Подбор видит только то, что увидел бы на платформе: анкету и результат теста.",
        "- **Шум самоописания:** "
        f"забыт настоящий навык — {percent(noise['omitted_true_skill_rate'])}; "
        f"раздутый список навыков — {percent(noise['inflated_skill_list_share'])}; "
        f"грейд завышен — {percent(noise['overclaimed_grade_share'])}, "
        f"занижен — {percent(noise['underclaimed_grade_share'])}; "
        f"тест прошли {percent(noise['tested_share'])}, "
        f"ФСП привязали {percent(noise['fsp_linked_share'])}.",
        "- **Разметка релевантности** считается по истинным атрибутам до прогона и под "
        "результаты не подстраивалась:",
        "",
        "  | Уровень | Условие |",
        "  |:---|:---|",
        "  | 3 | Подходит полностью, и истинная способность в верхней половине грейда |",
        "  | 2 | Истинный грейд из вакансии, все обязательные навыки, ожидания ≤ вилки + 10 % |",
        "  | 1 | Соседний грейд или ≥ половины обязательных навыков, ожидания ≤ вилки + 30 % |",
        "  | 0 | Иначе, а также другая специализация или несовместимый формат |",
        "",
        "- **Метрики.** P@10 строго — доля пар уровня ≥ 2 в первой десятке (потолок "
        f"{number(matching['mean_ideal_precision_at_10'])}: для части вакансий подходящих "
        "меньше десяти). P@10 частично — уровень ≥ 1. nDCG@10 — по уровням 0–3, "
        "nDCG@10 без силы — уровни 2 и 3 не различаются. MRR — 1 / позиция первого "
        "подходящего. R@50 — доля всех подходящих в первых пятидесяти.",
        "- В квадратных скобках — 95-процентный бутстреп-интервал по вакансиям.",
        "",
    ]


def delta_cell(entry: Mapping[str, Any]) -> str:
    """Парная разница с «Скаутом» и её интервал."""
    low, high = entry["delta_ci95"]
    return f"{signed(entry['delta_vs_scout'], 3)} [{signed(low, 2)}…{signed(high, 2)}]"


def ablation_table(groups: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Абляции: значение метрики и парная разница со «Скаутом»."""
    rows = [
        [
            group["title"],
            number(group["ndcg_at_10"]["mean"]),
            delta_cell(group["ndcg_at_10"]),
            number(group["precision_at_10"]["mean"]),
            delta_cell(group["precision_at_10"]),
            number(group["mrr"]["mean"]),
        ]
        for group in groups.values()
    ]
    return table(["Вариант", "nDCG@10", "Δ nDCG@10", "P@10 строго", "Δ P@10", "MRR"], rows)


def quoted(titles: Sequence[str]) -> str:
    """Перечисление названий в кавычках-ёлочках или «нет»."""
    return ", ".join(f"«{title}»" for title in titles) if titles else "нет"


def matching_results(matching: Mapping[str, Any]) -> list[str]:
    """Сравнение с бейзлайнами и абляции."""
    main_metrics = ["precision_at_10", "precision_partial_at_10", "ndcg_at_10", "mrr"]
    lines = [
        "### 1.2 Сравнение с поиском по ключевым словам",
        "",
        *systems_table(matching["systems"], main_metrics),
        "",
    ]
    lines += [
        f"- **{group['title']}** — {sentence_tail(group['description'])}."
        for group in matching["systems"].values()
    ]
    recall = {key: group["recall_at_50"]["mean"] for key, group in matching["systems"].items()}
    lines += [
        "",
        f"R@50: «Скаут» {number(recall['scout'])}, BM25 {number(recall['keyword'])}, "
        f"BM25 с фильтрами {number(recall['keyword_filters'])}. Высокая полнота BM25 — "
        "следствие поиска по всей базе без фильтров: он находит подходящих где-то в "
        "первой полусотне, но ставит наверх тех, кто лучше описал себя, а не тех, кто "
        "подходит. Полноту «Скаута» ограничивает жёсткий фильтр по подтверждённому "
        "грейду: тест ошибается в основном на соседний грейд, и такие люди в подборку "
        "по точному грейду не попадают — отсюда автодополнение (1.5).",
        "",
        "### 1.3 Абляции: что даёт каждый компонент",
        "",
        "Каждая строка — «Скаут» с одним изменением. Δ — парная разница со «Скаутом» на "
        "тех же вакансиях и популяциях, в скобках её 95-процентный интервал.",
        "",
        *ablation_table(matching["ablations"]),
        "",
    ]
    lines += [
        f"- **{group['title']}** — {sentence_tail(group['description'])}."
        for group in matching["ablations"].values()
    ]
    harmful = [
        group["title"]
        for group in matching["ablations"].values()
        if group["ndcg_at_10"]["delta_ci95"][1] < 0
    ]
    neutral = [
        group["title"]
        for group in matching["ablations"].values()
        if group["ndcg_at_10"]["delta_ci95"][0] <= 0 <= group["ndcg_at_10"]["delta_ci95"][1]
    ]
    helpful = [
        group["title"]
        for group in matching["ablations"].values()
        if group["ndcg_at_10"]["delta_ci95"][0] > 0
    ]
    lines += [
        "",
        f"По nDCG@10 значимо хуже «Скаута»: {quoted(harmful)}. В пределах шума: "
        f"{quoted(neutral)}. Значимо лучше: {quoted(helpful)}.",
        "",
        "Как читать. «Без теста» на честном самоописании выглядит почти как «Скаут»: в "
        "синтетике люди завышают грейд умеренно, а заявленный грейд не страдает от ошибки "
        "измерения. Но как только грейд решает попадание в выдачу, появляется стимул "
        "завышать, и строка «Без теста, грейд завышает половина» показывает, что тогда "
        "происходит. Тест защищает подбор от этого стимула, а не улучшает его в мире, где "
        "все честны.",
        "",
        "Индекс подтверждённого профиля, ФСП и текстовая близость на синтетике заметного "
        "вклада не дают, и мы это не скрываем. Индекс профиля оставлен, потому что "
        "реализует требование ТЗ «внутри категории выше те, у кого сильнее подтверждённый "
        "профиль», и это единственный компонент, который нельзя накрутить анкетой. В "
        "синтетике ФСП слабо связан с релевантностью, а тексты анкет шаблонны; на живых "
        "данных оба сигнала нужно перепроверить, веса для этого вынесены в одну константу.",
        "",
    ]
    return lines


def parsing_section(matching: Mapping[str, Any]) -> list[str]:
    """Качество разбора текста вакансии в потребность."""
    parsing = matching["parsing"]
    latency = matching["shortlist_latency_ms"]
    rows = [
        ["Специализация", percent(parsing["specialization_accuracy"])],
        ["Грейды (точно)", percent(parsing["grades_exact"])],
        ["Обязательные навыки: полнота", percent(parsing["must_recall"])],
        ["Обязательные навыки: точность", percent(parsing["must_precision"])],
        ["Все навыки: полнота", percent(parsing["skills_recall"])],
        ["Вилка", percent(parsing["salary_exact"])],
        ["До/после НДФЛ", percent(parsing["gross_correct"])],
        ["Формат работы", percent(parsing["formats_exact"])],
        ["Город", percent(parsing["city_correct"])],
    ]
    return [
        "### 1.4 Разбор текста вакансии",
        "",
        *table(["Поле", "Верно"], rows),
        "",
        f"Вакансий, где работодателю пришлось бы дописывать поля вручную: "
        f"{parsing['vacancies_needing_manual_fields']}. Точность обязательных навыков ниже "
        "полноты: разбор относит к обязательным часть навыков из «будет плюсом», если они "
        "стоят в общем списке требований. Строка «потребность выверена» в 1.2 показывает, "
        "что на ранжирование это почти не влияет.",
        "",
        f"Подборка на базе этого размера строится в среднем за {number(latency['mean'], 0)} мс "
        f"(95-й перцентиль — {number(latency['p95'], 0)} мс).",
        "",
    ]


def weights_section(matching: Mapping[str, Any], baseline: Mapping[str, Any] | None) -> list[str]:
    """Подбор весов на кросс-валидации и решения, принятые по оценке."""
    tuning = matching["weight_tuning"]
    lines = [
        "### 1.5 Что изменили по итогам",
        "",
        "**Веса балла соответствия (`match-1.1`).** Веса подбирались перебором по сетке с "
        f"шагом 0,05 в ограниченных диапазонах ({tuning['grid_size']} вариантов) на "
        "кросс-валидации: три фолда, в каждом по одной вакансии каждой специализации, веса "
        "выбираются на двух фолдах и проверяются на третьем. Без ограничений оптимум "
        "вырождался в «почти только условия» — такой балл не объясним работодателю, "
        "поэтому сетка ограничена.",
        "",
    ]
    if baseline is not None:
        old = baseline["weight_tuning"]
        rows = [
            [
                str(fold["fold"] + 1),
                ", ".join(f"{key} {number(value, 2)}" for key, value in fold["weights"].items()),
                number(fold["current"]["ndcg_at_10"]),
                number(fold["tuned"]["ndcg_at_10"]),
            ]
            for fold in old["folds"]
        ]
        lines += [
            "Прогон на весах `match-1.0` "
            f"({', '.join(f'{k} {number(v, 2)}' for k, v in old['current_weights'].items())}):",
            "",
            *table(["Фолд", "Веса, выбранные на остальных", "nDCG@10 было", "стало"], rows),
            "",
            f"Подобранные веса лучше прежних во всех трёх фолдах; среднее nDCG@10 на "
            f"отложенных вакансиях — {number(old['cv_current']['ndcg_at_10'])} → "
            f"{number(old['cv_tuned']['ndcg_at_10'])}. Приняты веса "
            f"{', '.join(f'{k} {number(v, 2)}' for k, v in old['selected_weights'].items())}"
            " — медиана выбора по фолдам.",
            "",
        ]
    lines += [
        f"Текущий прогон на `match-1.1`: на отложенных вакансиях nDCG@10 "
        f"{number(tuning['cv_current']['ndcg_at_10'])}, перебор поверх даёт "
        f"{number(tuning['cv_tuned']['ndcg_at_10'])}. "
        + (
            "Дальнейшая подгонка весов под 21 вакансию ухудшает результат на отложенных "
            "вакансиях — это была бы подгонка под шум."
            if tuning["cv_tuned"]["ndcg_at_10"] <= tuning["cv_current"]["ndcg_at_10"]
            else "Прирост меньше разброса между прогонами, веса не меняем."
        ),
        "",
        "**Автодополнение соседними грейдами.** Тест ошибается в основном на соседний "
        "грейд, поэтому часть подходящих людей оказывается рядом с запрошенным. Если "
        "точного грейда меньше десяти кандидатов, подборка добирает соседние с множителем "
        "0,85 и пометкой в интерфейсе; при достаточном пуле выдача не меняется.",
        "",
    ]
    if baseline is not None:
        before = baseline["systems"]["scout"]
        after = matching["systems"]["scout"]
        rows = [
            [METRIC_TITLES[metric], number(before[metric]["mean"]), number(after[metric]["mean"])]
            for metric in METRIC_TITLES
        ]
        lines += [
            "«Скаут» до и после изменений (те же зёрна популяции; тест случаен, поэтому "
            "сами популяции чуть различаются):",
            "",
            *table(["Метрика", "match-1.0, точный грейд", "match-1.1 + автодополнение"], rows),
            "",
        ]
    return lines


def separated(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    """Не пересекаются ли бутстреп-интервалы двух систем по метрике."""
    return bool(first["ci95"][0] > second["ci95"][1] or second["ci95"][0] > first["ci95"][1])


def matching_limits(matching: Mapping[str, Any]) -> list[str]:
    """Ограничения оценки подбора."""
    scout = matching["systems"]["scout"]
    filtered = matching["systems"]["keyword_filters"]
    outside = [
        title for key, title in METRIC_TITLES.items() if separated(scout[key], filtered[key])
    ]
    inside = [
        title
        for key, title in METRIC_TITLES.items()
        if key not in scout or not separated(scout[key], filtered[key])
    ]
    return [
        "### 1.6 Ограничения",
        "",
        "- Данные синтетические: распределение навыков, шум самоописания и связь ФСП с "
        "силой заданы нами. Абсолютные значения метрик зависят от этих допущений; "
        "сравнение систем на одних и тех же данных — нет.",
        f"- {matching['vacancies']} "
        f"{plural(matching['vacancies'], 'вакансия', 'вакансии', 'вакансий')} — мало для "
        "точных оценок, поэтому везде "
        "интервалы. Интервалы «Скаута» и «BM25 с фильтрами» не пересекаются по метрикам: "
        f"{', '.join(outside) or 'нет'}; пересекаются: {', '.join(inside) or 'нет'}.",
        "- Адаптивный тест рандомизирует выбор заданий, поэтому один прогон "
        "невоспроизводим до знака: метрики усреднены по трём популяциям.",
        "- Первый вариант метрик засчитывал в P@10 частичные совпадения и не учитывал "
        "силу кандидата. После первого прогона мы ужесточили P@10 (уровень ≥ 2) и "
        "добавили уровень 3; обе версии оставлены в таблицах (частично / строго, "
        "nDCG@10 / без силы).",
        "",
    ]


def estimator_section(assessment: Mapping[str, Any]) -> list[str]:
    """EAP против WLE: смещение по истинному грейду."""
    rows = []
    for specialization, populations in assessment["estimators"].items():
        graded = populations["graded"]
        eap, wle = graded["eap"], graded["wle"]
        rows.append(
            [
                SPECIALIZATION_TITLES[specialization],
                signed(eap["bias_by_true_grade"]["senior"]),
                signed(wle["bias_by_true_grade"]["senior"]),
                percent(eap["grade_exact"]),
                percent(wle["grade_exact"]),
                number(eap["retest_kappa_weighted"], 2),
                number(wle["retest_kappa_weighted"], 2),
            ]
        )
    return [
        "### 2.2 Итоговая оценка: WLE вместо EAP",
        "",
        "EAP с априорным N(0, 1) стягивает оценку к среднему: сильных занижает, слабых "
        "завышает. Для выбора следующего задания это полезная устойчивость, для решения "
        "о грейде — систематическая несправедливость к сильным. Парный эксперимент (одни и "
        "те же ответы, две оценки; популяция с долями грейдов как на рынке):",
        "",
        *table(
            [
                "Специализация",
                "Смещение Senior, EAP",
                "WLE",
                "Точный грейд, EAP",
                "WLE",
                "κw, EAP",
                "WLE",
            ],
            rows,
        ),
        "",
        "Итог: по ходу теста θ оценивается EAP (выбор заданий и остановка), итоговое "
        "решение о грейде — по WLE (взвешенное правдоподобие Уорма).",
        "",
    ]


def retest_section(simulation: Sequence[Mapping[str, Any]]) -> list[str]:
    """Повторное прохождение на синтетической популяции: полный и экспресс-режим."""
    lines = [
        "## 2. Тест",
        "",
        "### 2.1 Повторное прохождение (test-retest)",
        "",
        "Каждый синтетический кандидат проходит два независимых адаптивных теста. "
        "Параметры заданий в тесте берутся с шумом (b ± 0,3, ln a ± 0,15), как после "
        "калибровки на реальных ответах. κ — каппа Коэна, κw — квадратично взвешенная "
        "каппа: для порядковой шкалы грейдов она штрафует расхождение на соседний грейд "
        "слабее, чем через грейд.",
        "",
    ]
    for mode, title in (("full", "Полный тест"), ("express", "Экспресс-режим")):
        rows = [
            [
                SPECIALIZATION_TITLES[row["specialization"]],
                str(row["bank_size"]),
                number(row["theta_correlation"], 2),
                percent(row["decision_accuracy"]),
                percent(row["grade_exact"]),
                percent(row["grade_within_one"], 1),
                number(row["retest_grade_kappa"], 2),
                number(row["retest_grade_kappa_weighted"], 2),
                number(row["mean_items"], 1),
                percent(row["max_exposure_rate"]),
            ]
            for row in simulation
            if row["mode"] == mode
        ]
        lines += [
            f"**{title}**",
            "",
            *table(
                [
                    "Специализация",
                    "Семейств",
                    "r(θ, θ̂)",
                    "Решение верно",
                    "Грейд точно",
                    "±1",
                    "κ",
                    "κw",
                    "Заданий",
                    "Макс. показ",
                ],
                rows,
            ),
            "",
        ]
    lines += [
        "«Решение верно» — подтверждён ли заявленный грейд так же, как по истинной θ. "
        "«Макс. показ» — доля сессий, в которых встречалось самое популярное семейство: "
        "в маленьких банках (QA, DevOps, Mobile) отдельные семейства выпадают почти "
        "каждому, поэтому там утечка опаснее, а банк надо расширять в первую очередь.",
        "",
    ]
    return lines


def discrimination_section(assessment: Mapping[str, Any]) -> list[str]:
    """Разделяющая сила заданий и теста в целом."""
    rows = []
    weakest: list[str] = []
    nominal: set[str] = set()
    for specialization, report in assessment["discrimination"].items():
        cuts = report["auc_by_cut"]
        rows.append(
            [
                SPECIALIZATION_TITLES[specialization],
                str(report["bank_size"]),
                number(report["a_median"], 2),
                number(report["point_biserial_median"], 2),
                percent(report["point_biserial_acceptable_share"]),
                " / ".join(number(cuts[code], 2) for code in ("junior", "middle", "senior")),
                number(report["auc_strong_vs_weak"], 3),
            ]
        )
        weakest += [
            f"`{item['family']}` ({number(item['r_pb'], 2)}, "
            f"{GRADE_TITLES.get(REGISTRY[item['family']].nominal_grade, '—')})"
            if item["family"] in REGISTRY
            else f"`{item['family']}` ({number(item['r_pb'], 2)})"
            for item in report["weakest_families"]
            if item["r_pb"] < 0.2
        ]
        nominal |= {
            REGISTRY[item["family"]].nominal_grade
            for item in report["weakest_families"]
            if item["r_pb"] < 0.2 and item["family"] in REGISTRY
        }
    lines = [
        "### 2.3 Разделяющая сила",
        "",
        *table(
            [
                "Специализация",
                "Семейств",
                "Медиана a",
                "Медиана r_pb",
                "r_pb ≥ 0,2",
                "AUC по порогам Junior / Middle / Senior",
                "AUC сильные vs слабые",
            ],
            rows,
        ),
        "",
        "- a — дискриминативность 3PL; r_pb — точечно-бисериальная корреляция ответа на "
        "задание с итоговой θ̂; AUC по порогу — вероятность, что кандидат не ниже грейда "
        "оценён выше кандидата ниже грейда; «сильные vs слабые» — верхняя и нижняя трети.",
        "- r_pb в адаптивном тесте занижен: каждое задание видят люди узкого диапазона θ.",
    ]
    if weakest:
        easy = nominal <= {"intern", "junior"}
        lines.append(
            "- Семейства с r_pb < 0,2 — кандидаты на ревизию методистом (в скобках r_pb и "
            "номинальный грейд): "
            + ", ".join(weakest)
            + (
                ". Все они лёгкие: адаптивный тест показывает их в основном слабым "
                "кандидатам, у которых разброс θ мал, поэтому низкий r_pb здесь — скорее "
                "свойство отбора, чем брак задания. Семейство с отрицательным r_pb методист "
                "может перевести в пилот в «Банке заданий»."
                if easy
                else "."
            )
        )
    lines.append("")
    return lines


def leaks_section(assessment: Mapping[str, Any]) -> list[str]:
    """Устойчивость к утечкам и детекторы списывания."""
    leaks = assessment["leaks"]
    fit = assessment["person_fit"]
    rows = [
        [
            "Честное прохождение",
            percent(leaks["honest"]["fixed_test"]),
            percent(leaks["honest"]["scout_cat"]),
        ]
    ]
    rows += [
        [
            f"Утекли {scenario['budget']} "
            f"{plural(scenario['budget'], 'семейство', 'семейства', 'семейств')}, "
            f"β = {number(scenario['template_advantage'], 1)}",
            percent(scenario["fixed_test_inflation"]),
            percent(scenario["scout_cat_inflation"]),
        ]
        for scenario in leaks["pooled"]
    ]
    return [
        "### 2.4 Устойчивость к утечкам",
        "",
        "Сценарий: в сеть утекают самые часто показываемые задания (худший случай). У "
        "фиксированного теста из 16 заданий утекает точный ответ, и слитое задание решено "
        "всегда. У «Скаута» утекает только шаблон семейства — числа и формулировка у "
        "каждого кандидата свои, поэтому знание шаблона даёт преимущество β: "
        "P' = P + β(1 − P). β = 1 — шаблон даёт полный ответ (самый пессимистичный "
        "вариант). В таблице — доля кандидатов, получивших грейд выше истинного:",
        "",
        *table(["Сценарий", "Фиксированный тест", "«Скаут»"], rows),
        "",
        "При честном прохождении завышение около 20 % у обоих — это ошибка измерения на "
        "соседний грейд, она симметрична занижению.",
        "",
        "**Детекторы списывания** (FTT.4: «будет большим плюсом»). Проверили два:",
        "",
        f"- индекс согласованности ответов l_z: при 5 % ложных срабатываний находит "
        f"{percent(fit['recall_cat_cheaters'])} списывающих в адаптивном тесте "
        f"(AUC {number(fit['auc_cat'], 2)}) и {percent(fit['recall_fixed_cheaters'])} в "
        f"фиксированном (AUC {number(fit['auc_fixed'], 2)});",
        f"- статистика предзнания (решает ли человек популярные задания лучше прогноза по "
        f"остальным): {percent(fit['preknowledge_recall'])} при 5 % ложных, "
        f"AUC {number(fit['preknowledge_auc'], 2)}.",
        "",
        "Оба слишком слабы, чтобы автоматически аннулировать результат: каждый двадцатый "
        "честный кандидат был бы обвинён. В продукт они не встроены; защиту дают "
        "уникальные экземпляры, контроль экспозиции, правила пересдачи и честность "
        "сессии (ASSESSMENT.md, раздел 5). Статистика предзнания — первый кандидат в "
        "сигнал для ручной проверки методистом, когда появятся реальные ответы.",
        "",
    ]


def assessment_limits() -> list[str]:
    """Ограничения валидации теста."""
    return [
        "### 2.5 Ограничения",
        "",
        "- Ответы генерируются той же моделью 3PL, на которой работает тест; реальные "
        "люди отклоняются от модели. Шум параметров частично это имитирует, но "
        "калибровка на реальных ответах (ASSESSMENT.md, раздел 7) обязательна.",
        "- Точный грейд 55–70 % — следствие узких диапазонов θ между порогами; почти все "
        "ошибки — на соседний грейд (±1 ступень ≥ 92 %). Поэтому грейд у нас — решение с "
        "правилами пересдачи, а подборка умеет добирать соседние грейды.",
        "",
    ]


def reproduce() -> list[str]:
    """Команды для воспроизведения всех чисел документа."""
    return [
        "## 3. Как воспроизвести",
        "",
        "```bash",
        "make simulate             # test-retest, ~1 мин",
        "make validate-assessment  # EAP/WLE, разделяющая сила, утечки, ~1,5 мин",
        "make eval-matching        # подбор на отдельной базе fsp_scout_eval, ~5 мин",
        "make validation-report    # этот документ из JSON-отчётов",
        "```",
        "",
        "Оценка подбора пересоздаёт схему базы, поэтому запускается только на базе с "
        "суффиксом `_eval` и не трогает стенд. Исходные отчёты — в `docs/validation/`.",
        "",
    ]


def build() -> str:
    """Собирает документ валидации из JSON-отчётов."""
    matching = load(MATCHING_REPORT)
    assessment = load(ASSESSMENT_REPORT)
    simulation = load(SIMULATION_REPORT)
    baseline_path = VALIDATION_DIR / MATCHING_BASELINE
    baseline = (
        json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else None
    )
    lines = [
        "# Валидация «Скаута» в цифрах",
        "",
        "> Документ собирается командой `make validation-report` из отчётов в "
        "`docs/validation/` — числа в нём не правятся вручную.",
        "",
        *headline(matching, simulation, assessment),
        *matching_setup(matching),
        *matching_results(matching),
        *parsing_section(matching),
        *weights_section(matching, baseline),
        *matching_limits(matching),
        *retest_section(simulation),
        *estimator_section(assessment),
        *discrimination_section(assessment),
        *leaks_section(assessment),
        *assessment_limits(),
        *reproduce(),
    ]
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    """Записывает docs/VALIDATION.md."""
    REPORT_PATH.write_text(build(), encoding="utf-8")
    print(f"Записан {REPORT_PATH.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    main()
