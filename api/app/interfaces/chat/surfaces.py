"""What the chat may put on the page (plan §3, `docs/specs/a2ui.md` §3).

- **The catalog** is `catalog.json` here, a copy of `web/src/lib/a2ui/catalog.json` (the
  API image has no `web/`); a test keeps the two equal.
- **Ids only.** Every component keeps only the props the catalog gives it, so a domain card
  carries its id and nothing else; the page loads the engine's data itself.
- **No duplicate cards.** A second card for the same component and id in one turn is
  dropped.
- **Gap filling.** A tool that has a card and no matching card from the model gets one from
  the server at the end of the turn.
- **No confirmation link.** Text and envelopes that contain `/c/` never reach the stream.
"""

import json
import re
import uuid
from functools import cache
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).with_name("catalog.json")
A2UI_VERSION = "v0.9"

# The props each component may carry, besides `id` and `component`.
ALLOWED_PROPS: dict[str, frozenset[str]] = {
    "Column": frozenset({"children"}),
    "Row": frozenset({"children"}),
    "Text": frozenset({"text", "variant"}),
    "Notice": frozenset({"text"}),
    "Button": frozenset({"label", "action", "primary"}),
    "RecipeDraftCard": frozenset({"draftId"}),
    "RecipeCard": frozenset({"recipeId", "portions"}),
    "QuoteCard": frozenset({"quoteId"}),
    "MenuWeek": frozenset({"menuId"}),
    "SentNotice": frozenset(),
}

# Domain cards and the prop that identifies them. SentNotice has no id: one per turn.
CARD_ID: dict[str, str | None] = {
    "RecipeDraftCard": "draftId",
    "RecipeCard": "recipeId",
    "QuoteCard": "quoteId",
    "MenuWeek": "menuId",
    "SentNotice": None,
}

# The confirmation link is `<PUBLIC_BASE_URL>/c/<token>`; a word that contains `/c/` goes.
LINK_MARK = "/c/"
_LINK_WORD = re.compile(r"\S*/c/\S*")


@cache
def catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def catalog_id() -> str:
    return catalog()["id"]


def has_link(value: Any) -> bool:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return LINK_MARK in text


class LinkScrubber:
    """Streams text with every word that contains `/c/` taken out. The last word of a delta
    is held back until the next whitespace, so a link split across deltas is caught too."""

    def __init__(self) -> None:
        self._held = ""
        self.sent: list[str] = []

    def feed(self, delta: str) -> str:
        text = self._held + delta
        cut = max(text.rfind(" "), text.rfind("\n"), text.rfind("\t"))
        if cut < 0:
            self._held = text
            return ""
        ready, self._held = text[: cut + 1], text[cut + 1 :]
        return self._emit(ready)

    def flush(self) -> str:
        text, self._held = self._held, ""
        return self._emit(text)

    def _emit(self, text: str) -> str:
        clean = _LINK_WORD.sub("", text) if LINK_MARK in text else text
        if clean:
            self.sent.append(clean)
        return clean

    @property
    def text(self) -> str:
        return re.sub(r"[ \t]+", " ", "".join(self.sent)).strip()


def _card_key(component: dict[str, Any]) -> tuple[str, str] | None:
    name = component.get("component")
    if name not in CARD_ID:
        return None
    prop = CARD_ID[name]
    return (name, "" if prop is None else str(component.get(prop, "")))


def _clean_component(component: Any) -> dict[str, Any] | None:
    if not isinstance(component, dict):
        return None
    name = component.get("component")
    if name not in ALLOWED_PROPS or not isinstance(component.get("id"), str):
        return None
    allowed = ALLOWED_PROPS[name]
    clean = {
        "id": component["id"],
        "component": name,
        **{k: v for k, v in component.items() if k in allowed},
    }
    # Genkit's A2UI instructions teach `variant: "primary"` and h2/h3 headings; our catalog
    # says `primary: true` and `heading`.
    variant = component.get("variant")
    if name == "Button" and variant == "primary":
        clean["primary"] = True
    if name == "Text" and isinstance(variant, str) and variant.startswith("h"):
        clean["variant"] = "heading"
    return clean


class TurnCards:
    """The cards of one turn: what the model drew, and what the tools call for."""

    def __init__(self) -> None:
        self.drawn: set[tuple[str, str]] = set()
        self.expected: dict[str, tuple[str, str]] = {}  # slot -> (component, id)

    def expect(self, component: str, card_id: str = "", *, slot: str | None = None) -> None:
        """A tool that has a card ran. A later call for the same slot replaces the card (the
        latest quote only)."""
        self.expected[slot or f"{component}:{card_id}"] = (component, card_id)

    def filter(self, envelopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The model's envelopes from one fence, cleaned: unknown components and props
        dropped, duplicate cards dropped, and nothing with the link."""
        out: list[dict[str, Any]] = []
        emptied: set[str] = set()
        for envelope in envelopes:
            if not isinstance(envelope, dict) or has_link(envelope):
                continue
            update = envelope.get("updateComponents")
            if not isinstance(update, dict):
                out.append(envelope)
                continue
            kept: list[dict[str, Any]] = []
            dropped: set[str] = set()
            for raw in update.get("components") or []:
                component = _clean_component(raw)
                if component is None:
                    if isinstance(raw, dict) and isinstance(raw.get("id"), str):
                        dropped.add(raw["id"])
                    continue
                key = _card_key(component)
                if key is not None:
                    if key in self.drawn:
                        dropped.add(component["id"])
                        continue
                    self.drawn.add(key)
                kept.append(component)
            for component in kept:
                children = component.get("children")
                if isinstance(children, list):
                    component["children"] = [
                        c for c in children if isinstance(c, str) and c not in dropped
                    ]
            if not kept:
                emptied.add(str(update.get("surfaceId")))
                continue
            out.append({**envelope, "updateComponents": {**update, "components": kept}})
        if emptied:
            # A surface whose every component went is not created at all.
            out = [e for e in out if _surface_id(e) not in emptied]
        return out

    def missing(self) -> list[dict[str, Any]]:
        """Server surfaces for the expected cards the model didn't draw."""
        out: list[dict[str, Any]] = []
        for component, card_id in self.expected.values():
            if (component, card_id) in self.drawn:
                continue
            self.drawn.add((component, card_id))
            out.extend(card_surface(component, card_id))
        return out


def _surface_id(envelope: dict[str, Any]) -> str | None:
    for key in ("createSurface", "updateComponents", "updateDataModel", "deleteSurface"):
        body = envelope.get(key)
        if isinstance(body, dict):
            return str(body.get("surfaceId"))
    return None


def card_surface(component: str, card_id: str = "") -> list[dict[str, Any]]:
    """A surface with one domain card as its root."""
    surface_id = f"simo-{uuid.uuid4().hex[:12]}"
    root: dict[str, Any] = {"id": "root", "component": component}
    prop = CARD_ID.get(component)
    if prop is not None:
        root[prop] = card_id
    return [
        {
            "version": A2UI_VERSION,
            "createSurface": {"surfaceId": surface_id, "catalogId": catalog_id()},
        },
        {
            "version": A2UI_VERSION,
            "updateComponents": {"surfaceId": surface_id, "components": [root]},
        },
    ]
