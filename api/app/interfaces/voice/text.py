"""Transcript text for the call screen and the audit log.

Gemini Live's output transcription sometimes carries stray markup (a `</td>` and line
breaks between words in the #53 prompt runs, spikes/gemini-live/README.md), so every
transcript is cleaned before it is shown or stored.
"""

import re

# An HTML or XML tag, or an unfinished one at the end of a streamed piece.
_TAG = re.compile(r"</?[A-Za-z][^<>]*>|<[A-Za-z/][^<>]*$")
# Markdown emphasis, headings and code marks; the agent speaks, so it never means them.
_MARKDOWN = re.compile(r"[*_`#]+")
_ENTITIES = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"}
_SPACE = re.compile(r"\s+")


def clean(text: str) -> str:
    """The text without markup, on one line, with single spaces."""
    text = _TAG.sub(" ", text)
    for entity, char in _ENTITIES.items():
        text = text.replace(entity, char)
    text = _MARKDOWN.sub("", text)
    return _SPACE.sub(" ", text).strip()


class Utterance:
    """One side's current utterance, streamed as `transcript` deltas.

    Gemini sends the text in pieces. The pieces are joined raw and cleaned as a whole, so a
    tag split across pieces is still removed, and only the part of the clean text not yet
    sent goes out as the next delta. If cleaning ever changes text already sent, nothing more
    is sent until `close()`, whose final message carries the whole clean text and replaces
    the pieces on the call screen.
    """

    def __init__(self) -> None:
        self.raw = ""
        self.sent = ""
        self.diverged = False

    @property
    def text(self) -> str:
        return clean(self.raw)

    def add(self, piece: str) -> str:
        """Adds a piece; returns the delta to send (may be empty).

        `clean()` strips the ends, so a word break shows up as the leading space of the
        next delta, once the next word arrives.
        """
        self.raw += piece
        current = clean(self.raw)
        if self.diverged or not current.startswith(self.sent):
            self.diverged = True
            return ""
        delta = current[len(self.sent) :]
        self.sent = current
        return delta

    def close(self) -> str:
        """Ends the utterance; returns its whole clean text and starts a new one."""
        text = clean(self.raw)
        self.__init__()
        return text

    def __bool__(self) -> bool:
        return bool(self.raw.strip())


_FI_HINTS = {
    "ja",
    "ei",
    "on",
    "se",
    "että",
    "kiitos",
    "kyllä",
    "joo",
    "moi",
    "hei",
    "mitä",
    "tarvitsen",
    "tarvitsisin",
    "litraa",
    "kiloa",
    "maanantaiksi",
    "huomiseksi",
    "muuta",
    "siinä",
    "kaikki",
    "lähetä",
    "vielä",
    "laatikkoa",
    "pakkausta",
    "minä",
    "meille",
    "olisi",
    "saisi",
    "kanssa",
}
_EN_HINTS = {
    "the",
    "and",
    "is",
    "a",
    "i",
    "need",
    "yes",
    "no",
    "please",
    "send",
    "it",
    "that",
    "for",
    "of",
    "to",
    "my",
    "we",
    "thanks",
    "thank",
    "you",
    "litres",
    "liters",
    "kilos",
    "all",
    "some",
    "would",
    "like",
    "monday",
    "tomorrow",
    "okay",
    "hi",
    "hello",
}
_WORD = re.compile(r"[a-zåäö]+")


def guess_language(text: str) -> str | None:
    """`fi`, `en` or None, from a caller's caption. A rough word count, for the filler line."""
    words = _WORD.findall(text.lower())
    if not words:
        return None
    fi = sum(w in _FI_HINTS for w in words) + sum(any(c in w for c in "äöå") for w in words)
    en = sum(w in _EN_HINTS for w in words)
    if fi == en:
        return None
    return "fi" if fi > en else "en"
