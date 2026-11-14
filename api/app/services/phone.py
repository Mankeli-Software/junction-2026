"""Phone numbers: E.164 normalisation and the one masking function used everywhere.

Any country is accepted (#44 decision 3). A number without a country code is read as
Finnish, since the number field defaults to +358 (`call-screen.md` §2.1).
"""

import phonenumbers

DEFAULT_REGION = "FI"


class InvalidPhoneNumber(ValueError):
    """The text is not a possible phone number."""


def normalize_phone(raw: str) -> str:
    """Return the number in E.164 form (`+358401234512`), or raise InvalidPhoneNumber."""
    try:
        number = phonenumbers.parse(raw, DEFAULT_REGION)
    except phonenumbers.NumberParseException as error:
        raise InvalidPhoneNumber(str(error)) from error
    if not phonenumbers.is_possible_number(number):
        raise InvalidPhoneNumber("not a possible phone number")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def mask_phone(phone_e164: str) -> str:
    """`+358401234512` -> `+358 40 *** **12`.

    Country code, the first two national digits, `*** **`, the last two digits. This is
    the only form a number may take on screens and in audit events (CLAUDE.md design rules).
    """
    number = phonenumbers.parse(phone_e164, None)
    national = phonenumbers.national_significant_number(number)
    return f"+{number.country_code} {national[:2]} *** **{national[-2:]}"
