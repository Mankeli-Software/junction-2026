"""Check that the Live model calls build_quote from a Finnish spoken order, blocking and non-blocking.

    uv run function_call.py                          # sync and async, phrases p01 p05 p08
    uv run function_call.py --modes async --scheduling INTERRUPT --delay 4

The tool result is a stub sent after --delay seconds (standing in for the engine).
For each run we record when the call came, its arguments, what the agent said
before and after the result, and whether it kept talking while the call was
pending (the point of asynchronous function calling). Output: out/fc/<time>/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime

from google.genai import types

from common import HERE, LIVE_MODEL, OUT_RATE, load_phrases, make_client, read_wav, resample, write_wav
from live import build_quote_declaration, live_config, run_turn, stub_quote_result

INSTRUCTION = {
    "sync": (
        "Kun soittaja on kertonut tilausrivit, kutsu build_quote kerran kaikilla riveillä. "
        "Kun saat tuloksen, kerro rivit ja kokonaishinta lyhyesti."
    ),
    "async": (
        "Kun soittaja on kertonut tilausrivit, kutsu build_quote kerran kaikilla riveillä. "
        "Tarjouksen laskeminen kestää hetken: sillä aikaa kerro soittajalle lyhyesti, että tarkistat "
        "tuotteet, ja toista tilausrivit. Kun saat tuloksen, kerro kokonaishinta lyhyesti."
    ),
}


def split_output(res, response_at: float | None) -> tuple[str, str]:
    if response_at is None:
        return "".join(t for _, t in res.output_segments), ""
    before = "".join(t for at, t in res.output_segments if at < response_at)
    after = "".join(t for at, t in res.output_segments if at >= response_at)
    return before, after


async def main_async(args) -> None:
    client = make_client()
    phrases = {p.id: p for p in load_phrases(include_extra=True)}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = HERE / "out" / "fc" / stamp
    report = []

    for mode in args.modes:
        non_blocking = mode == "async"
        config = live_config(
            voice=args.voice,
            tools=[build_quote_declaration(non_blocking=non_blocking)],
            extra_instruction=INSTRUCTION[mode],
        )

        async def on_tool_call(state, fc: types.FunctionCall, non_blocking=non_blocking) -> None:
            await asyncio.sleep(args.delay)
            resp = types.FunctionResponse(id=fc.id, name=fc.name, response=stub_quote_result(fc.args or {}))
            if non_blocking:
                resp.scheduling = types.FunctionResponseScheduling[args.scheduling]
            await state.respond(resp)

        for pid in args.only:
            p = phrases[pid]
            samples, rate = read_wav(HERE / args.audio_dir / f"{pid}.wav")
            res = await run_turn(
                client, args.model, config, resample(samples, rate, 16_000), on_tool_call=on_tool_call
            )
            response_at = res.tool_responses[0]["at"] if res.tool_responses else None
            before, after = split_output(res, response_at)
            row = {
                "mode": mode,
                "id": pid,
                "expected": p.text,
                "heard": res.input_text.strip(),
                "tool_calls": res.tool_calls,
                "first_tool_call_s": res.first_tool_call,
                "first_audio_s": res.first_audio,
                "response_sent_s": response_at,
                "said_before_result": before.strip(),
                "said_after_result": after.strip(),
                "audio_while_pending_s": round(res.audio_while_tool_pending_bytes / 2 / OUT_RATE, 2),
                "interrupted": res.interrupted,
                "timed_out": res.timed_out,
                "error": res.error,
                "events": res.summary()["events"],
            }
            report.append(row)
            if res.audio_out:
                write_wav(out_dir / f"{mode}-{pid}.wav", bytes(res.audio_out), OUT_RATE)
            print(f"[{mode}] {pid}: calls {len(res.tool_calls)}, first call {row['first_tool_call_s']} s, "
                  f"audio while pending {row['audio_while_pending_s']} s"
                  + (f", ERROR {res.error}" if res.error else "") + (", TIMEOUT" if res.timed_out else ""))
            for c in res.tool_calls:
                print(f"    args: {json.dumps(c['args'], ensure_ascii=False)}")
            print(f"    before result: {row['said_before_result']}")
            print(f"    after result : {row['said_after_result']}")
            await asyncio.sleep(1.0)

    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {"model": args.model, "delay_s": args.delay, "scheduling": args.scheduling, "time": stamp}
    (out_dir / "results.json").write_text(json.dumps({"meta": meta, "rows": report}, ensure_ascii=False, indent=2))
    print(f"Saved to {out_dir.relative_to(HERE)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=LIVE_MODEL)
    ap.add_argument("--audio-dir", default="audio/tts")
    ap.add_argument("--only", nargs="*", default=["p01", "p05", "p08"])
    ap.add_argument("--modes", nargs="*", default=["sync", "async"], choices=["sync", "async"])
    ap.add_argument("--delay", type=float, default=3.0, help="seconds before the stub result is sent")
    ap.add_argument("--scheduling", default="WHEN_IDLE", choices=["INTERRUPT", "WHEN_IDLE", "SILENT"])
    ap.add_argument("--voice", default=None)
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
