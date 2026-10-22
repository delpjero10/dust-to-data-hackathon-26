# GOALS — Dust to Data (Bosch Hackathon 2026)

## Vision

We are building an **innovative solution** that adds **AI across the whole system** — from
mapping, through automation, to natural-language control of the device. We turn the
device's weaknesses into an advantage: most problems everyday users face with a robot
vacuum can be solved with a smart layer on top of the hardware.

## Main goal

Show that a "bad" device with the right AI layer becomes much better:
- **Innovation** — AI is not an add-on, it is embedded in every part of the system (data → decision → action).
- **Functionality** — we solve real problems: poor mapping, suboptimal cleaning, impractical control.

## Specific goals

### 1. AI for better mapping
- The device **maps poorly** — we analyze maps, room data, and cleaning progress.
- We generate a **better picture of the space** than the raw map provides (e.g. room
  detection, real obstacles, "dead" zones that were missed).

### 2. AI action automation
- **Automatic start/pause/stop of cleaning** based on state, triggers, or data (e.g.
  schedule, room occupancy, past sessions).
- **Smart planning** — we don't clean "however the device wants", but based on what the
  data says is needed.

### 3. Natural-language control and reporting
- The user talks to the device (chatbot / voice).
- AI translates intent into Home Connect commands and **explains what is happening** (reports).

### 4. AI in communication (end-to-end)
- The AI layer is **always in the loop**: we read state/events, interpret them, make
  decisions, send commands — all through the Home Connect API.

## How we measure success

- An innovative, demonstrable solution in front of the jury (not just "it works", but "it works smartly").
- Visible improvement in mapping / coverage compared to stock settings.
- Automated actions that run without human intervention.
- Natural-language control that feels intuitive to the audience.
- A clean, reproducible architecture the team can explain.

## Principles

- Simulator-first: safe testing before touching the real device.
- Log and document every endpoint/interaction for the team.
- Focus on a concrete demo by the end of the hackathon.
