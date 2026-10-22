# AGENTS.md

## Project overview

This repository is a test environment for the **Bosch Spotless BCRD2W "Spotless Advanced"**
robotic vacuum cleaner and its **Home Connect API**.

- Home Connect Developer API: https://apiclient.home-connect.com/#/map
- Event target: **Bosch Hackathon Belgrade 2026**

The repo is intentionally minimal right now (scaffold/initial commit). Treat it as a
sandbox: experiment with device communication, then build the AI layer on top.

## Goals

1. **Communicate with the real device** — the Bosch Spotless BCRD2W robot vacuum during the
   hackathon (Home Connect API).
2. **Add an AI layer** on top of the raw Home Connect data, for example:
   - improve mapping / map understanding (analyze maps, room metadata, cleaning progress)
   - automate actions (start/pause/stop cleaning based on state, triggers, or data)
   - natural-language control and reporting to the user.

## Tech & architecture notes

- Home Connect API is OAuth2-based. You need client credentials (client_id/secret) from the
  Home Connect developer portal; there is also an optional "Accept SIMULATOR device"
  flow for testing against simulated appliances before touching the real hardware.
- Communication patterns you will encounter:
  - **Programs** — start/stop cleaning programs (e.g. `BSH.Common.Root.SelectedProgram`).
  - **Settings** — device configuration, e.g. `BSH.Common.Setting.PowerState`.
  - **Status** — live device state values.
  - **Events** — server-sent events (SSE) pushed from the API for state changes.
  - **Commands** — one-shot actions in the `commands`/`interactions` block.
  - Robot vacuum specifics may include map-related settings (e.g. clear/save/activate map).
- Prefer test-first, simulator-first development. Only exercise real-device calls when
  verified against the API docs so you do not leave the device in a bad state (e.g. always
  confirm program/settings payloads before sending them).
- Keep credentials out of the repo (`.gitignore` already covers `.env*` — use a local
  `.env` for secrets).

## Working agreements for this repo

- **Use English for everything** — code comments, docs, commit messages, file contents.
  Even if the team communicates in another language, everything committed to the repo
  must be in English.
- Ask before modifying anything that could affect the physical device beyond reading state.
- Keep API calls idempotent and safe where possible.
- Document any endpoint/interaction you use in code comments or a small `docs/` section so
  the hackathon team can reuse it.
- Follow the existing repo conventions once code lands; right now the repo is empty, so
  establish clean, minimal structure (e.g. `src/` for logic, `.env` for secrets).
