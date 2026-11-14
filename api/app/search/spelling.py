"""Spelling correction against the catalogue's own words (#30, spec §3.2).

A query word that is not a word in any product name gets the known words one edit away
(a dropped, added or changed letter, or two neighbouring letters swapped): "miato" ->
"maito", "kemaa" -> "kermaa". A joined pair is split when both halves are known words:
"laktoositonmaito" -> "laktoositon maito". Known words are never changed.

Lookup uses a deletion index (every word with one letter removed), so a correction costs
a few dictionary lookups, not a scan of the vocabulary.
"""

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.search.text import fold

_WORD = re.compile(r"[a-zåäöéü]{3,}")
MAX_CORRECTIONS = 3
MIN_SPLIT_PART = 3


def _deletes(word: str) -> set[str]:
    return {word[:i] + word[i + 1 :] for i in range(len(word))}


def _one_edit(a: str, b: str) -> bool:
    """True if a and b are one insertion, deletion, substitution or adjacent swap apart."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        i, j = diff[0], diff[-1]
        return len(diff) == 2 and j == i + 1 and a[i] == b[j] and a[j] == b[i]
    short, long = (a, b) if len(a) < len(b) else (b, a)
    return any(long[:i] + long[i + 1 :] == short for i in range(len(long)))


@dataclass
class Vocabulary:
    counts: Counter[str]  # folded word -> how many names use it
    spelled: dict[str, str]  # folded word -> its most common spelling, with ä and ö
    index: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    @classmethod
    def from_names(cls, names: Iterable[str]) -> "Vocabulary":
        counts: Counter[str] = Counter()
        spellings: dict[str, Counter[str]] = defaultdict(Counter)
        for name in names:
            for word in _WORD.findall(name.lower()):
                folded = fold(word)
                counts[folded] += 1
                spellings[folded][word] += 1
        vocab = cls(counts, {f: c.most_common(1)[0][0] for f, c in spellings.items()})
        for word in counts:
            vocab.index[word].add(word)
            for d in _deletes(word):
                vocab.index[d].add(word)
        return vocab

    def __contains__(self, folded: str) -> bool:
        return folded in self.counts

    def corrections(self, folded: str) -> tuple[str, ...]:
        """Known words one edit away, most common first (ties by spelling), as spelled."""
        candidates: set[str] = set()
        for key in {folded, *_deletes(folded)}:
            candidates |= self.index.get(key, set())
        found = sorted(
            (w for w in candidates if _one_edit(folded, w)), key=lambda w: (-self.counts[w], w)
        )
        return tuple(self.spelled[w] for w in found[:MAX_CORRECTIONS])

    def split(self, folded: str) -> tuple[str, str] | None:
        """Two known words that make up the word, preferring the most common pair."""
        best: tuple[int, int, str, str] | None = None
        for cut in range(MIN_SPLIT_PART, len(folded) - MIN_SPLIT_PART + 1):
            left, right = folded[:cut], folded[cut:]
            if left in self and right in self:
                key = (min(self.counts[left], self.counts[right]), -cut, left, right)
                if best is None or key > best:
                    best = key
        return (self.spelled[best[2]], self.spelled[best[3]]) if best else None
