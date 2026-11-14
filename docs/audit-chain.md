# Audit chain format

How each audit event is hashed, so anyone can check the chain: the API (`api/app/services/audit/chain.py`), the dashboard in the browser (`web/src/lib/dashboard/hash.ts`) and a judge with the downloaded JSON. Decided in #41; `technical-plan.md` §8.5 has the why.

Test vectors: [`audit-chain-vectors.json`](audit-chain-vectors.json). Both the Python and the TypeScript tests check them, so a change here must change both implementations and regenerate the vectors.

## Fields

| Field | Format |
|---|---|
| `seq` | Place in the global chain: 1, 2, 3 and so on, with no gaps |
| `at` | UTC, exactly six fractional digits and `Z`: `2026-11-14T10:23:45.123456Z`. The API sends this exact string |
| `type` | An event type, for example `quote_built` (`api/app/schemas/audit.py`) |
| `actor` | Who did it: `buyer`, `agent`, `engine`, `mcp`, `relay`, `confirmation`, `system` and so on |
| `session_id`, `quote_id` | Lowercase UUID with hyphens, or null |
| `payload` | JSON object, the event's detail |
| `text_fi`, `text_en` | The plain-language sentence, or null |
| `payload_hash` | Lowercase hex SHA-256, see below |
| `prev_hash` | `hash` of the event with `seq - 1`. For `seq` 1 it is 64 zeros |
| `session_prev_hash` | `hash` of the previous event in the same session. Null for a session's first event and for events with no session |
| `hash` | Lowercase hex SHA-256, see below |

## `payload_hash`

SHA-256 over the [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) canonical JSON (UTF-8) of this object:

```json
{"payload": <payload>, "text_fi": <text_fi>, "text_en": <text_en>}
```

The sentences are inside, so the text shown on the dashboard can't change without the chain noticing. RFC 8785 sorts keys, drops whitespace and writes numbers the way JavaScript's `JSON.stringify` does, so in a browser a key-sorting `JSON.stringify` gives the same bytes.

## `hash`

SHA-256 over the UTF-8 bytes of these nine values joined with a newline (`\n`), in this order:

```
prev_hash
session_prev_hash
seq
at
type
actor
session_id
quote_id
payload_hash
```

A null value is the empty string, and `seq` is written in decimal. There is no newline at the end.

Example (vector 2), with `\n` written as line breaks. The empty lines are `session_prev_hash` (the session's first event) and `quote_id`:

```
ffeb09fbb7573244dc88b59e8bce75bf206b9db6e3e990daaf108b52209c3050

2
2026-11-14T10:23:45.123456Z
buyer_said
buyer
5b0c7a3e-2f41-4d8e-9a6b-1c2d3e4f5a6b

8b45d52e8ade2f1c24173fecb54d9bc552d9500383a625134ce103813c0dc589
```

## Checking

For each event in `seq` order:

1. `seq` is one more than the previous event's (the first is 1).
2. `prev_hash` is the previous event's `hash` (64 zeros for `seq` 1).
3. `session_prev_hash` is the `hash` of the session's previous event (null for its first).
4. When the payload is there, `payload_hash` matches it. Because the chain covers only `payload_hash`, a payload can be left out or deleted (for example a transcript after the event) and the rest still checks.
5. `hash` matches the nine fields.

One session's events can be checked on their own with steps 3 to 5. Step 2 then applies only where two of them are next to each other in `seq`; the gaps hold other sessions' events.

The API's `GET /api/v1/public/audit/verify` and `scripts/verify_audit_chain.py` run all five steps on the stored rows.
