# Home Connect device control from the laptop

Provides a CLI to authenticate with the Home Connect API and control the robot vacuum
(start / stop cleaning, read status) directly from the laptop.

## How it works

1. **OAuth2 authorization-code flow** — you open an authorization URL in the browser,
   log in with your Home Connect account, and paste the returned `code` back into the
   CLI. The token (access + refresh) is stored in a local `.token.json` (gitignored).
2. **API client** — `HomeConnectClient` calls the API with the stored token and
   auto-refreshes it on `401` responses.

See `hcsdk-production.yaml` for the authoritative endpoint definitions.

## Commands

| Command | Endpoint(s) used | Purpose |
| --- | --- | --- |
| `login` | `/security/oauth/authorize`, `/security/oauth/token` | Authenticate and store token |
| `appliances` | `GET /homeappliances` | List paired appliances (`haId`) |
| `status` | `GET /homeappliances/{haId}/status` | Show live status values |
| `programs` | `GET /homeappliances/{haId}/programs/available` | List available programs |
| `start` | `PUT /homeappliances/{haId}/programs/active` | Start cleaning (`CleanAll` program) |
| `stop` | `DELETE /homeappliances/{haId}/programs/active` | Stop the active program |
| `resume` | `PUT /homeappliances/{haId}/commands/BSH.Common.Command.ResumeProgram` | Resume (unpause) the active program |
| `dock` | `PUT /homeappliances/{haId}/programs/active` | Send the robot back to base (`GoHome` program) |
| `settings` | `GET /homeappliances/{haId}/settings` | List device settings (`Settings`) |
| `maps` | `GET /homeappliances/{haId}/map/maps` | List robot maps (`Map`) |
| `mapinfo --map-id M [--field F]` | `GET .../map/maps/{M}[/...]` | Map data JSON: occupancyGrid, layout, cleaningStatus, objects, rooms, zones (`Map`) |
| `robot` | `GET /homeappliances/{haId}/map/robot/position` | Robot position (`Map`) |
| `summaries` | `GET /homeappliances/{haId}/map/cleaningSummary` | Cleaning summaries (`Map`) |
| `smart-empty` | `GET /homeappliances/{haId}/programs/active` | Smart Emptying: is emptying the dust box justified for the current session? (`AI layer`) |
| `watch [--interval I] [--timeout T]` | polls `GET /homeappliances/{haId}/status` | Smart Emptying (live): flag a false empty the moment the robot docks (`AI layer`) |
| `coverage [--map-id M] [--json] [--ai]` | `GET .../map/maps/{M}/occupancyGrid`, `.../cleaningStatus`, `.../robot/position` + LLM (`--ai`) | Coverage analysis + fake-cleaning detection from the map; human summary by default, raw JSON with `--json`, natural-language verdict with `--ai` (`AI layer`) |
| `obstacles [--auto [--yes]]` | same map endpoints as `coverage` + device control on recovery | Obstacle-loop detection; `--auto` recovers the robot (stop → GoHome → wait dock → restart) (`AI layer`) |

## Setup

