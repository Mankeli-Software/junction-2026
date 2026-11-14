import random
import re
from itertools import islice

from app.services.company_names import (
    ADJECTIVES,
    NOUNS,
    PAIRS,
    PLAIN_TRIES,
    company_name_candidates,
)


def test_every_pair_alliterates():
    assert PAIRS
    assert all(adjective[0] == noun[0] for adjective, noun in PAIRS)


def test_every_word_has_a_partner():
    used_adjectives = {a for a, _ in PAIRS}
    used_nouns = {n for _, n in PAIRS}
    assert used_adjectives == set(ADJECTIVES)
    assert used_nouns == set(NOUNS)


def test_first_tries_are_plain_then_numbered():
    names = list(islice(company_name_candidates(random.Random(1)), PLAIN_TRIES + 3))

    plain = re.compile(r"^(\w+) (\w+) Oy$")
    numbered = re.compile(r"^(\w+) (\w+) \d+ Oy$")
    assert all(plain.match(name) for name in names[:PLAIN_TRIES])
    assert all(numbered.match(name) for name in names[PLAIN_TRIES:])


def test_names_have_no_middle_dot():
    names = islice(company_name_candidates(random.Random(2)), 50)
    assert all("·" not in name for name in names)
