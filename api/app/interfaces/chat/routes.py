"""The chat endpoints (#57, docs/plans/57-a2ui-chat.md §3).

- `POST /api/v1/chat`: the webshop chat, web session (cookie) only, so no agent token can
  use it. An SSE stream: `start`, then `text`, `a2ui` and `tool`, then `done` or `error`.
- `GET /api/v1/chat/menus/{menu_id}`: a menu `show_menu` stored, for the `MenuWeek` card.
- `GET /api/v1/chat/sent/latest`: for the `SentNotice` card.
- `POST /api/v1/confirmations/{token}/chat`: the confirmation page's "Ask for changes", the
  same stream, authorised by the link like the page's other actions, with `update_quote`
  only, always on the link's quote.

Without `CHAT_MODEL` the two streams answer 503 "chat not configured".
"""

import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.agent import build_system_prompt
from app.db import get_sessionmaker
from app.interfaces.chat import agent, menus
from app.interfaces.chat.conversations import Conversation, store
from app.interfaces.chat.schemas import ChatMenu, ChatRequest, ChatSentLatest
from app.interfaces.deps import web_session_user
from app.models import Confirmation, SmsMessage
from app.schemas import UpdateQuoteRequest
from app.services import (
    accounts,
    confirmation_page,
    customers,
    recipe_drafts,
    sessions,
    tokens,
    voice_calls,
)
from app.services.caller import Caller
from app.services.confirmation_page import ConfirmationRefused
from app.services.errors import NotFoundError, ServiceError
from app.services.phone import mask_phone
from app.settings import get_settings

log = logging.getLogger(__name__)

CLIENT_NAME = "S.I.MO chat"
SHOP_SCOPE = "shop"
UPDATE_QUOTE = "update_quote"

router = APIRouter(tags=["chat"])

WebUser = Annotated[Caller, Depends(web_session_user)]

STREAM_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
STREAM_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {"text/event-stream": {}},
        "description": "Server-sent events: start, text, a2ui, tool, done, error",
    },
    409: {"description": "Busy: still answering the previous message"},
    503: {"description": "Chat not configured (no CHAT_MODEL)"},
}

BUSY = {"code": "busy", "message": "S.I.MO is still answering the previous message."}
FAILED = {"code": "failed", "message": "S.I.MO could not answer. Try again."}

CONFIRMATION_PAGE_NOTE = """

# On the confirmation page
This chat is the "Ask for changes" panel on the confirmation page of quote {quote_id}. The \
buyer asks for changes in words. You have one tool, `update_quote`: call it with this quote \
and only what changes: a changed line with its `line_id`, a new line with a new `line_id`, or \
a line's id in `remove_line_ids`. The other lines stay by themselves. The lines now are:
{lines}
The page then shows the new quote; the buyer checks any flags and confirms with the page's \
own button. You can't confirm, cancel or send a link, and the buyer needs no new link: the \
page follows the change. After a change, say in a few words what changed. \
The page shows the order itself, so don't draw quote or recipe cards here."""


def refusal(edit: confirmation_page.ChatEdit) -> str:
    """The tool result for a change the page refused: the link stays on its quote."""
    assert edit.refused is not None
    text = (
        "Not changed: the order on the page stays as it was. The engine says: "
        f"{edit.refused.en} / {edit.refused.fi}"
    )
    if edit.clarification is not None:
        options = "; ".join(
            f"{o.label.en} / {o.label.fi} (product_id {o.product_id})"
            for o in edit.clarification.options
        )
        text += (
            f" Ask the buyer this question in words{': ' + options if options else ''}. When "
            "they answer, call update_quote again with the clarified line and the chosen "
            "product_id."
        )
    else:
        text += " Tell the buyer in a sentence and ask how they want to change it instead."
    return text


def chat_caller(user: Caller) -> Caller:
    """The user as the chat's MCP caller: the session and dashboard client of the chat."""
    return user.model_copy(update={"channel": "web_chat", "client_name": CLIENT_NAME})


def _require_model() -> None:
    if not get_settings().chat_model:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "chat not configured")


def _require_idle(conversation: Conversation) -> None:
    """409 before the stream while the conversation is still answering a message."""
    if conversation.busy:
        raise HTTPException(status.HTTP_409_CONFLICT, BUSY)


def _sse(kind: str, data: dict[str, Any]) -> ServerSentEvent:
    return ServerSentEvent(event=kind, data=json.dumps(data, ensure_ascii=False, default=str))


