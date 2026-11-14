"""Audit event types (#41, technical-plan.md §8.5 and §9.7, docs/specs/dashboard.md §5).

The audit writer refuses any other type. The column is plain text, so a new type needs a
change here and no migration.
"""

from enum import StrEnum


class AuditEventType(StrEnum):
    # Session and identity
    session_started = "session_started"
    customer_identified = "customer_identified"
    session_ended = "session_ended"

    # Conversation, from the agent runtime and the MCP server
    buyer_said = "buyer_said"
    agent_said = "agent_said"
    tool_called = "tool_called"
    tool_returned = "tool_returned"

    # Engine and quote
    request_received = "request_received"
    products_searched = "products_searched"
    candidates_filtered = "candidates_filtered"
    availability_checked = "availability_checked"
    stock_rechecked = "stock_rechecked"
    line_resolved = "line_resolved"
    clarification_asked = "clarification_asked"
    quote_built = "quote_built"
    quote_rejected = "quote_rejected"
    quote_voided = "quote_voided"
    quote_edited = "quote_edited"
    quote_expired = "quote_expired"

    # Confirmation link and messages
    inbox_delivered = "inbox_delivered"
    sms_sent = "sms_sent"
    sms_delivered = "sms_delivered"
    sms_failed = "sms_failed"
    link_opened = "link_opened"
    flags_acknowledged = "flags_acknowledged"
    # Availability got worse at confirmation: the quote was replaced (confirmation-page.md §8)
    requote_needed = "requote_needed"

    # Outcome
    order_confirmed = "order_confirmed"
    order_cancelled = "order_cancelled"
    callback_requested = "callback_requested"

    # System: a rule set used for the first time, with its hashes (no session)
    rule_set_loaded = "rule_set_loaded"
