"""Chat conversations, in memory (#57 decision 3, plan §4.A step 2).

Keyed by user, scope and conversation id: the webshop chat is scope `shop`, the
confirmation page's "Ask for changes" chat is one scope per link. A conversation holds the
model history, the caller token, the language, the latest quote id and the menus that
`show_menu` stored. It is dropped after 30 idle minutes, and takes one message at a time.
A restart of the API starts new conversations; every turn is still in the audit log.
"""

import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

IDLE_S = 30 * 60.0


@dataclass(frozen=True)
class MenuSlot:
    day: str
    recipe_id: str
    portions: int


@dataclass(frozen=True)
class Menu:
    menu_id: str
    days: tuple[MenuSlot, ...]


@dataclass
class Conversation:
    id: str
    user_id: uuid.UUID
    scope: str
    lang: str
    last_used: float
    system_prompt: str = ""
    history: list[Any] = field(default_factory=list)  # genkit Messages, no system message
    token: str | None = None
    token_expires_at: datetime | None = None
    latest_quote_id: str | None = None
    menus: dict[str, Menu] = field(default_factory=dict)
    # One message at a time. A flag, not an asyncio.Lock: requests may run in different
    # event loops (tests), and the check and the set have no await between them.
    busy: bool = False

    def token_valid(self, now: datetime, margin: timedelta = timedelta(minutes=2)) -> bool:
        return (
            self.token is not None
            and self.token_expires_at is not None
            and now + margin < self.token_expires_at
        )


class ConversationStore:
    def __init__(self, clock: Callable[[], float] = time.monotonic, idle_s: float = IDLE_S):
        self.clock = clock
        self.idle_s = idle_s
        self._items: dict[tuple[uuid.UUID, str, str], Conversation] = {}

    def __len__(self) -> int:
        return len(self._items)

    def sweep(self) -> None:
        """Drop the conversations idle for longer than the limit (not a busy one)."""
        cutoff = self.clock() - self.idle_s
        for key, conversation in list(self._items.items()):
            if conversation.last_used < cutoff and not conversation.busy:
                del self._items[key]

    def get(self, user_id: uuid.UUID, scope: str, conversation_id: str) -> Conversation | None:
        self.sweep()
        return self._items.get((user_id, scope, conversation_id))

    def open(
        self, user_id: uuid.UUID, scope: str, conversation_id: str | None, lang: str
    ) -> tuple[Conversation, bool]:
        """The conversation, or a new one when the id is null or unknown. True when new."""
        if conversation_id:
            found = self.get(user_id, scope, conversation_id)
            if found is not None:
                found.last_used = self.clock()
                return found, False
        conversation = Conversation(
            id=secrets.token_urlsafe(12),
            user_id=user_id,
            scope=scope,
            lang=lang,
            last_used=self.clock(),
        )
        self._items[(user_id, scope, conversation.id)] = conversation
        return conversation, True

    def touch(self, conversation: Conversation) -> None:
        conversation.last_used = self.clock()

    def find_menu(self, user_id: uuid.UUID, menu_id: str) -> Menu | None:
        """A menu from any of this user's conversations."""
        self.sweep()
        for (owner, _, _), conversation in self._items.items():
            if owner == user_id and menu_id in conversation.menus:
                return conversation.menus[menu_id]
        return None

    def clear(self) -> None:
        self._items.clear()


store = ConversationStore()
