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

1. Clone the repo and create a local `.env` from your Home Connect developer
   credentials (never commit it — it's gitignored):

   ```bash
   cp .env.example .env   # or create .env manually
   ```

2. Fill in `HOME_CONNECT_CLIENT_ID` and `HOME_CONNECT_CLIENT_SECRET` from the
   Home Connect developer portal.
3. Optionally enable the simulator appliance ("Accept SIMULATOR device") to test
   against a simulated vacuum before touching real hardware.

## Getting started

- Start with read-only calls (status, programs, settings) against the simulator.
- Always confirm program/settings payloads against the API docs before sending
  them to a physical device.
- See `AGENTS.md` for working agreements and architecture notes, and `docs/`
  (when populated) for endpoint references.

## Repo structure

```
src/        application logic (when it lands)
docs/       API/endpoint notes for the hackathon team (when populated)
.env        local secrets — gitignored, do not commit
```
