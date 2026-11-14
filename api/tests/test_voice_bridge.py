"""The relay's tool bridge and transcript text (#52). No database needed."""

import json

import pytest
from mcp.types import CallToolResult, TextContent

from app.agent import AGENT_TOOLS, END_CALL
from app.interfaces.mcp.server import mcp
from app.interfaces.voice import bridge, filler
from app.interfaces.voice.text import Utterance, clean, guess_language
from tests import voice_fakes as fx


def test_inline_refs_resolves_nested_definitions():
    schema = bridge.inline_refs(fx.QUOTE_SCHEMA)
    assert "$defs" not in schema
    line = schema["properties"]["lines"]["items"]
    assert line["properties"]["unit"] == {"type": "string", "enum": ["l", "kg"]}
    assert fx.QUOTE_SCHEMA["properties"]["lines"]["items"] == {"$ref": "#/$defs/Line"}


def test_inline_refs_refuses_a_recursive_schema():
    schema = {"$ref": "#/$defs/A", "$defs": {"A": {"properties": {"a": {"$ref": "#/$defs/A"}}}}}
    with pytest.raises(ValueError, match="recursive"):
        bridge.inline_refs(schema)


async def test_every_mcp_tool_becomes_a_self_contained_declaration():
    tools = await mcp.list_tools()
    declarations = bridge.declarations(tools)
    assert [d.name for d in declarations] == [*AGENT_TOOLS, END_CALL]
    for declaration in declarations:
        text = json.dumps(declaration.parameters_json_schema)
        assert "$ref" not in text and "$defs" not in text, declaration.name
        assert declaration.description
    quote = next(d for d in declarations if d.name == "build_quote").parameters_json_schema
    line = quote["properties"]["lines"]["items"]
    assert "needed_by" in line["properties"]


def test_tool_results_become_function_responses():
    ok = CallToolResult(content=[], structuredContent={"quote_id": "q"}, isError=False)
    failed = CallToolResult(
        content=[TextContent(type="text", text="quote not found")], isError=True
    )
    assert bridge.tool_response(ok) == {"output": {"quote_id": "q"}}
    assert bridge.tool_response(failed) == {"error": "quote not found"}


def test_clean_strips_markup():
    assert clean("Hei <b>Hassu</b>\n Hauki</td>   Oy!") == "Hei Hassu Hauki Oy!"
    assert clean("**Kaksi** pakkausta &amp; `maito`") == "Kaksi pakkausta & maito"
    assert clean("hinta 41,90 € <") == "hinta 41,90 € <"
    assert clean("hinta <br") == "hinta"


def test_utterance_sends_clean_deltas_and_a_whole_final():
    utterance = Utterance()
    assert utterance.add("Hei, <b") == "Hei,"
    assert utterance.add(">Hassu") == " Hassu"
    assert utterance.add(" Hauki</td>\n") == " Hauki"
    assert utterance.add("Oy!") == " Oy!"
    assert utterance.close() == "Hei, Hassu Hauki Oy!"
    assert not utterance


def test_guess_language():
    assert guess_language("Tarvitsen viisi kiloa jauhelihaa maanantaiksi") == "fi"
    assert guess_language("I need five kilos of ground beef for Monday") == "en"
    assert guess_language("Oltermanni") is None


def test_the_filler_clips_exist_for_the_default_voice():
    for lang in filler.TEXT:
        pcm = filler.clip("Aoede", lang)
        assert pcm is not None
        assert 0.5 < len(pcm) / 2 / filler.RATE < 2.5
    assert filler.clip("NoSuchVoice", "fi") is None
