import pytest

from app.services.phone import InvalidPhoneNumber, mask_phone, normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+358401234512", "+358401234512"),
        ("+358 40 123 4512", "+358401234512"),
        ("040 123 4512", "+358401234512"),  # no country code: read as Finnish
        ("+46 70 123 45 67", "+46701234567"),
        ("+1 (202) 555-0123", "+12025550123"),
    ],
)
def test_normalize_phone_gives_e164(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "hello", "+358 1", "+358 40 123 4512 3456 7890"])
def test_normalize_phone_rejects_impossible_numbers(raw):
    with pytest.raises(InvalidPhoneNumber):
        normalize_phone(raw)


def test_mask_phone_finnish_number():
    assert mask_phone("+358401234512") == "+358 40 *** **12"


def test_mask_phone_foreign_numbers():
    assert mask_phone("+46701234567") == "+46 70 *** **67"
    assert mask_phone("+12025550123") == "+1 20 *** **23"


def test_mask_phone_has_no_middle_dot():
    assert "·" not in mask_phone("+358401234512")