async def _ensure_token(db: Any, conversation: Conversation) -> str:
    """The conversation's caller token, a new one when it is about to expire. Commit
    before using it on /mcp."""
    now = datetime.now(UTC)
    if not conversation.token_valid(now):
        conversation.token = await tokens.issue_caller_token(
            db, conversation.user_id, channel="web_chat", client_name=CLIENT_NAME
        )
        conversation.token_expires_at = now + tokens.CALLER_TOKEN_TTL
    assert conversation.token is not None
    return conversation.token


def _buyer_turn(conversation: Conversation, body: ChatRequest) -> tuple[str, str, Any]:
    """The model's user turn text, the buyer's words for the log, and the action."""
    if body.action is not None:
        action = body.action.model_dump()
        return (
            agent.action_sentence(action, conversation),
            agent.action_plain(action, conversation.lang),
            action,
        )
    text = (body.message or "").strip()
    return text, text, None


Prepare = Callable[[Conversation], Awaitable[tuple[Any, str, agent.ChatMode, str | None]]]


async def _stream(
    conversation: Conversation, body: ChatRequest, prepare: Prepare
) -> AsyncIterator[ServerSentEvent]:
    """`start`, then the turn. `prepare` opens the turn in the database and returns the
    session id, the caller token, the mode and a recipe draft the turn shows."""
    yield _sse("start", {"conversation_id": conversation.id})
    if conversation.busy:
        yield _sse("error", BUSY)
        return
    conversation.busy = True
    try:
        try:
            session_id, token, mode, draft_id = await prepare(conversation)
        except ServiceError as error:
            log.info("Chat turn refused: %s", error)
            yield _sse("error", {"code": "failed", "message": str(error)})
            return
        text, said, action = _buyer_turn(conversation, body)
        if draft_id:
            text += (
                f"\n[The buyer uploaded a recipe photo. It was read into recipe draft {draft_id}, "
                "which the page shows as a card for them to check and confirm. Wait for "
                "recipe_confirmed before quoting it.]"
            )
            said = said or (
                "Lähetin reseptikuvan." if conversation.lang == "fi" else "I sent a recipe photo."
            )
        if body.action is None:
            agent.turn_language(conversation, said)
        lang = conversation.lang
        await agent.record_said(session_id, "buyer", said, lang)
        message = agent.user_message(text, action)
        async for kind, data in agent.run_turn(
            conversation,
            message,
            session_id=session_id,
            token=token,
            mode=mode,
            expect_draft=draft_id,
        ):
            yield _sse(kind, data)
    except Exception:
        log.exception("Chat turn failed")
        yield _sse("error", FAILED)
    finally:
        conversation.busy = False
        store.touch(conversation)


# --- The webshop chat ------------------------------------------------------------------------


@router.post("/chat", response_class=EventSourceResponse, responses=STREAM_RESPONSES)
async def chat(user: WebUser, body: ChatRequest) -> EventSourceResponse:
    """One buyer turn in the webshop chat. A new conversation starts when `conversation_id`
    is null or unknown (for example after 30 idle minutes or a restart)."""
    _require_model()
    conversation, _ = store.open(user.user_id, SHOP_SCOPE, body.conversation_id, user.lang)
    _require_idle(conversation)
    caller = chat_caller(user)

    async def prepare(conversation: Conversation) -> tuple[Any, str, agent.ChatMode, str | None]:
        async with get_sessionmaker()() as db:
            if not conversation.system_prompt:
                context = await customers.get_customer_context(db, caller)
                conversation.system_prompt = build_system_prompt(
                    context, "web_chat", today=voice_calls.business_date()
                )
            draft_id = None
            if body.attachment_draft_id:
                draft = await recipe_drafts.get(db, caller, body.attachment_draft_id)
                draft_id = draft.draft_id
            token = await _ensure_token(db, conversation)
            session = await sessions.current_session(db, caller)
            session_id = session.id
            await db.commit()  # the token must be in the database before /mcp sees it
        return session_id, token, agent.ChatMode(), draft_id

    return EventSourceResponse(_stream(conversation, body, prepare), headers=STREAM_HEADERS)


@router.get("/chat/menus/{menu_id}", response_model=ChatMenu, responses={404: {}})
async def get_menu(user: WebUser, menu_id: str) -> ChatMenu:
    """A menu from one of this user's chat conversations, built from our recipe data."""
    menu = store.find_menu(user.user_id, menu_id)
    if menu is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown menu")
    async with get_sessionmaker()() as db:
        return await menus.menu_view(db, chat_caller(user), menu)


