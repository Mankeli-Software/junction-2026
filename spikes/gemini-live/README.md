# Gemini Live spike (#51)

Can a 3.x Gemini Live model, used through the Gemini API with an AI Studio key (not Vertex), take Finnish food-service orders by voice, answer fast enough, and call a function? This folder holds the scripts to check that, and the results (`technical-plan.md` §7.1, §13).

This is throwaway spike code, kept so the checks can be rerun (for example with your own voice). The real relay is #52, the real prompt is #53.

## Setup

- Python via [`uv`](https://docs.astral.sh/uv/). Dependencies are in `pyproject.toml`; `uv run` installs them on first use.
- An AI Studio API key. The scripts take the first non-empty `GEMINI_API_KEY` from: the environment variable; a `.env` in this folder or any parent (normally the repo root's git-ignored `.env`, see `.env.example`; from a worktree under `.claude/worktrees/` the walk reaches the main checkout's `.env`); `~/.config/junction-2026/gemini.env`. The scripts never print the key. Don't commit it.
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

## Results (2026-11-14, TTS audio)

Measured from WSL2 on a home connection, one run of each step: 46 Live sessions in total (one smoke test, 10 plain, 10 with vocabulary, 10 with tools, 1 English, 9 function-call sessions, 5 voices). Every number below comes from one run, so treat small differences as noise.

**The caller audio is Gemini TTS (voice Achird), which is cleaner than real speech: these accuracy figures are an upper bound.** The real check is the same run in a human voice (`record_mic.py`, step 6), which is still to do.

### Model

`gemini-3.8-live` through the Gemini API with an AI Studio key, API version `v1beta`. With the SDK's default `v1`, `models.get` returns 404 and `models.list` doesn't show any Live or TTS model. On `v1beta` the key sees `gemini-3.8-live`, `gemini-3.8-live-extended-thinking`, `gemini-3.1-flash-live-preview`, the 2.5 native-audio previews, `gemini-3.5-transcribe-live` and `gemini-3.5-live-translate-preview`. I chose `gemini-3.8-live` because it is the documented default for voice agents and the only 3.x Live model with both blocking and non-blocking function calls. It worked first time; the other models were not tried. TTS: `gemini-3.8-flash-tts` through `client.interactions`.

### Finnish accuracy (10 phrases)

WER is against the expected text (best over the written variants). "Terms" is the key-term check. "Plain" is input transcription with default settings. "Vocab" adds `custom_vocabulary` with 22 product names and compound words (`phrases.fi.json`).

| id | plain WER | plain terms | vocab WER | vocab terms | plain: what was heard (wrong parts) |
|---|---|---|---|---|---|
| p01 | 0.00 | 6/6 | 0.10 | 6/6 | |
| p02 | 0.44 | 5/6 | 0.11 | 6/6 | "Novabox valioruokakermaa" |
| p03 | 0.25 | 5/6 | 0.12 | 6/6 | "Oldermannin" |
| p04 | 0.12 | 6/6 | 0.12 | 6/6 | (only "2 kg" for "kahden kilon") |
| p05 | 0.00 | 7/7 | 0.00 | 7/7 | |
| p06 | 0.11 | 5/5 | 0.00 | 5/5 | |
| p07 | 0.11 | 6/6 | 0.00 | 6/6 | |
| p08 | 0.54 | 4/6 | 0.23 | 6/6 | "12 viipaleen kinkkua" for "kaksitoista vispikermaa", "violatoren juustoa" |
| p09 | 0.00 | 6/6 | 0.00 | 6/6 | Oddlygood Barista heard right |
| p10 | 0.29 | 6/7 | 0.07 | 7/7 | "salkkumakkaraa viikolla" for "sama kuin viime viikolla" |
| **all** | mean 0.19 | **56/61** | mean 0.08 | **61/61** | |

The vocab WER that remains comes from formatting, not from mishearing: a dropped "Hei", "2 kg" for "kahden kilon", and "mitä" for "niitä".

- **`custom_vocabulary` is the biggest win of the spike.** It took key terms from 56/61 to 61/61 and mean WER from 0.19 to 0.08, with no latency cost.
- **It also fixed what the model understood, not only the caption.** Without vocabulary, the agent's spoken read-back of p08 was "12 pakettia viipaleen kinkkua", the wrong product. With vocabulary the read-back was correct ("kaksitoista kahden desilitran vispikermaa ja kaksi puolentoista kilon Viola tuorejuustoa").
- **The model hears better than the plain caption suggests.** Without vocabulary, the caption said "Oldermannin" and "Novabox", but the agent still said "Oltermanni" in its reply.
- **Numbers came through in every phrase**, both as words and as digits ("kaksi ja puoli" became "2,5").

### Latency

All figures are from the moment the last speech chunk was sent. They include the server's end-of-speech detection with its default silence setting.

| | median | worst |
|---|---|---|
| First audio back, plain (10) | 1.07 s | 1.42 s |
| First audio back, vocab (10) | 1.06 s | 1.33 s |
| First input transcript (both runs) | 0.99 s | 1.09 s |
| build_quote call arrives (tools run, 10) | 0.99 s | 1.49 s |
| First audio with build_quote, stub answered at once (10) | 1.81 s | 2.27 s |
| First audio after a text prompt, voices run (5) | 0.67 s | 0.80 s |
| Opening the session (connect) | 0.38 to 0.41 s | |

- **About 1 s is spent before anything comes back.** The reply, the input transcript and the tool call all arrive about 1 s after the caller stops. Most of that is probably end-of-speech detection; the text-prompt case, which has none, starts in 0.67 s. The default `silence_duration_ms` was not tuned.
- **No interim input transcripts arrived** (`interim_input_transcription`). The caller's caption appears in one piece, about 1 s after they stop talking.
- **The model makes a tool call silently and ends the turn.** It then needs about 0.65 s after the tool response to start speaking. So time to first audio is about 1 s, plus the engine time, plus 0.65 s.

### Function calls

The declaration is a simplified `build_quote(lines: [{product_query, quantity, unit}], delivery_day)`. The stub result has prices and a `say` hint.

- **Calls and arguments (tools run, vocab on): `build_quote` was called in 10/10 phrases.** The arguments were sensible Finnish, for example:
  - `{"delivery_day": "torstai", "lines": [{"quantity": 2, "unit": "laatikko", "product_query": "Valio Eila laktoositon kevytmaitojuoma"}]}`
  - p05 and p08 were split correctly into two lines each.
  - Quantities were always numbers, including 2.5.
- **Key terms in the arguments: 55/61.** The misses come from the schema, not from hearing:
  - The pack size has no field. It was dropped in p04 ("kahden kilon") and p08 ("2 dl", "1,5 kg"), and moved into `product_query` in p03 ("900g") and p07 ("2,5 kg").
  - Product and unit words came both in base form ("litra", "kevytmaitojuoma") and inflected ("litraa", "sankoa", "laktoositonta kevytmaitojuomaa").
- **The spoken follow-up** read back the lines, the stub's total ("Yhteensä 9,70 euroa") and asked about the confirmation link. In one reply it offered the link "sähköpostiisi" (by email), which is wrong.
- **Blocking calls (`function_call.py`, 3 s engine delay):**
  - The model called `build_quote` in 2/3 sessions. In p08 it read the lines back and asked "Tuleeko muuta?" instead of calling.
  - It said nothing during the 3 s wait. Speech started 0.7 s after the result.
- **Non-blocking calls (`behavior: NON_BLOCKING`, 3 s delay):**
  - The model called `build_quote` in 6/6 sessions (3 with `WHEN_IDLE`, 3 with `INTERRUPT`).
  - **In all six it still said nothing while the call was pending: 0.0 s of audio between the call and the result.** That happened even though the system instruction asked it to tell the caller it was checking. It then spoke 0.6 to 0.9 s after the result.
  - `WHEN_IDLE` and `INTERRUPT` behaved the same, because there was nothing to interrupt.
  - `interaction_status` never arrived; `turn_complete` came right after the tool call.
  - In this setup, asynchronous calling gave no "keeps talking" benefit.

### Voice

S.I.MO said the same Finnish confirmation sentence in five voices (`voices.py`):
- All five were intelligible. Transcribing them back with `gemini-3.8-flash` gave the sentence word for word, apart from "10" for "kymmenen".
- First audio came 0.62 to 0.80 s after the text prompt.
- I could not listen to the clips. As a hint only, `gemini-3.8-flash` rated how native each clip sounded:

| Voice | Model rating | Model's comment |
|---|---|---|
| Aoede | 5/5 | Most natural |
| Kore | 4.5/5 | |
| Achird | 4.5/5 | |
| Charon | 4/5 | Stiff |
| Sulafat | 3.5/5 | Melodramatic intonation |

**Proposal: Aoede, with Kore as the alternative, to be confirmed by a Finnish speaker listening to `out/voices/`.**

### English fallback

**Not needed for Finnish.** Finnish recognition with vocabulary was 61/61 on key terms (TTS audio).

The opposite direction failed once: an English caller (en01, transcribed perfectly) got a Finnish reply. The system instruction said, in Finnish, "speak Finnish unless the caller speaks another language". That is a prompt problem for #53, not a recognition problem.

### Surprises

- The Live and TTS models exist only on `v1beta` (see Model).
- `custom_vocabulary` made the difference between "mostly right" and "all key terms right" (see Finnish accuracy).
- Asynchronous function calling gave no filler speech (see Function calls).
- No interim input transcripts (see Latency).
- After the tool response, `generation_complete` came 1.7 to 2.5 s later, but `turn_complete` came 5.9 to 14.3 s later. That is about the reply's audio length plus 0.7 s: the server seems to hold `turn_complete` until the reply would have finished playing.

### Implications for #52 (relay)

- Create the client with `http_options={"api_version": "v1beta"}`.
- Always pass `input_audio_transcription.custom_vocabulary`. Fill it from the catalogue: brand names (Eila, Oltermanni, Koskenlaskija, Viola, Polar, Oddlygood, novobox) and the compound words of the products in play. The docs advise at most about 100 terms.
- Plan for silence while `build_quote` runs: about 1 s plus the engine time plus 0.65 s before the agent speaks. Non-blocking calls did not fill the gap here. Options:
  - keep the engine fast;
  - have the relay play a short local filler ("Hetkinen, tarkistan...") when a call takes longer than about 1 s;
  - try a prompt that makes the model speak before it calls (not tested).
- Don't wait for `turn_complete` to free anything up: it comes about a full playback length late. Use `generation_complete` and the tool-call messages instead.
- Expect the buyer's caption only at the end of each utterance. The call screen should not promise word-by-word captions.
- Worth a quick test in #52: a lower `silence_duration_ms`, to cut the roughly 1 s end-of-speech delay.

### Implications for #53 (prompt) and the tool schema

- **Language:** say in the prompt (in English, or both languages) that S.I.MO must answer in the caller's language. Today's Finnish line did not make it answer an English caller in English.
- **Confirmation link:** say plainly that it comes as a text message to the phone after the call. The agent improvised "sähköpostiisi" (email) once.
- **When to call `build_quote`:** be explicit. In one of three blocking sessions the agent kept collecting lines instead of calling.
- **Pack size:** give `build_quote` lines a pack-size field (for example `pack_size: "2 dl"`), or tell the model to keep the pack size in `product_query`. Today it is sometimes dropped, which loses the difference between a 2 dl and a 1 l cream.
- **Inflected Finnish:** expect `product_query` and `unit` in inflected forms ("laktoositonta kevytmaitojuomaa", "litraa", "sankoa"). Search and unit mapping must handle them, or the prompt must ask for base forms.

## Prompt calls (#53, 2026-11-14)

`prompt_calls.py` runs scripted calls against the real S.I.MO system prompt (`api/app/agent/prompt.py`). It checks the #53 checklist before the relay (#52) and the MCP server (#43) exist.

- **Prompt and tools.** The system prompt comes from `build_system_prompt(context, channel, today=...)` for a demo account: Hassu Hauki Oy, a lactose-free kitchen with usual butter. The function declarations are the contract's request models (`api/app/schemas/tools.py`, listed in `AGENT_TOOLS`), turned into JSON Schema with the `$ref`s inlined. On the phone the relay's local `end_call` is added. Each tool description is one line from vision §8; the real descriptions will come from the MCP server.
- **Tool answers.** The stub engine (`api/app/engine/stub.py`) answers `build_quote` and `update_quote`, wrapped as a `QuoteResponse` without the trace. The harness forces the stub's paths per call:
  - the first quote in the clarification call takes the "unclear" path;
  - a cheese line in the chat call takes the "reject" path;
  - the Finnish and English calls get an `ALLERGEN_NO_LISTING` flag.

  `request_confirmation` gets a fake `ConfirmationRequestResponse` (`held` on the phone). Arguments are checked against the contract models, so a bad argument goes back to the model as an error, as MCP would return it.
- **Phone calls** run on `gemini-3.8-live` (`v1beta`, voice Aoede), one Live session per call.
  - The relay's first turn, `[call connected]`, goes as realtime text, so S.I.MO greets first.
  - Caller turns go as realtime text. With `--audio` they are Gemini TTS speech (voice Achird), paced in real time with trailing silence.
  - The next caller turn waits for `turn_complete`, after any tool response has been answered.
- **The chat call** runs on `gemini-3.8-flash` with `generate_content` and manual function calling, as the webshop chat would. It opens no Live session.
- **Output.** Each run writes `out/prompt_calls/<time>/results.md` (a checklist table and the transcript for each call) and `results.json`. Each Live session it opens is logged in `out/prompt_calls/sessions.log`. A 429 stops the run.

```sh
uv run prompt_calls.py                            # all four calls, caller turns as text
uv run prompt_calls.py --only fi_clarify          # one call
uv run prompt_calls.py --audio --only fi_milk     # caller turns spoken (TTS, cached in audio/prompt_calls/)
uv run prompt_calls.py --recheck out/prompt_calls/<time>   # score a saved run again, no API calls
uv run prompt_calls.py --dry-run                  # print the prompt and the declarations
```

The script imports from `../../api`. That is why `pydantic`, `pydantic-settings` and `pyyaml` are in this folder's `pyproject.toml`.

### The calls

| id | Channel | Caller | What it checks |
|---|---|---|---|
| `fi_milk` | phone | Finnish: 100 l Arki-kevytmaito for Monday, then 20 one-litre cartons for Tuesday, "siinä kaikki", "joo, lähetä se" | Greeting, two lines collected, the `build_quote` trigger, pack size, allergen notice, link after a yes, how the link arrives, `end_call` |
| `en_order` | phone | English caller on a Finnish account: 200 l milk, "my usual butter", "what would that come to?" (the price trigger), "where does the link go?" (not a yes), then "yes, please send it" | Replies in English, the usual item's product id, the price as a trigger, no link before the yes |
| `fi_clarify` | phone | Finnish: 50 l "maitoa" for tomorrow, "ei muuta", "kevytmaitoa", "kyllä kiitos" | The engine's `needs_clarification`: one question with at most two options, then `update_quote` with the chosen `product_id` |
| `chat_reject` | web_chat | Finnish: milk and Oltermanni cheese for Friday; the cheese is rejected; "joo, ilman juustoa", "lähetä vahvistus" | Written style, a rejection said and moved on from, `update_quote` without the line, the chat link wording |

The automatic checks are simple on purpose: substring and word-list checks on the transcript, plus tool names, turn numbers and arguments. I also read every transcript. In the question check, "2 = read by hand" turned out to be one question across two sentences each time ("Mitä maitoa tarkoitat? Valio Arki kevytmaitoa vai täysmaitoa?").

### Results

23 Live sessions in total (8 rounds of phone calls and 1 audio run), plus 8 chat calls on the text model. Every run is under `out/prompt_calls/` (git-ignored). The table lists what the checks and the reading found for each prompt version.

| Round | Prompt | Calls | Failures, and the fix in the next version |
|---|---|---|---|
| 1 | .1 | fi_milk | Made up `product_id` "400812" for both milk lines. Fix: never make up an id. |
| 2 | .2 | all 4 | fi_milk: reused the usual butter's id for the milk and gave no `package_word` for "purkki". en_order: asked "Is that all?" and called `build_quote` without waiting. Fix: `product_id` only for a usual item or a picked option; always set `package_word`; wait after "anything else?"; say goodbye and hang up right after the link. |
| 3 | .3 | all 4 | None. |
| 4 | .3 | all 4 | en_order: on "what would that come to?" it read back the quote and asked "Shall I send the confirmation link?", **then sent the link and hung up without waiting for an answer**. Fix: end the turn after any question, and call `request_confirmation` only in the next turn, after the caller's yes. |
| 5 | .4 | all 4 | fi_clarify: asked "which milk?" itself, called `search_products` and quoted with the id the caller picked, so the engine's clarification never ran. Fix: don't ask the caller to choose between products; the engine asks. |
| 6 | .5 | all 4 | None. The chat call offered to "leave a callback request", which no tool does. Fix: don't promise what no tool does. |
| 7 | .6 | all 4 | fi_milk: "kaksikymmentä litran purkkia" became `text` "Arki-kevytmaito", so the 1 l pack size was lost. Fix: a size on a package word goes into `text`, with an example on another product. |
| 8 | .7 | all 4 | None. |
| audio | .7 | fi_milk | None (see below). |

**Final round (prompt `2026-11-14.7`) against the #53 checklist:**

| Checklist item | fi_milk | en_order | fi_clarify | chat_reject |
|---|---|---|---|---|
| Greets by company name, says it is S.I.MO, an AI helper | pass | pass (in Finnish, before the caller spoke) | pass | pass |
| All lines collected, then one `build_quote` at the trigger | pass ("siinä kaikki") | pass (asked for the price) | pass ("ei muuta") | pass |
| One clarification per turn, at most two options | pass | pass | pass | pass |
| Top pick, at most one alternative | pass | pass | pass | pass |
| No-allergen-listing notice once, at the end of the read-back | pass | pass | n/a (no flag) | n/a (no flag) |
| Never says the order is placed | pass | pass | pass | pass ("Tilaus on valmis vahvistettavaksi") |
| Asks about the link, `request_confirmation` only after a clear yes | pass | pass ("where does the link go?" got an answer, no link) | pass | pass |
| Link comes to the phone after hanging up (phone) or to the phone (chat); no email or SMS | pass | pass | pass | pass |
| A decision that can't be overridden: said, moved on | n/a | n/a | n/a | pass (the cheese, then `update_quote` without it) |
| Answers in the caller's language | pass | pass (English from the first English turn) | pass | pass |
| Pack size in `text`, base forms | pass ("Valio Arki kevytmaito 1 l", "purkki") | pass | pass | pass |
| Spoken style on the phone, written style in the chat | pass | pass | pass | pass (a short list of lines in the first reply) |
| `end_call` after the link is agreed | pass | pass | pass | n/a |

Only the unit tests cover the `call_language` line (`fi`, `en`); no call forced a language.

**Audio run** (`--audio --only fi_milk`, prompt .7). It passed every check.
- Live's input caption got the first three turns right but misheard the last: "Joo, lähetä se." became "Ja, vad heter du?" (Swedish for "yes, what's your name?").
- The agent answered "Nimeni on S.I.MO", then sent the link and hung up. The model took a yes from the audio itself, which was right here, but the caption shows how easily a short Finnish answer is misheard.
- The run passed no `custom_vocabulary`; the relay should pass one (see the #51 results).
- This time the agent left out the goodbye before `end_call`.

### What stays open

- **The link sent without an answer (round 4) is the worst failure seen.** It happened once in 23 sessions and not again after the fix, but a prompt can't rule it out. The relay (#52) or the service should guard against it: refuse `request_confirmation` unless the buyer has spoken since the latest quote, and return an error the model can pass on ("I'll wait for your answer").
- The model sometimes adds "1 l" to a line where the caller gave no pack size ("Arki-kevytmaitoa" became "Valio Arki kevytmaito 1 l"); here "samaa maitoa" in the next line made that more likely. The engine should treat a pack size in `text` as a preference, not a hard filter.
- The greeting comes in the account language before the caller speaks, so an English caller on a Finnish account hears Finnish first. That follows `call-screen.md` §2.3.
- The stub prices every line as milk, so the English call's read-back sometimes said both lines were milk. That comes from the stub, not the prompt.
- Text mode shows 4 to 7 s per turn because `turn_complete` arrives when the reply would have finished playing (#51 Surprises), not because the model is slow.
