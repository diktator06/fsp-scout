import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence

_TOKEN = re.compile(r"[a-zа-яё][a-zа-яё0-9+#]*|\d+[a-zа-я]+", re.IGNORECASE)

_STOP_WORDS = frozenset(
    re.split(
        r"\s+",
        """
    и в во на с со по для к ко от до из у о об а но или не ни что как это эти этот
    мы вы они он она оно наш наша наше наши ваш ваша свой своя свои который которая
    которые где когда так также уже ещё еще все всё весь при над под без через про
    будет быть есть был была были который чтобы если то же ли бы ну год лет опыт работы
    the and of to in for with a an on is are we our you your at by be as or from it
    """.strip(),
    )
)

_RUSSIAN_ENDINGS = tuple(
    sorted(
        re.split(
            r"\s+",
            """
        иями ями ами ого его ому ему ыми ими ией ах ях ов ев ей ой ий ый ая яя ое ее
        ые ие ую юю ам ям ом ем ть ет ют ут ит ат ят ешь ишь ся сь ы и а я о е у ю ь
        """.strip(),
        ),
        key=len,
        reverse=True,
    )
)


def stem(token: str) -> str:
    """Лёгкая нормализация слова для сравнения текстов.

    Полноценный морфологический анализ для подбора избыточен: достаточно отрезать
    типичное окончание, чтобы «платёжного», «платёжный» и «платёжные» совпали.
    Основа короче трёх букв не укорачивается, иначе слишком много слов склеится.
    """
    word = token.lower().replace("ё", "е")
    if not re.search("[а-я]", word):
        return word
    for ending in _RUSSIAN_ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[: -len(ending)]
    return word


def tokenize(text: str, synonyms: Mapping[str, str] | None = None) -> list[str]:
    """Значимые слова текста в нормализованном виде.

    `synonyms` сводит алиасы навыков к одному токену («питон» → `python`), поэтому
    описание вакансии и рассказ кандидата сравниваются по смыслу, а не по написанию.
    """
    result = []
    for raw in _TOKEN.findall(text.lower()):
        if raw in _STOP_WORDS or len(raw) < 2:
            continue
        canonical = synonyms.get(raw) if synonyms else None
        result.append(canonical or stem(raw))
    return result


def cosine(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    """Косинусная близость разреженных векторов."""
    if len(left) > len(right):
        left, right = right, left
    return sum(weight * right.get(term, 0.0) for term, weight in left.items())


class TfidfIndex:
    """TF-IDF по коллекции документов: смысловая близость без внешних моделей.

    Это офлайновая базовая линия для фактора Semantic в балле соответствия. Веса редких
    слов выше: совпадение «платёж» говорит о кандидате больше, чем совпадение «разработка».
    Векторы нормированы, поэтому близость не зависит от длины текста.
    """

    def __init__(self, documents: Sequence[str], synonyms: Mapping[str, str] | None = None) -> None:
        """Считает документную частоту слов по коллекции."""
        self._synonyms = synonyms
        frequency: Counter[str] = Counter()
        for document in documents:
            frequency.update(set(tokenize(document, synonyms)))
        total = max(1, len(documents))
        self._idf = {
            term: math.log((1 + total) / (1 + count)) + 1.0 for term, count in frequency.items()
        }
        self._default_idf = math.log(1 + total) + 1.0

    def vector(self, text: str) -> dict[str, float]:
        """Нормированный TF-IDF-вектор текста с логарифмической частотой слов."""
        counts = Counter(tokenize(text, self._synonyms))
        weights = {
            term: (1.0 + math.log(count)) * self._idf.get(term, self._default_idf)
            for term, count in counts.items()
        }
        norm = math.sqrt(sum(value * value for value in weights.values()))
        if norm == 0:
            return {}
        return {term: value / norm for term, value in weights.items()}

    def similarity(self, left: str, right: str) -> float:
        """Близость двух текстов от 0 до 1."""
        return cosine(self.vector(left), self.vector(right))

    def shared_terms(self, left: str, right: str, limit: int = 4) -> list[str]:
        """Слова, которые сильнее всего сближают два текста, в написании из первого текста.

        Нужны объяснению подборки: «общие темы: платежи, микросервисы» понятнее голого числа.
        """
        left_vector = self.vector(left)
        right_vector = self.vector(right)
        shared = sorted(
            (term for term in left_vector if term in right_vector),
            key=lambda term: left_vector[term] * right_vector[term],
            reverse=True,
        )[:limit]
        surface: dict[str, str] = {}
        for raw in _TOKEN.findall(left):
            key = (self._synonyms or {}).get(raw.lower()) or stem(raw)
            surface.setdefault(key, raw)
        return [surface.get(term, term) for term in shared]