@router.get(
    "/chat/sent/latest",
    response_model=ChatSentLatest,
    responses={404: {"description": "Nothing sent yet"}},
)
async def sent_latest(user: WebUser) -> ChatSentLatest:
    """How this user's latest confirmation request went, for the `SentNotice` card: the
    masked number, `delivery_status` as `request_confirmation` says it (`sent` or `failed`
    only once a real SMS went, which needs Twilio, #46) and whether the inbox has it."""
    async with get_sessionmaker()() as db:
        confirmation = await db.scalar(
            select(Confirmation)
            .where(Confirmation.user_id == user.user_id)
            .order_by(Confirmation.created_at.desc())
            .limit(1)
        )
        if confirmation is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "nothing sent yet")
        messages = list(
            await db.scalars(
                select(SmsMessage).where(SmsMessage.confirmation_id == confirmation.id)
            )
        )
    by_path = {m.path: m for m in messages}
    twilio, inbox = by_path.get("twilio"), by_path.get("inbox")
    if twilio is not None and twilio.status in ("sent", "failed"):
        delivery = twilio.status
    elif inbox is not None and inbox.status == "held":
        delivery = "held"
    else:
        delivery = "off"
    return ChatSentLatest(
        sent_to_masked=mask_phone(confirmation.recipient_e164),
        delivery_status=delivery,  # type: ignore[arg-type]
        inbox=inbox is not None,
    )


# --- The confirmation page's chat ------------------------------------------------------------


def _token_scope(token: str) -> str:
    return "confirmation:" + tokens.hash_token(token)[:24]


@router.post(
    "/confirmations/{token}/chat",
    response_class=EventSourceResponse,
    responses={
        **STREAM_RESPONSES,
        404: {"description": "Unknown link"},
        409: {"description": "The order is closed, or busy"},
        410: {"description": "Expired"},
    },
)
async def confirmation_chat(token: str, body: ChatRequest) -> EventSourceResponse:
    """ "Ask for changes" on the confirmation page: the chat as the link's user, with
    `update_quote` only. The page reloads its view after `done`."""
    _require_model()
    async with get_sessionmaker()() as db:
        try:
            target = await confirmation_page.chat_target(db, token)
        except NotFoundError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except ConfirmationRefused as error:
            raise HTTPException(error.status, error.detail().model_dump(mode="json")) from error
        account = await accounts.me(db, target.user_id)
        await db.commit()
    if account is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "the order is closed")
    caller = Caller(
        user_id=account.user_id,
        company_id=account.company_id,
        company_name=account.company_name,
        phone_masked=account.phone_masked,
        exclusions=account.exclusions,
        lang=account.lang,
        channel="web_chat",
        client_name=CLIENT_NAME,
    )
    conversation, _ = store.open(
        account.user_id, _token_scope(token), body.conversation_id, account.lang
    )
    _require_idle(conversation)

    async def update_quote(arguments: dict[str, Any]) -> dict[str, Any]:
        """The chat's change, through the page's own edit path, on the link's quote
        whatever id the model wrote."""
        try:
            request = UpdateQuoteRequest.model_validate(
                {
                    "quote_id": "link",
                    "lines": arguments.get("lines") or [],
                    "remove_line_ids": arguments.get("remove_line_ids") or [],
                }
            )
        except ValidationError as error:
            return {"error": f"invalid lines: {error.errors(include_url=False)}"}
        async with get_sessionmaker()() as db:
            try:
                edit = await confirmation_page.chat_edit(
                    db, token, request.lines, request.remove_line_ids
                )
            except ServiceError as error:
                await db.commit()
                return {"error": str(error)}
            await db.commit()
        if edit.quote is not None:
            return {"output": edit.quote.model_dump(mode="json")}
        return {"error": refusal(edit)}

    mode = agent.ChatMode(
        tool_names=frozenset({UPDATE_QUOTE}),
        show_menu=False,
        local={UPDATE_QUOTE: update_quote},
        cards=False,
    )

    async def prepare(conversation: Conversation) -> tuple[Any, str, agent.ChatMode, str | None]:
        async with get_sessionmaker()() as db:
            current = await confirmation_page.chat_target(db, token)
            context = await customers.get_customer_context(db, caller)
            lines = json.dumps(
                [line.model_dump(mode="json", exclude_none=True) for line in current.lines],
                ensure_ascii=False,
            )
            # Rebuilt every turn: the lines change with each update.
            conversation.system_prompt = build_system_prompt(
                context, "web_chat", today=voice_calls.business_date()
            ) + CONFIRMATION_PAGE_NOTE.format(quote_id=current.quote_id, lines=lines)
            conversation.latest_quote_id = current.quote_id
            token_ = await _ensure_token(db, conversation)
            await db.commit()
        return current.session_id, token_, mode, None

    return EventSourceResponse(_stream(conversation, body, prepare), headers=STREAM_HEADERS)
