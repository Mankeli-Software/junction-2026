"""Demo accounts and the signed-in user (#44, `technical-plan.md` §9.2).

The shapes match the phone page (`web/src/lib/demo/types.ts`).
"""

from uuid import UUID

from .common import Exclusion, Lang, StrictModel
from .engine import UsualItem


class DemoAccountRequest(StrictModel):
    """`POST /api/v1/demo/accounts`: typing a phone number is the login.

    `phone_e164` may be typed loosely ("040 123 4512"); the server normalises it, reading a
    number without a country code as Finnish.
    """

    phone_e164: str
    exclusions: list[Exclusion]
    lang: Lang


class DemoAccountResponse(StrictModel):
    """The browser's demo user. The session token travels only in the `simo_session` cookie."""

    user_id: UUID
    company_id: UUID
    company_name: str
    phone_masked: str  # "+358 40 *** **12"
    exclusions: list[Exclusion]
    usual_items: list[UsualItem]
    new_company: bool  # the number was new, so its company was just created
    new_user: bool  # this browser got a new user (a new browser, or another number)


class Me(StrictModel):
    """`GET /api/v1/me`: the signed-in user's company and kitchen profile."""

    user_id: UUID
    company_id: UUID
    company_name: str
    phone_masked: str
    exclusions: list[Exclusion]
    lang: Lang
