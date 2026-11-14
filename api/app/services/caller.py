"""Who is calling. Internal to the API, so not part of the shared contract in `app.schemas`."""

import uuid
from typing import Literal

from pydantic import BaseModel

from app.schemas import Exclusion, Lang

Channel = Literal["phone", "web", "web_chat", "connector"]


class Caller(BaseModel):
    user_id: uuid.UUID
    company_id: uuid.UUID
    company_name: str
    phone_masked: str
    exclusions: list[Exclusion]
    lang: Lang
    channel: Channel
    client_name: str | None = None
