"""Demo accounts and the signed-in user (#44, `technical-plan.md` §9.2).

The shapes match the phone page (`web/src/lib/demo/types.ts`).
"""

from uuid import UUID

from .common import Exclusion, KitchenType, Lang, StrictModel
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
    kitchen_type: KitchenType | None = None  # chosen from the number (#32)


class Me(StrictModel):
    """`GET /api/v1/me`: the signed-in user's company and kitchen profile."""

    user_id: UUID
    company_id: UUID
    company_name: str
    phone_masked: str
    exclusions: list[Exclusion]
    lang: Lang
    kitchen_type: KitchenType | None = None  # chosen from the number (#32)


# --- Connector accounts and the OAuth consent step (#48, `technical-plan.md` §7.3) ---


class SignupRequest(StrictModel):
    """`POST /api/v1/signup`: open sign-up for the connectors. Nothing is verified.

    The email is lower-cased; the password needs at least 10 characters; `phone_e164` is
    read like the demo account's.
    """

    email: str
    password: str
    phone_e164: str


class LoginRequest(StrictModel):
    """`POST /api/v1/session`: email and password log the browser in."""

    email: str
    password: str


class LoginResponse(StrictModel):
    """The session travels in the `simo_session` cookie.

    `phone_required` is true for a hand-out account that has no number yet: the login
    page then asks for it (`POST /api/v1/me/phone`) before going on.
    """

    phone_required: bool


class PhoneRequest(StrictModel):
    """`POST /api/v1/me/phone`: the number of a hand-out account, set once."""

    phone_e164: str


class ConnectRequestView(StrictModel):
    """`GET /api/v1/oauth/requests/{id}`: what the consent page shows.

    "Allow <client_name> to order for <company_name>?" `redirect_host` is where the browser
    goes next (the MCP spec asks the consent screen to show it).
    """

    client_name: str
    company_name: str
    phone_masked: str
    redirect_host: str


class ConnectDecision(StrictModel):
    """`POST /api/v1/oauth/requests/{id}`: Allow (true) or Cancel (false)."""

    allow: bool


class ConnectRedirect(StrictModel):
    """Where the browser goes next: the client's redirect URI with a code or an error."""

    redirect_to: str
