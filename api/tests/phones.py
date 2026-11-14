"""Random demo numbers for tests that sign in."""

import random

from app.schemas import KitchenType
from app.seed import history


def new_number() -> str:
    """A random Finnish mobile number, so numbers in one test never collide.

    Never one of the vegan catering type: a new company of that type starts with the
    Vegan exclusion (#81), and the tests that use this expect a kitchen with none.
    """
    while True:
        phone = f"+35840{random.randrange(10**6, 10**7)}"
        if history.kitchen_type_for(phone) != KitchenType.vegan_catering:
            return phone
