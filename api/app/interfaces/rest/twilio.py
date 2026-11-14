"""`POST /api/v1/twilio/status`: Twilio's delivery report for a real SMS (#46, §9.7).

Only Twilio may call it: the `X-Twilio-Signature` must match an HMAC-SHA1 over the public
URL and the form parameters, keyed with our auth token. The URL is the one we gave Twilio
(`PUBLIC_BASE_URL`), not the one this process sees behind Caddy. A bad signature gets 403.

The form names the recipient's full number, so it is never logged. Not in the OpenAPI
document: it is for Twilio only.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.services import sms, twilio
from app.settings import get_settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/twilio", tags=["twilio"])


@router.post("/status", status_code=204, response_class=Response, include_in_schema=False)
async def twilio_status(
    request: Request, db: Annotated[AsyncSession, Depends(get_session)]
) -> Response:
    """Twilio's status callback: moves the message on to sent, delivered or failed, with
    `sms_delivered` or `sms_failed` in the audit log. 204 also for a message we don't
    know, so Twilio has nothing to retry."""
    form = await request.form()
    params = [(name, value) for name, value in form.multi_items() if isinstance(value, str)]
    url = sms.status_callback_url()
    if request.url.query:
        url += "?" + request.url.query
    received = request.headers.get("X-Twilio-Signature", "")
    if not twilio.valid_signature(get_settings().twilio_auth_token, url, params, received):
        log.warning("Refused a Twilio status callback with a bad or missing signature")
        raise HTTPException(status_code=403, detail="invalid signature")
    sid, status = form.get("MessageSid"), form.get("MessageStatus")
    if isinstance(sid, str) and isinstance(status, str):
        error_code = form.get("ErrorCode")
        await sms.record_status_callback(
            db, sid, status, error_code if isinstance(error_code, str) and error_code else None
        )
        await db.commit()
    return Response(status_code=204)
