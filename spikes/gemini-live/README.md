# Gemini Live spike (#51)

Can a 3.x Gemini Live model, used through the Gemini API with an AI Studio key (not Vertex), take Finnish food-service orders by voice, answer fast enough, and call a function? This folder holds the scripts to check that, and the results (`technical-plan.md` §7.1, §13).

This is throwaway spike code, kept so the checks can be rerun (for example with your own voice). The real relay is #52, the real prompt is #53.

## Setup

- Python via [`uv`](https://docs.astral.sh/uv/). Dependencies are in `pyproject.toml`; `uv run` installs them on first use.
- An AI Studio API key in `GEMINI_API_KEY`, or in `~/.config/junction-2026/gemini.env` as a line `GEMINI_API_KEY=...`. The scripts never print the key. Don't commit it.
- Everything the scripts write goes to `audio/`, `out/` and `recordings/`, which are git-ignored. **Never commit recordings of a real voice.**

## Steps

All commands run from this folder.

1. **Check which models the key can use.**
   `uv run check_models.py`
2. **Make the test audio.** `phrases.fi.json` holds ten Finnish kitchen orders with real Valio product names (from `data/recipe-product-map.json`), the other acceptable spellings of each (digits, units) and the key terms that must come through. Gemini TTS speaks them; the script resamples to 16 kHz 16-bit mono in numpy (no ffmpeg) and trims silence.
   `uv run tts.py` writes `audio/tts/<id>.wav` (add `--voice`, `--force`, `--only p01 p02`).
3. **Run the phrases through Live.** One fresh session per phrase, input and output transcription on, a short Finnish S.I.MO system instruction. Audio is sent in 40 ms chunks paced in real time, followed by silence as a real microphone would, so the server's voice activity detection decides when the caller stopped.
   - `uv run run_live.py` (baseline)
   - `uv run run_live.py --vocab --label vocab` (input transcription with `custom_vocabulary` of product names)
   - `uv run run_live.py --lang fi-FI --label lang` (`language_codes` hint)
   - `uv run run_live.py --tools --label tools` (also declares `build_quote` and scores the arguments the model passes)
   - `--extra` adds one English phrase, to check that the agent follows the caller's language.

   Each run writes `out/runs/<time>-<label>/results.md` (table), `results.json` (everything, with an event timeline) and the agent's replies as WAVs.
4. **Function calls, blocking and non-blocking.**
   `uv run function_call.py` runs p01, p05 and p08 with a blocking `build_quote`, then with `behavior: NON_BLOCKING`. The stub result comes back after `--delay` seconds (default 3) with `--scheduling` (default `WHEN_IDLE`). It records the arguments, what the agent said before and after the result, and how much audio it produced while the call was pending.
5. **Voices.**
   `uv run voices.py --asr-model <a Flash text model>` has S.I.MO say one Finnish reply in several voices (`--voices Kore Aoede ...`), saves the WAVs to `out/voices/` for listening, and transcribes each back with a text model as a rough intelligibility check.
6. **Your own voice** (the real accuracy check; TTS audio is cleaner than real speech).
   `uv run --extra mic record_mic.py --speaker <name>`
   For each phrase: read it, press Enter, say it as you would on the phone, press Enter. The audio goes to `recordings/<name>/` (git-ignored) and the script then runs `run_live.py` on it with the label `mic-<name>`. `--list-devices` and `--device` pick the microphone; `--only p03` re-records one phrase.
   - **WSL2**: `sounddevice` needs PortAudio (`sudo apt install libportaudio2`), and the microphone reaches Linux through WSLg's PulseAudio server (`/mnt/wslg/PulseServer`). If no input device shows up, check that WSLg is enabled and Windows allows microphone access for desktop apps.
   - **Alternative**: run the same script on the Windows side. Install `uv` for Windows, clone the repo, set `$env:GEMINI_API_KEY`, and run the command above in PowerShell from `spikes\gemini-live`.

### What is measured

- **WER**: word error rate of Live's input transcription against the expected text, after lowercasing and removing punctuation and hyphens. The best match over the spoken form and the written variants counts, so "kaksi" and "2" are both right.
- **Key terms**: product names, compound words, numbers and units that must come through; each is checked as a substring of the transcript, also with spaces removed, so "sulate juusto" still counts for "sulatejuusto". This matters more than WER: the engine's search tolerates typos (`technical-plan.md` §5.3), but a wrong number or product does not.
- **Latency**: seconds from the moment the last chunk of speech was sent to the first audio chunk back, and to the first input transcript. It includes the server's end-of-speech detection and the network round trip, so it is what the caller feels on a good connection. The browser leg and playback buffering of the real relay come on top.

## Sources (checked 2026-11-14)

- Models: https://aistudio.google.com/docs/models (formerly ai.google.dev/gemini-api/docs/models). Live models listed: `gemini-3.8-live` (new, default for voice agents), `gemini-3.8-live-extended-thinking`, `gemini-3.1-flash-live-preview` (legacy), `gemini-2.5-flash-native-audio-preview-12-2025`. TTS: `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`.
- Live capabilities: https://aistudio.google.com/docs/live-api/capabilities. Input 16-bit little-endian PCM at 16 kHz (`audio/pcm;rate=16000`), output 24 kHz. Finnish (`fi`) is in the supported-language table. Native audio models choose the language themselves and take no language code; a language can be forced in the system instruction. Input transcription accepts a `custom_vocabulary` (up to 1,000 terms, best results up to about 100). `gemini-3.8-live` takes no `thinkingLevel`, always has proactive audio, and has no affective dialog.
- Live tools: https://aistudio.google.com/docs/live-api/tools. `gemini-3.8-live` supports synchronous and asynchronous function calling; `gemini-3.8-live-extended-thinking` asynchronous only; `gemini-3.1-flash-live-preview` synchronous only. Asynchronous calls use `behavior: NON_BLOCKING` on the declaration and `scheduling` (`INTERRUPT`, `WHEN_IDLE`, `SILENT`) on the response.
- Speech generation: https://aistudio.google.com/docs/speech-generation. 30 prebuilt voices (the same names work for Live). Finnish is supported by `gemini-3.8-flash-tts` but not by `gemini-3.8-flash-lite-tts`. Output is 24 kHz 16-bit mono.
- SDK: `google-genai` 3.3.0 (PyPI, 2026-11-12).

## Results

**Not run yet: waiting for the API key.** The scripts are built and checked offline (syntax, `--help` of each script, the setup message they send, and the send/receive/tool-call logic against a fake session). Only numbers actually measured will go here.
