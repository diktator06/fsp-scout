import math
from collections import Counter
from collections.abc import Mapping, Sequence

from app.services.matching.text_similarity import tokenize

K1 = 1.5
B = 0.75


class Bm25Index:
    """BM25 — классический поиск по ключевым словам, как в базах резюме.

    Это бейзлайн для сравнения: он видит только самоописание кандидата (о себе, опыт,
    заявленные навыки) и ничего не знает о тесте, категории и условиях. Токенизация
    та же, что у подбора (стемминг и синонимы навыков), чтобы сравнение было честным:
    разница в метриках — заслуга механики, а не нормализации текста.
    """

    def __init__(
        self, documents: Mapping[str, str], synonyms: Mapping[str, str] | None = None
    ) -> None:
        """Индексирует документы: ключ — идентификатор кандидата, значение — текст."""
        self._synonyms = synonyms
        self._terms = {key: Counter(tokenize(text, synonyms)) for key, text in documents.items()}
        self._lengths = {key: sum(terms.values()) for key, terms in self._terms.items()}
        self._average = sum(self._lengths.values()) / len(self._lengths) if self._lengths else 0.0
        frequency: Counter[str] = Counter()
        for terms in self._terms.values():
            frequency.update(terms.keys())
        total = len(self._terms)
        self._idf = {
            term: math.log(1 + (total - count + 0.5) / (count + 0.5))
            for term, count in frequency.items()
        }

    def score(self, key: str, query_terms: Sequence[str]) -> float:
        """BM25 документа по запросу."""
        terms = self._terms[key]
        length = self._lengths[key] or 1
        norm = K1 * (1 - B + B * length / (self._average or 1))
        return sum(
            self._idf.get(term, 0.0) * terms[term] * (K1 + 1) / (terms[term] + norm)
            for term in set(query_terms)
            if terms[term]
        )

    def rank(self, query: str, keys: Sequence[str] | None = None) -> list[str]:
        """Кандидаты по убыванию BM25; при равенстве — в исходном порядке."""
        query_terms = tokenize(query, self._synonyms)
        candidates = list(keys) if keys is not None else list(self._terms)
        return sorted(candidates, key=lambda key: self.score(key, query_terms), reverse=True)
