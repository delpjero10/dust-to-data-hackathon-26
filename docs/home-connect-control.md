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

## Setup

1. Create `.env` with your Home Connect developer credentials (from
   https://developer.home-connect.com).
2. Install deps: `pip install -r requirements.txt`.
3. Log in: `python -m src.cli login`.

## Safety notes

- ALWAYS confirm program keys/options from `programs` before sending `start` to a
  physical device (never leave the vacuum in a bad state).
- The default `start` sends `BSH.Common.Root.SelectedProgram` with
  `RobotCleaner.Option.CleanType=Auto`. Other types: `CleanSpot`, `CleanTurbo`,
  `CleanRoom`, `CleanZone`.
- Prefer the Home Connect SIMULATOR appliance for development.
