# Live demo-script tests (#98)

These tests play the stage demo script against a running S.I.MO, the way outsiders see it:
an agent over MCP, and a phone call whose caller lines are typed instead of spoken. They
are for rehearsing the demo, for checking a release, and for a loop where the script is
run, what happened is read back, a fix is made and the script is run again.

They are skipped unless `SIMO_LIVE_URL` is set, so `uv run pytest` and CI never run them.
They write to the target's database, call the live Valio API through it and open Gemini
Live sessions.

## Running

```sh
cd api
SIMO_LIVE_URL=https://simo.mankeli.co uv run pytest tests/live -s
```

- `-s` prints each beat: the quotes as S.I.MO has them, each call's captions and tool
  calls, and the session's steps from the dashboard.
- One file or one case: `tests/live/test_demo_script.py`, or
  `tests/live/test_phone_script.py -k "order and fi"`.
- Against the local stack: `SIMO_LIVE_URL=http://localhost`. The phone tests need
  `GEMINI_API_KEY` on that API, and the quotes need recorded or live Valio answers.
- The phone tests open one Gemini Live session per call (six in all). Keep runs few: the
  key has abuse limits.
- Run it after each release to `production`.

## What it covers

| File | Door | Beats |
|---|---|---|
| `test_demo_script.py` | MCP, with the real OAuth flow | `context`, `usual`, `recipe`, `allergen`, `exception`, `unusual`, `update`, `confirm`, `errors`, `audit`, `hidden` |
| `test_phone_script.py` | `/voice/ws` with typed lines, in Finnish and English | `call-order`, `call-allergen`, `call-recipe` |

The MCP script runs its beats in order in one session and reports every failing beat at
the end. Each phone case is a call by a new company.

A typed line skips speech recognition, so mishearing is not tested here;
`scripts/voice_smoke_test.py` speaks its lines.

## Finding a run afterwards

Each run prints its id, `demo-script-<unix time>`. Every request carries it as
`X-Simo-Test-Run`, with the beat as `X-Simo-Test-Case`.

- **Dashboard API:** a company created by a stamped request is a test company and stays off
  the public dashboard. `GET /api/v1/public/orders?test_run=<run id>` lists the run's
  sessions; `/api/v1/public/orders/{session_id}/steps`, `/transcript` and `/events` give
  one session.
- **Application Insights:** the stamps are span and log attributes `simo.test_run` and
  `simo.test_case` (#84). A starting point, not yet tried against the workspace:

  ```kusto
  union AppRequests, AppDependencies, AppTraces
  | where tostring(Properties["simo.test_run"]) == "demo-script-1794685899"
  | project TimeGenerated, Type, Name, case = Properties["simo.test_case"], Properties
  | order by TimeGenerated asc
  ```

## The pieces

- `simo_live.py`: the client. `Run` (run id, stamps, dashboard read-back), `Visitor`
  (demo account, inbox, confirmation page, OAuth consent), `mcp_agent` (the tools over
  `/mcp`) and `play_call` (a typed phone call).
- `agent.py`: tool calls over any MCP session, and reading a quote. It doesn't know where
  the server is, so an offline test can run the same script against fixtures with an
  in-memory session (`tests/test_script_agent.py`, and the replay test of #105).
