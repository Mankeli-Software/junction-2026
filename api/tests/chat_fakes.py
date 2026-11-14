"""Fakes for the chat tests (#57): the Gemini model at Genkit's model boundary.

`FakeModel` is registered on the chat's Genkit as `fake/chat`; set `CHAT_MODEL=fake/chat`.
Each model call answers with the next step of the script: `text(...)` streams in small
chunks (so fences and links get split), `call(...)` asks for one tool.
"""

import itertools
import json
from typing import Any

from genkit import Message, ModelResponse, ModelResponseChunk, Part, Role
from genkit.model import ModelContext, ModelRequest

from app.interfaces.chat import agent, surfaces

MODEL = "fake/chat"
CHUNK = 7

_refs = itertools.count(1)


def text(value: str) -> list[Part]:
    return [Part.from_text(value)]


def call(name: str, arguments: dict[str, Any] | None = None) -> list[Part]:
    return [Part.from_tool_request(name=name, input=arguments or {}, ref=f"r{next(_refs)}")]


def fence(*components: dict[str, Any]) -> str:
    """A fenced A2UI surface as the model writes it, with the catalog's placeholder id."""
    envelopes = [
        {"createSurface": {"surfaceId": "SURFACE_ID", "catalogId": surfaces.catalog_id()}},
        {"updateComponents": {"surfaceId": "SURFACE_ID", "components": list(components)}},
    ]
    return "\n```a2ui\n" + json.dumps(envelopes) + "\n```\n"


class FakeModel:
    def __init__(self) -> None:
        self.script: list[list[Part] | Any] = []
        self.requests: list[ModelRequest] = []

    def reset(self, *steps: list[Part] | Any) -> None:
        self.script = list(steps)
        self.requests = []

    async def __call__(self, request: ModelRequest, ctx: Any) -> ModelResponse:
        self.requests.append(request.model_copy(deep=True))
        if not self.script:
            raise AssertionError("the fake model has no step left")
        step = self.script.pop(0)
        if callable(step):
            step = step(request)
        for part in step:
            if part.text is not None:
                for i in range(0, len(part.text), CHUNK):
                    ctx.send_chunk(
                        ModelResponseChunk(
                            role=Role.MODEL, content=[Part.from_text(part.text[i : i + CHUNK])]
                        )
                    )
            else:
                ctx.send_chunk(ModelResponseChunk(role=Role.MODEL, content=[part]))
        return ModelResponse(message=Message(role=Role.MODEL, content=step), finish_reason="stop")

    # --- What the model saw ---

    def tool_names(self, index: int = 0) -> list[str]:
        return [t.name for t in self.requests[index].tools or []]

    def tool_results(self, index: int) -> list[Any]:
        """The tool responses in request `index`'s last message."""
        last = self.requests[index].messages[-1]
        return [p.tool_response.output for p in last.content if p.tool_response is not None]

    def user_texts(self, index: int) -> list[str]:
        out = []
        for message in self.requests[index].messages:
            if message.role == Role.USER:
                out.append("".join(p.text or "" for p in message.content))
        return out


fake_model = FakeModel()
_registered = False


def install() -> FakeModel:
    global _registered
    if not _registered:

        async def model_fn(request: ModelRequest, ctx: ModelContext) -> ModelResponse:
            return await fake_model(request, ctx)

        agent.get_ai().define_model(name=MODEL, fn=model_fn)
        _registered = True
    fake_model.reset()
    return fake_model


def events(body: str) -> list[tuple[str, Any]]:
    """An SSE body as `(event, data)` pairs."""
    out = []
    kind = None
    for line in body.splitlines():
        if line.startswith("event:"):
            kind = line[6:].strip()
        elif line.startswith("data:") and kind is not None:
            out.append((kind, json.loads(line[5:].strip())))
            kind = None
    return out


def streamed_text(pairs: list[tuple[str, Any]]) -> str:
    return "".join(d["delta"] for k, d in pairs if k == "text")


def cards(pairs: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    """Every component in the stream's `a2ui` events."""
    out = []
    for kind, data in pairs:
        if kind != "a2ui":
            continue
        for envelope in data["envelopes"]:
            update = envelope.get("updateComponents")
            if update:
                out.extend(update["components"])
    return out
