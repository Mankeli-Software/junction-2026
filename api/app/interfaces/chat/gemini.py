"""Gemini as a Genkit model, on our own `google-genai` (#57 spike).

Genkit's own Gemini plugin (`genkit-google-genai` 0.13) needs `google-genai<3`, and the voice
relay needs 3.x, so the chat registers this small model instead: Genkit keeps the tool loop
and the A2UI `Surfaces` middleware, and this file only turns a Genkit `ModelRequest` into one
streamed `generate_content` call and back.

- Tools are function declarations with their JSON Schema as is (`parameters_json_schema`),
  like the voice bridge's, so optional fields (`anyOf` with null) stay.
- Gemini 3 returns thought signatures on its parts and wants them back in the history; they
  ride in the Genkit part's metadata.
- Thinking text is never streamed or kept.
"""

import base64
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from genkit import FinishReason, Message, ModelResponse, ModelResponseChunk, Part, Role
from genkit.model import ModelContext, ModelRequest
from google import genai
from google.genai import types

log = logging.getLogger(__name__)

SIGNATURE = "thoughtSignature"

_FINISH = {
    "STOP": FinishReason.STOP,
    "MAX_TOKENS": FinishReason.LENGTH,
    "SAFETY": FinishReason.BLOCKED,
    "RECITATION": FinishReason.BLOCKED,
    "BLOCKLIST": FinishReason.BLOCKED,
    "PROHIBITED_CONTENT": FinishReason.BLOCKED,
    "SPII": FinishReason.BLOCKED,
}

# (model id, contents, config) -> the stream of responses. Swapped out by the tests.
StreamFn = Callable[
    [str, list[types.Content], types.GenerateContentConfig],
    AsyncIterator[types.GenerateContentResponse],
]


def client_stream(api_key: str) -> StreamFn:
    client = genai.Client(api_key=api_key)

    async def stream(
        model: str, contents: list[types.Content], config: types.GenerateContentConfig
    ) -> AsyncIterator[types.GenerateContentResponse]:
        async for response in await client.aio.models.generate_content_stream(
            model=model, contents=contents, config=config
        ):
            yield response

    return stream


def _signature(part: Part) -> bytes | None:
    raw = (part.metadata or {}).get(SIGNATURE)
    return base64.b64decode(raw) if isinstance(raw, str) else None


def _signed(signature: bytes | None) -> dict[str, Any] | None:
    return {SIGNATURE: base64.b64encode(signature).decode()} if signature else None


def to_contents(messages: list[Message]) -> tuple[str | None, list[types.Content]]:
    """The system text and the Gemini contents for Genkit's messages."""
    system: list[str] = []
    contents: list[types.Content] = []
    for message in messages:
        if message.role == Role.SYSTEM:
            system.extend(p.text for p in message.content if p.text)
            continue
        parts: list[types.Part] = []
        for part in message.content:
            if part.tool_request is not None:
                request = part.tool_request
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(
                            id=request.ref, name=request.name, args=dict(request.input or {})
                        ),
                        thought_signature=_signature(part),
                    )
                )
            elif part.tool_response is not None:
                response = part.tool_response
                output = response.output
                parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=response.ref,
                            name=response.name,
                            response=output if isinstance(output, dict) else {"output": output},
                        )
                    )
                )
            elif part.text:
                parts.append(types.Part(text=part.text, thought_signature=_signature(part)))
        if parts:
            role = "model" if message.role == Role.MODEL else "user"
            contents.append(types.Content(role=role, parts=parts))
    return ("\n\n".join(system) or None), contents


def to_config(request: ModelRequest, system: str | None) -> types.GenerateContentConfig:
    declarations = [
        types.FunctionDeclaration(
            name=tool.name,
            description=tool.description,
            parameters_json_schema=tool.input_schema or {"type": "object", "properties": {}},
        )
        for tool in request.tools or []
    ]
    return types.GenerateContentConfig(
        system_instruction=system,
        tools=[types.Tool(function_declarations=declarations)] if declarations else None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def gemini_model(model_id: str, stream: StreamFn):
    """A Genkit model function for `model_id`."""

    async def generate(request: ModelRequest, ctx: ModelContext) -> ModelResponse:
        system, contents = to_contents(list(request.messages))
        text: list[str] = []
        text_signature: bytes | None = None
        calls: list[Part] = []
        finish: str | None = None
        async for response in stream(model_id, contents, to_config(request, system)):
            for candidate in response.candidates or []:
                if candidate.finish_reason is not None:
                    finish = str(getattr(candidate.finish_reason, "value", candidate.finish_reason))
                for part in (candidate.content.parts if candidate.content else None) or []:
                    if part.thought:
                        continue
                    if part.function_call is not None:
                        call = Part.from_tool_request(
                            name=part.function_call.name or "",
                            input=dict(part.function_call.args or {}),
                            ref=part.function_call.id,
                            metadata=_signed(part.thought_signature),
                        )
                        calls.append(call)
                        ctx.send_chunk(ModelResponseChunk(role=Role.MODEL, content=[call]))
                    elif part.text:
                        text.append(part.text)
                        text_signature = part.thought_signature or text_signature
                        ctx.send_chunk(
                            ModelResponseChunk(role=Role.MODEL, content=[Part.from_text(part.text)])
                        )
                    elif part.thought_signature:
                        text_signature = part.thought_signature
        content: list[Part] = []
        if text:
            content.append(Part.from_text("".join(text), metadata=_signed(text_signature)))
        content.extend(calls)
        if not content:
            content.append(Part.from_text(""))
        reason = FinishReason.STOP if calls else _FINISH.get(finish or "STOP", FinishReason.OTHER)
        return ModelResponse(
            message=Message(role=Role.MODEL, content=content), finish_reason=reason
        )

    return generate
