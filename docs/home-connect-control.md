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
| `start [--type X]` | `PUT /homeappliances/{haId}/programs/active` | Start cleaning (`CleanType`) |
| `stop` | `DELETE /homeappliances/{haId}/programs/active` | Stop the active program |
| `settings` | `GET /homeappliances/{haId}/settings` | List device settings (`Settings`) |
| `maps` | `GET /homeappliances/{haId}/map/maps` | List robot maps (`Map`) |
| `mapinfo --map-id M [--field F]` | `GET .../map/maps/{M}[/...]` | Map data JSON: occupancyGrid, layout, cleaningStatus, objects, rooms, zones (`Map`) |
| `robot` | `GET /homeappliances/{haId}/map/robot/position` | Robot position (`Map`) |
| `summaries` | `GET /homeappliances/{haId}/map/cleaningSummary` | Cleaning summaries (`Map`) |

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

The `chat` command wires the **Bosch on-prem model** (the same one opencode uses) into
the device control via `src/ai/`:

```bash
python -m src.cli chat "start cleaning"
python -m src.cli chat "stop cleaning"
python -m src.cli chat "what is the battery level?"
```

- `src/ai/llm.py` — OpenAI-compatible chat client (the Bosch on-prem endpoint is vLLM).
- `src/ai/agent.py` — `VacuumAgent`: puts the current device status in the prompt, asks
  the model for a structured JSON decision, then executes start/stop via the same
  `HomeConnectClient` the CLI uses.
- Configure the model with `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` in `.env` (defaults
  point to the Bosch on-prem endpoint configured in opencode).
- The model is a reasoning model — leave enough `max_tokens` or the reply may be empty.

## Safety notes

- ALWAYS confirm program keys/options from `programs` before sending `start` to a
  physical device (never leave the vacuum in a bad state).
- The default `start` sends `BSH.Common.Root.SelectedProgram` with
  `RobotCleaner.Option.CleanType=Auto`. Other types: `CleanSpot`, `CleanTurbo`,
  `CleanRoom`, `CleanZone`.
- Prefer the Home Connect SIMULATOR appliance for development.
