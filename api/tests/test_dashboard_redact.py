import json

import pytest

from app.schemas import Localized
from app.services.dashboard.redact import mask_email, redact, redact_text


def test_removes_secret_keys_at_any_depth():
    payload = {
        "token": "abc",
        "token_hash": "f00",
        "link": "https://simo.mankeli.co/c/abc",
        "cookie": "session=1",
        "authorization": "Bearer x",
        "access_token": "y",
        "kept": 1,
        "nested": {"deeper": [{"token": "abc", "ok": True}, {"Authorization": "Bearer z"}]},
        "headers": {"Cookie": "a=b", "Accept": "text/html"},
    }
    assert redact(payload) == {
        "kept": 1,
        "nested": {"deeper": [{"ok": True}, {}]},
        "headers": {"Accept": "text/html"},
    }


def test_keeps_keys_that_only_contain_a_secret_word():
    payload = {"tokens_used": 12, "linked_quote": "q_1", "token_count": 3}
    assert redact(payload) == payload


@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("+358401234512", "+358 40 *** **12"),
        ("Call +358401234512 now", "Call +358 40 *** **12 now"),
        ("+358 40 123 4512", "+358 40 *** **12"),
        ("+358-40-123-4512", "+358 40 *** **12"),
        ("+14155552671", "+1 41 *** **71"),
        ("(+442071838750)", "(+44 20 *** **50)"),
        ("tel:+358401234512", "tel:+358 40 *** **12"),
        ("a +358401234512, b +358409876543", "a +358 40 *** **12, b +358 40 *** **43"),
    ],
)
def test_masks_phone_numbers(raw, masked):
    assert redact(raw) == masked


def test_masks_an_unreadable_number_without_showing_its_digits():
    assert redact("+9991234567") == "+*** *** **67"


@pytest.mark.parametrize(
    "text",
    [
        "+358 40 *** **12",
        "Caller +358 40 *** **12 identified",
        "+1 41 *** **71",
        "2026-11-12T10:02:14+02:00",
        "price 12.95, 1 000 l",
        "b51c0e6a2f1d9c7e4a3b8f20d6e1c9a75f3e2b8d4c6a1f09e7d3b5c2a8f4e610",
        "sig abc+1234567890def",
        "+358 40",
    ],
)
def test_leaves_masked_numbers_and_other_digits_alone(text):
    assert redact(text) == text


@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("jane.doe@example.com", "j***@example.com"),
        ("Signed in as jane@mail.example.fi.", "Signed in as j***@mail.example.fi."),
        ("<j.d+tag@x-y.io>", "<j***@x-y.io>"),
        ("a@b.co and c.d@e.org", "a***@b.co and c***@e.org"),
    ],
)
def test_masks_emails(raw, masked):
    assert redact(raw) == masked


@pytest.mark.parametrize("text", ["j***@example.com", "Hi j***@example.com", "not@an-email", "@x"])
def test_leaves_masked_emails_and_non_emails_alone(text):
    assert redact(text) == text


def test_mask_email():
    assert mask_email("jane@example.com") == "j***@example.com"


@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("https://simo.mankeli.co/c/Xy7_k-29aQ", "https://simo.mankeli.co/c/…"),
        ("/c/Xy7_k-29aQ", "/c/…"),
        ("Open /c/abc123?x=1 now", "Open /c/…?x=1 now"),
        ('"url": "http://localhost/c/abc#top"', '"url": "http://localhost/c/…#top"'),
        ("/c/abc/def", "/c/…/def"),
    ],
)
def test_replaces_confirmation_urls(raw, masked):
    assert redact(raw) == masked


@pytest.mark.parametrize("text", ["/c/…", "https://simo.mankeli.co/c/…", "/c/", "/dashboard/s_1"])
def test_leaves_redacted_and_other_urls_alone(text):
    assert redact(text) == text


def test_a_token_in_a_url_never_survives():
    token = "kq3Z_9fT-0xY"
    text = redact_text(f"Sent https://simo.mankeli.co/c/{token} to +358401234512")
    assert token not in text
    assert text == "Sent https://simo.mankeli.co/c/… to +358 40 *** **12"


def test_walks_lists_tuples_and_nested_payloads():
    event = {
        "type": "sms_sent",
        "payload": {
            "to": "+358401234512",
            "body": "Vahvista tilaus: https://simo.mankeli.co/c/tok123",
            "recipients": ("+358409876543", {"email": "jane@example.com"}),
            "args": [[{"text": "mail jane@example.com"}]],
            "count": 2,
            "ok": True,
            "missing": None,
            "ratio": 1.5,
        },
    }
    assert redact(event) == {
        "type": "sms_sent",
        "payload": {
            "to": "+358 40 *** **12",
            "body": "Vahvista tilaus: https://simo.mankeli.co/c/…",
            "recipients": ["+358 40 *** **43", {"email": "j***@example.com"}],
            "args": [[{"text": "mail j***@example.com"}]],
            "count": 2,
            "ok": True,
            "missing": None,
            "ratio": 1.5,
        },
    }


def test_does_not_change_its_input():
    payload = {"token": "x", "to": "+358401234512", "list": ["jane@example.com"]}
    copy = json.loads(json.dumps(payload))
    redact(payload)
    assert payload == copy


def test_is_idempotent():
    payload = {"a": "+358401234512 jane@example.com /c/tok", "token": "t"}
    once = redact(payload)
    assert redact(once) == once


def test_dumps_a_model_first():
    assert redact(Localized(fi="Soita +358401234512", en="Call +358401234512")) == {
        "fi": "Soita +358 40 *** **12",
        "en": "Call +358 40 *** **12",
    }


def test_non_string_keys_and_scalars_pass_through():
    assert redact({1: "x", None: 2}) == {1: "x", None: 2}
    assert redact(42) == 42
    assert redact(None) is None
