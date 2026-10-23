# Dust to Data — Bosch Hackathon 2026

Connecting Bosch devices to AI. Test environment for the **Bosch Spotless BCRD2W
"Spotless Advanced"** robotic vacuum cleaner and its **Home Connect API**.

## Overview

This repo is a sandbox for the **Bosch Hackathon Belgrade 2026**:

1. **Talk to the real device** — the Bosch Spotless BCRD2W robot vacuum via the
   [Home Connect Developer API](https://apiclient.home-connect.com/#/map).
2. **AI layer on top** — improve mapping / map understanding, automate actions
   (start/pause/stop cleaning), natural-language control and reporting.

## Setup

1. Register a developer account + application in the **Home Connect Developer Portal**
   (https://developer.home-connect.com). To experiment with the real API you have to
   create a new application (host: `https://api.home-connect.com`); for your application
   to interact with appliances it must be authorized by the API — register an application
   first, then log in with your Home Connect Account and grant access.

2. Clone the repo and create a local `.env` from your Home Connect developer
   credentials (never commit it — it's gitignored):

   ```bash
   cp .env.example .env   # or create .env manually
   ```

3. Fill in `HOME_CONNECT_CLIENT_ID` and `HOME_CONNECT_CLIENT_SECRET` from the
   Home Connect developer portal.
4. Optionally enable the simulator appliance ("Accept SIMULATOR device") to test
   against a simulated vacuum before touching real hardware.

## Getting started

- Install deps: `pip install -r requirements.txt`
- Start with read-only calls (status, programs, settings) against the simulator.
- Always confirm program/settings payloads against the API docs before sending
  them to a physical device.
- See `AGENTS.md` for working agreements and architecture notes, and `docs/`
  for endpoint references.

## Architecture

See `docs/architecture.md` for diagrams of how the laptop talks to the **real BCRD2W
in the office** through the Home Connect cloud (OAuth2, status, start/stop, events).

### Demo

A full **5-minute live demo script** (Smart Emptying + Coverage + Fake-cleaning) is in
[`docs/demo-5min.md`](docs/demo-5min.md).

## Controlling the device from the laptop

A CLI lives in `src/cli.py` (Home Connect OAuth2 + API client):

```bash
python -m src.cli login      # one-time auth, stores token in .token.json
python -m src.cli appliances # list your paired appliances
python -m src.cli start      # start cleaning (CleanAll)
python -m src.cli stop       # stop the active cleaning program
python -m src.cli status     # live status
python -m src.cli chat "start cleaning"   # AI layer: natural-language control
```

> **Note for the real BCRD2W:** the device only supports the `CleanAll` program and no
> options. `BSH.Common.Root.SelectedProgram` is rejected with a `409
> SDK.Error.UnsupportedProgram` — always start with the `CleanAll` key (see
> `ROBOT_CLEAN_ALL_PROGRAM` in `src/home_connect/client.py`).

### Quick launch from the terminal (no opencode)

Use the `Makefile` shortcuts from the repo root:

```bash
make start        # start cleaning (CleanAll)
make stop         # stop cleaning
make dock         # send the robot back to base (GoHome)
make status       # live status
make chat MESSAGE="start cleaning"   # AI layer
make smart-empty  # AI layer: is emptying the dust box justified?
make watch        # AI layer: live detection of false empties when the robot docks
make coverage     # AI layer: coverage analysis + fake-cleaning detection from the map
make obstacles    # AI layer: obstacle-loop detection (read-only)
make test         # unit tests
```

The complete reference for every `make` command (with options and examples) is in
[`docs/home-connect-control.md`](docs/home-connect-control.md) &rarr; "All `make` commands".

Optional: put this in your shell config (`~/.zshrc`) so `vacuum ...` works from anywhere:

```bash
alias vacuum='make -C ~/Code/dust-to-data-hackathon-26'
```

Then just run `vacuum start`, `vacuum stop`, `vacuum status`, etc.

The `chat` command uses the **Bosch on-prem model** (the same one opencode uses) through
`src/ai/` to turn natural language into device actions. See
`docs/home-connect-control.md` for the AI layer details.

## Repo structure

```
src/                application logic (Home Connect client + CLI)
docs/               API/endpoint notes for the hackathon team
.env                local secrets — gitignored, do not commit
.token.json         local OAuth token — gitignored, do not commit
```