1. **Register an application** in the Home Connect Developer Portal:
   - To experiment with the real API, you will have to create a new application.
     Host: `https://api.home-connect.com`.
   - To get started, visit the Home Connect Developer Portal
     (https://developer.home-connect.com) and register an account. To start testing on a
     real appliance, you should register an application first.
   - Note the generated `client_id` / `client_secret` and the allowed redirect URI.
2. Create `.env` with your Home Connect developer credentials
   (`HOME_CONNECT_CLIENT_ID`, `HOME_CONNECT_CLIENT_SECRET`).
3. Install deps: `pip install -r requirements.txt`.
4. Log in: `python -m src.cli login`.
   - For your application to interact with home appliances it needs to get authorized by
     the API. When prompted, log in with your Home Connect Account and grant access.

## AI layer (natural-language control)

The `chat` command wires an LLM into the device control via `src/ai/`. Two providers are
supported (selected with `AI_MODEL_PROVIDER` in `.env`):

- `openai` (default) — the **Bosch on-prem model** (OpenAI-compatible, same one opencode uses).
- `anthropic` — **Claude** via `ANTHROPIC_API_KEY` (`AI_CLAUDE_BASE_URL`, `AI_CLAUDE_MODEL`).

```bash
python -m src.cli chat "start cleaning"
python -m src.cli chat "stop cleaning"
python -m src.cli chat "what is the battery level?"
```

The agent is **state-aware** (`VacuumAgent` in `src/ai/agent.py`): it reads the live
`OperationState` before acting and adapts instead of crashing:

- `Run` / `DelayedStart` → "already cleaning", no duplicate start is sent.
- `Pause` → a `start` request is turned into `ResumeProgram` (resumes instead of restarting).
- `Ready` / `Finished` / `Inactive` → `start`/`stop` are sent normally.
- API errors like `409 SDK.Error.WrongOperationState` are translated into a short,
  actionable message that names the current state (no raw traceback in your terminal).

Verified on the real BCRD2W: `chat "start cleaning"` works from `Ready` (off the dock),
and is a harmless no-op while the robot is already running.

### Smart Emptying (`chat "..."` action `empty`, or `smart-empty`)

Observed bug: the station empties the dust box on every return to base, even when the
robot barely cleaned. The AI layer applies a policy — an empty is only considered
justified when the robot cleaned for at least **2 minutes**
(`AI_MIN_CLEAN_SECONDS`, default `120`):

```bash
python -m src.cli smart-empty                          # verdict for current session
python -m src.cli chat "should I empty the dust box?"  # same policy through the model
```

The API currently exposes no direct empty trigger, so this is a decision/reporting
layer (see `docs/ai-features.md`).

- `src/ai/llm.py` — chat client for the OpenAI-compatible Bosch endpoint or the Anthropic
  API (Claude). Provider chosen via `AI_MODEL_PROVIDER` (default `openai`).
- `src/ai/agent.py` — `VacuumAgent`: puts the current device status in the prompt, asks
  the model for a structured JSON decision, then executes start/stop via the same
  `HomeConnectClient` the CLI uses.
- Configure the model with `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` (Bosch) or
  `ANTHROPIC_API_KEY`, `AI_CLAUDE_MODEL` (Claude) in `.env` (never commit `.env`).
- The model is a reasoning model — leave enough `max_tokens` or the reply may be empty.

## Fast start from the terminal (no opencode)

The `Makefile` in the repo root wraps the CLI. Run from the repo root, or from anywhere
with `make -C ~/Code/dust-to-data-hackathon-26 <target>`. `make help` lists all targets.

### All `make` commands

| make command | What it does |
| --- | --- |
| `make login` | One-time OAuth login (stores token in `.token.json`) |
| `make appliances` | List paired appliances |
| `make status` | Live status (state, battery) |
| `make programs` | List available programs |
| `make start` | Start cleaning (`CleanAll`) |
| `make stop` | Stop the active program |
| `make resume` | Resume (unpause) the active program (`ResumeProgram` command) |
| `make dock` | Send the robot back to base (`GoHome`) |
| `make settings` | List device settings |
| `make maps` | List robot maps |
| `make robot` | Show robot position |
| `make summaries` | Show cleaning summaries |
| `make smart-empty` | AI: is emptying the dust box justified? |
| `make watch` | AI: live false-empty detection (Ctrl+C to stop) |
| `make coverage` | AI: coverage analysis + fake-cleaning from the map |
| `make coverage-live` | AI: collect the path live (`COLLECT_SECONDS=45`s), then analyze |
| `make obstacles` | AI: obstacle-loop detection (read-only) |
| `make obstacles AUTO=1 YES=1` | AI: detect + auto-recover the robot (stop → dock → restart) — **touches the device** |
| `make test` | Run unit tests |
| `make help` | List all targets |

### Examples with options

```bash
# start / stop / resume / return to base
make start
make stop
make resume
make dock
make status

# AI layer — natural language
make chat MESSAGE="start cleaning"
make chat MESSAGE="stop cleaning"
make chat MESSAGE="what is the battery level?"
make chat MESSAGE="should I empty the dust box?"

# AI layer — smart emptying
make smart-empty
make watch                                  # wait until the robot docks, flag false empty
make watch ARGS="--interval 2 --timeout 60" # tune polling / stop after 60 s

# AI layer — coverage & fake-cleaning
make coverage                                # human-readable summary (default)
make coverage ARGS="--json"                  # same data, raw JSON
make coverage ARGS="--ai"                    # + AI natural-language verdict on what it means
make coverage ARGS="--map-id 488755484"
make coverage-live                           # collect path 45 s, then analyze
make coverage-live COLLECT_SECONDS=60        # collect 60 s instead
make coverage-live ARGS="--interval 2"       # sample every 2 s while collecting
make coverage-live ARGS="--ai"               # collect + analyze + AI verdict
```

The default `coverage`/`coverage-live` output is a short **human-readable summary**
(cleaning effort, map knowledge, health check). If the robot has barely cleaned
(`distance < 1 m`) it says so instead of printing a misleading coverage % — run
`make start` in another terminal and re-collect with `make coverage-live`.

With `--ai` the report ends with an **AI insight** block (`src/ai/insight.py`): the LLM
reads the measured metrics and explains in plain language what the robot did, whether
that is a problem, and the best next action. It never crashes the report — if the
model is unconfigured/unavailable it prints a short note instead.

# AI layer — obstacle loop (analysis is read-only)
make obstacles
make obstacles ARGS="--collect 45"           # collect live path, then analyze

# AI layer — obstacle loop + auto-recovery (REAL DEVICE: stops, docks, restarts)
make obstacles AUTO=1                        # will ask for confirmation
make obstacles AUTO=1 YES=1                  # skip confirmation (fully automatic)

# from anywhere
make -C ~/Code/dust-to-data-hackathon-26 start
```

Optional shortcut for your shell config (`~/.zshrc`):

```bash
alias vacuum='make -C ~/Code/dust-to-data-hackathon-26'
```

Then `vacuum start`, `vacuum stop`, `vacuum status`, `vacuum chat MESSAGE="start cleaning"`, ...

## Safety notes

- ALWAYS confirm program keys/options from `programs` before sending `start` to a
  physical device (never leave the vacuum in a bad state).
- The real BCRD2W only supports the `CleanAll` program
  (`ConsumerProducts.CleaningRobot.Program.Cleaning.CleanAll`) with **no options**.
  `BSH.Common.Root.SelectedProgram` is rejected with `409 SDK.Error.UnsupportedProgram`,
  and there are no `CleanType` values (Auto/CleanSpot/...) on this device. This is
  captured in `ROBOT_CLEAN_ALL_PROGRAM` in `src/home_connect/client.py`.
- To return the robot to base use the `GoHome` program
  (`ConsumerProducts.CleaningRobot.Program.Basic.GoHome`, the `dock` command). It is
  only listed by `/programs/available` while the robot is off the dock.
- Prefer the Home Connect SIMULATOR appliance for development.
