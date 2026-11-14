"""The S.I.MO agent: the system prompt shared by the voice relay and the webshop chat (#53)."""

from .prompt import (
    AGENT_TOOLS,
    CALL_CONNECTED,
    END_CALL,
    PROMPT_VERSION,
    Channel,
    build_system_prompt,
)

__all__ = [
    "AGENT_TOOLS",
    "CALL_CONNECTED",
    "END_CALL",
    "PROMPT_VERSION",
    "Channel",
    "build_system_prompt",
]
