"""The chat's own request and response models (#57, docs/plans/57-a2ui-chat.md §3).

They belong to the chat endpoints only, so they live here and not in the shared contract
(`app.schemas`).
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_MESSAGE = 2000
MAX_CONTEXT_JSON = 2000

Weekday = Literal["mon", "tue", "wed", "thu", "fri"]


class A2uiClientAction(BaseModel):
    """A card's button, as A2UI v0.9 sends it back: `{name, surfaceId, sourceComponentId,
    timestamp, context}`."""

    name: str = Field(min_length=1, max_length=64)
    surfaceId: str = Field(default="", max_length=200)  # noqa: N815 - A2UI's own field names
    sourceComponentId: str = Field(default="", max_length=200)  # noqa: N815
    timestamp: str = Field(default="", max_length=64)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("context")
    @classmethod
    def _small(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, default=str)) > MAX_CONTEXT_JSON:
            raise ValueError("the action context is too large")
        return value


class ChatRequest(BaseModel):
    """One buyer turn: a message or a card action, exactly one of them."""

    conversation_id: str | None = Field(default=None, max_length=64)
    message: str | None = Field(default=None, max_length=MAX_MESSAGE)
    action: A2uiClientAction | None = None
    # A recipe photo read with POST /api/v1/recipe-drafts/read just before this message.
    attachment_draft_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _one_of(self) -> "ChatRequest":
        has_message = self.message is not None and self.message.strip() != ""
        if has_message == (self.action is not None):
            raise ValueError("give exactly one of message and action")
        return self


class ChatMenuDay(BaseModel):
    day: Weekday
    recipe_id: str
    name: str
    image_url: str | None
    portions: int
    # Ingredients with a product link (what the order will contain), and all ingredients.
    linked_count: int | None = None
    ingredient_count: int | None = None


class ChatMenu(BaseModel):
    """A menu that `show_menu` stored in the conversation, built from our recipe data."""

    menu_id: str
    days: list[ChatMenuDay]


class ChatSentLatest(BaseModel):
    """For the `SentNotice` card: how this user's latest confirmation request went, in the
    words of `request_confirmation`'s answer. The page shows the SMS line only when
    `delivery_status` is `sent`. The number is masked (`+358 40 *** **12`)."""

    sent_to_masked: str | None
    delivery_status: Literal["held", "sent", "failed", "off"]
    inbox: bool
