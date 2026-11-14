"""Twilio's request signatures and Messages API client (#46), with a fake transport."""

import httpx
import pytest

from app.services import twilio
from app.settings import Settings

# The example in Twilio's own SDK tests, checked against it, with its phone numbers swapped
# for Twilio's test numbers.
URL = "https://mycompany.com/myapp.php?foo=1&bar=2"
PARAMS = {
    "CallSid": "CA1234567890ABCDE",
    "Caller": "+15005550006",
    "Digits": "1234",
    "From": "+15005550006",
    "To": "+18005551212",
}
SIGNATURE = "qmN+4xY5uTfJ9jRNCfUFFV62w5I="

SETTINGS = Settings(
    _env_file=None,
    sms_twilio_enabled=True,
    twilio_account_sid="AC-test",
    twilio_auth_token="test-token",
    twilio_from_number="+15005550006",
)


def test_the_signature_is_twilios():
    assert twilio.signature("12345", URL, PARAMS.items()) == SIGNATURE
    # The order the form came in doesn't matter.
    assert twilio.signature("12345", URL, reversed(PARAMS.items())) == SIGNATURE


def test_a_changed_url_parameter_or_token_is_not_valid():
    assert twilio.valid_signature("12345", URL, PARAMS.items(), SIGNATURE)
    assert not twilio.valid_signature("12346", URL, PARAMS.items(), SIGNATURE)
    assert not twilio.valid_signature("12345", URL + "&x=1", PARAMS.items(), SIGNATURE)
    changed = {**PARAMS, "Digits": "1235"}
    assert not twilio.valid_signature("12345", URL, changed.items(), SIGNATURE)
    assert not twilio.valid_signature("12345", URL, PARAMS.items(), "")


def test_nothing_is_valid_without_an_auth_token():
    signature = twilio.signature("", URL, PARAMS.items())
    assert not twilio.valid_signature("", URL, PARAMS.items(), signature)


@pytest.fixture
def respond(monkeypatch):
    def use(handler):
        monkeypatch.setattr(twilio, "transport", httpx.MockTransport(handler))

    return use


async def test_a_created_message_gives_its_sid_and_status(respond):
    respond(lambda request: httpx.Response(201, json={"sid": "SM1", "status": "accepted"}))
    sent = await twilio.send_sms(
        to="+15005550001", body="hello", status_callback="https://x/cb", settings=SETTINGS
    )
    assert sent == twilio.SentMessage(sid="SM1", status="queued")


@pytest.mark.parametrize(
    ("response", "http_status", "code"),
    [
        (httpx.Response(400, json={"code": 21211, "message": "+15005550001 is bad"}), 400, "21211"),
        (httpx.Response(401, text="no"), 401, None),
        (httpx.Response(201, json={"status": "queued"}), 201, "unreadable response"),
    ],
)
async def test_a_refusal_carries_only_the_status_and_code(respond, response, http_status, code):
    respond(lambda request: response)
    with pytest.raises(twilio.TwilioError) as raised:
        await twilio.send_sms(
            to="+15005550001", body="the link", status_callback="https://x/cb", settings=SETTINGS
        )
    assert (raised.value.http_status, raised.value.code) == (http_status, code)
    assert "+15005550001" not in str(raised.value) and "link" not in str(raised.value)


async def test_twilio_out_of_reach_is_an_error_without_the_request(respond):
    def down(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    respond(down)
    with pytest.raises(twilio.TwilioError) as raised:
        await twilio.send_sms(
            to="+15005550001", body="the link", status_callback="https://x/cb", settings=SETTINGS
        )
    assert raised.value.http_status is None
    assert raised.value.code == "network: ConnectTimeout"
    assert raised.value.__cause__ is None
