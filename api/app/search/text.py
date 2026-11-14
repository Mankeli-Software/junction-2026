"""Query and name normalisation for product search (#30, docs/plans/30-product-search.md §3)."""

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from app.search.spelling import Vocabulary

HERE = Path(__file__).parent

# "17 %" = "17%", "2 kg" = "2kg", "0,5 l" = "0.5l", so refinements match the names exactly.
_AMOUNT = re.compile(r"(\d+)(?:[.,](\d+))?\s*(%|kg|g|l|dl|cl|ml)(?![a-z0-9])")
# Any letter or digit, so crème, fraîche and jalapeño stay whole words.
_TOKEN = re.compile(r"[^\W_](?:[^\W_]|[.%])*")
STOPWORDS = frozenset({"and", "the", "with", "for", "ja", "tai", "sekä", "kanssa"})
MIN_WORD_LENGTH = 3


def fold(s: str) -> str:
    """Lower case without accents, matching immutable_unaccent(lower(...)) in Postgres."""
    decomposed = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _join_amounts(s: str) -> str:
    def join(m: re.Match[str]) -> str:
        number = m[1] if m[2] is None else f"{m[1]}.{m[2]}"
        return f"{number}{m[3]}"

    return _AMOUNT.sub(join, s)


def tokens(s: str) -> list[str]:
    """Lower-case tokens with ä and ö kept (the Finnish stemmer needs them)."""
    return [t.rstrip(".") for t in _TOKEN.findall(_join_amounts(s.lower())) if t.rstrip(".")]


def is_amount(token: str) -> bool:
    return token[0].isdigit()


@dataclass(frozen=True)
class Term:
    """One word the buyer said, with its synonyms. Matching any of them covers the word."""

    word: str
    alternatives: tuple[str, ...]  # the word itself first, then synonyms; all lower case

    @property
    def folded(self) -> tuple[str, ...]:
        return tuple(fold(a) for a in self.alternatives)


@dataclass(frozen=True)
class Query:
    terms: tuple[Term, ...]  # words matched by full-text search and trigram similarity
    amounts: tuple[str, ...]  # "17%", "2kg": matched exactly against the name's tokens
    folded_text: str  # the whole query, folded, for the modifier check

    @property
    def fts(self) -> str:
        """Input for websearch_to_tsquery: every word and synonym, joined with `or`."""
        return " or ".join(dict.fromkeys(a for t in self.terms for a in t.alternatives))

    @property
    def trigram_words(self) -> list[str]:
        return [w for t in self.terms for w in t.folded]


@lru_cache
def synonyms() -> dict[str, tuple[str, ...]]:
    data = yaml.safe_load((HERE / "synonyms.yaml").read_text(encoding="utf-8")) or {}
    return {fold(k): tuple(str(v).lower() for v in vs) for k, vs in data.items()}


@lru_cache
def modifiers() -> tuple[str, ...]:
    data = yaml.safe_load((HERE / "modifiers.yaml").read_text(encoding="utf-8")) or []
    return tuple(fold(m) for m in data)


def _term(word: str, corrections: tuple[str, ...] = ()) -> Term:
    """The word, its spelling corrections, and the synonyms of both."""
    words = (word, *corrections)
    extra = [s for w in words for s in synonyms().get(fold(w), ())]
    return Term(word, tuple(dict.fromkeys((*words, *extra))))


def parse_query(
    q: str, ignore: frozenset[str] = frozenset(), vocabulary: "Vocabulary | None" = None
) -> Query:
    """Words, amounts and the folded text. With a vocabulary, a word that is in no product
    name gets its spelling corrections, or is split into two known words (spelling.py)."""
    terms: list[Term] = []
    amounts: list[str] = []
    for token in tokens(q):
        if is_amount(token):
            amounts.append(token)
        elif len(token) >= MIN_WORD_LENGTH and token not in STOPWORDS and token not in ignore:
            folded = fold(token)
            if vocabulary is None or folded in vocabulary or not folded.isalpha():
                terms.append(_term(token))
            elif corrections := vocabulary.corrections(folded):
                terms.append(_term(token, corrections))
            elif stem := vocabulary.stem(folded):
                terms.append(_term(token, (stem,)))
            elif parts := vocabulary.split(folded):
                terms.extend(_term(p) for p in parts if p not in ignore)
            else:
                terms.append(_term(token))
    return Query(tuple(terms), tuple(dict.fromkeys(amounts)), fold(q))


def name_tokens(name: str) -> set[str]:
    return {fold(t) for t in tokens(name)}


def unasked_modifiers(name: str, query: Query) -> tuple[str, ...]:
    """Modifier words in the product name that the buyer did not say (§3.4)."""
    folded = fold(name)
    return tuple(m for m in modifiers() if m in folded and m not in query.folded_text)
