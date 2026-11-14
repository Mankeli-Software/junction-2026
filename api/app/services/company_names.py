"""Generated demo company names: "<Adjective> <Noun> Oy" with alliteration (#44, minimal).

The names are built only from these lists, never from anything the visitor typed, so they
are safe on the public dashboard. #32 may replace the lists with better ones.
"""

import random
from collections.abc import Iterator

ADJECTIVES = (
    "Hassu", "Hilpeä", "Hurja", "Huoleton", "Herkkä",
    "Pörröinen", "Pirteä", "Pullea", "Puuhakas", "Pippurinen",
    "Kiltti", "Kujeileva", "Kukkea", "Kipakka",
    "Mehevä", "Mukava", "Muhkea", "Mietteliäs",
    "Sävyisä", "Sisukas", "Säkenöivä",
    "Touhukas", "Tuuhea", "Tyytyväinen",
    "Lempeä", "Leppoisa", "Lystikäs",
    "Veikeä", "Vilkas", "Vikkelä",
    "Reipas", "Rapsakka", "Rohkea",
)  # fmt: skip

NOUNS = (
    "Hauki", "Hirvi", "Hilla", "Hamsteri", "Haapana",
    "Peura", "Pupu", "Pulla", "Pingviini", "Porkkana",
    "Kettu", "Karhu", "Kurki", "Kaali",
    "Majava", "Mansikka", "Muikku", "Mustikka",
    "Siili", "Silakka", "Saukko", "Sieni",
    "Tikka", "Tiikeri", "Taimen",
    "Lohi", "Lammas", "Leivos",
    "Varis", "Voileipä", "Vesikko",
    "Rapu", "Riekko", "Rusina",
)  # fmt: skip

# Alliterating pairs: the adjective and the noun start with the same letter.
PAIRS = tuple((a, n) for a in ADJECTIVES for n in NOUNS if a[0] == n[0])

PLAIN_TRIES = 5


def company_name_candidates(rng: random.Random | None = None) -> Iterator[str]:
    """Yield names to try until one is unique.

    The first PLAIN_TRIES are plain ("Hassu Hauki Oy"); after that each gets a number
    ("Hassu Hauki 17 Oy"). The iterator never ends; the caller stops at the first free name.
    """
    rng = rng or random.SystemRandom()
    tries = 0
    while True:
        adjective, noun = rng.choice(PAIRS)
        if tries < PLAIN_TRIES:
            yield f"{adjective} {noun} Oy"
        else:
            yield f"{adjective} {noun} {rng.randint(2, 999)} Oy"
        tries += 1
