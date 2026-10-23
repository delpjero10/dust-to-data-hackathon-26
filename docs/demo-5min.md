# 5-minute demo — Dust to Data AI layer for the Bosch Spotless BCRD2W

Goal: show, live on the real robot, the three AI-layer features we built on top of raw
Home Connect data:

1. **Smart Emptying** — live detection of *false empties* (the station empties the dust
   box on every return, even after a 30 s "cleaning").
2. **Coverage analysis** — from the robot's real cleaning path: how far it travelled and
   how much of the area it was in it actually covered.
3. **Fake-cleaning detection** — flag a robot that "cleaned" for a long time but never
   entered new cells (stuck/circling).
4. **Obstacle-loop detection & auto-recovery** — if the robot hits something ~3 times in
   a row, the AI detects it and rolls back to normal (return to base + restart).

Everything runs from the repo root against the real device in the office.

---

## Setup (once, before the demo)

```bash
cp .env.example .env        # put HOME_CONNECT_CLIENT_ID / _SECRET in .env
pip install -r requirements.txt   # requests + zstandard
make login                  # one-time OAuth (paste the redirect URL back)
make test                   # 14 unit tests pass -> shows the logic is safe
```

You need **two terminals** (A and B) both in the repo root.

---

## Timeline (5:00)

### 0:00–0:30 — "We control the real device"

Terminal B:

```bash
make status
```

Show: device `Ready`, battery, charging. One command, real hardware, cloud API.
Then the punchline: **"the robot's dock empties the dust box every single time it
returns — even if it barely cleaned. Our AI layer catches that."**

### 0:30–2:00 — Feature 1: live false-empty detection

Terminal A — start watching **before** we move the robot:

```bash
make watch
```

It prints: `Watching for a false empty: waiting for the robot to start cleaning...`

Terminal B — a deliberately **short** cleaning run (~30 s):

```bash
make start        # robot leaves the dock, cleans ~30 s
sleep 30
make stop         # interrupt
make dock         # send it home (GoHome)
```

When the robot docks, **Terminal A** prints (this is the money shot):

```
Cleaning in progress... 30 s (min 2 min 0 s)

Robot docked after only 30 s of cleaning - FALSE EMPTY: the station emptied although that was unnecessary (min 2 min 0 s required).
{
  "cleaning_seconds": 30.5,
  "empty_justified": false,
  "min_clean_seconds": 120
}
```

Talking point: *"The API cannot stop the empty (no such endpoint), so our AI layer
monitors the session live and flags every unjustified empty — that's the data we use to
later gate docking / maintenance."*

> Tip: lower/raise the threshold in `.env` → `AI_MIN_CLEAN_SECONDS` (default 120) to
> make the verdict "false" or "justified" faster for the demo.

### 2:00–3:30 — Feature 2 + 3: coverage & fake-cleaning from the real path

Terminal B — start a real cleaning run:

```bash
make start
```

Terminal A — collect the live cleaning path for ~45 s, then analyze:

```bash
make coverage-live        # = python -m src.cli coverage --collect 45
```

Output (example):

```
  collected 120 cleaning points...
Map 488755484 ('(unnamed)')
Grid 800x800 @ 5.0 cm/cell | free=37951 unknown=598767 obstacles=3282
Cleaning path: 120 points, 18.4 m travelled over a 2.1 m span, 920 distinct cells visited
Coverage: ~78% of the area the robot was in
---
Cleaning looks normal: 18.4 m travelled over a 2.1 m span, 920 distinct cells visited (50.0 cells/m).
```

Talking point: *"We decompress the Zstandard map + path straight from Home Connect and
compute, for a live run, how far it went and how thoroughly it covered the area —
coverage ~78% means it missed ~22% (gaps near obstacles), a number the app never shows
you."*

### 3:30–3:45 — Feature 3: the fake-cleaning flag

Same command, but explain the red-flag case: *"if the robot is stuck (cable, rug
fringe), it reports `Run` and drains the battery, but it only revisits the same few
cells — that's fake cleaning. Our metric is new cells per metre; healthy cleaning gives
~10-50 cells/m, a stuck robot collapses to < 2."*

Show the detector on synthetic stuck data (guaranteed to work even if the real robot is
behaving):

```bash
python3 - <<'PY'
import math
from src.ai.coverage import fake_cleaning_verdict
# a robot orbiting a 30 cm circle for minutes -> long distance, no new ground
pts = [(1000 + 300*math.cos(t), 1000 + 300*math.sin(t)) for t in [i*0.1 for i in range(6000)]]
print(fake_cleaning_verdict(pts)[1])
PY
```

Expected:

```
SUSPECTED FAKE CLEANING: robot travelled 179.9 m but only entered 45 distinct cells (0.25 cells/m; healthy cleaning is > 2) - it keeps re-cleaning the same spot instead of covering new ground (possibly stuck).
```

And contrast with the healthy run from step 2 (`cells/m = 50`).

### 3:45–4:15 — Feature 4: obstacle-loop detection + recovery (roll back & resume)

Same collected path, obstacle analysis:

```bash
make obstacles        # read-only: is the robot stuck on an obstacle?
```

Output when normal:

```
No obstacle loop: recent 15 points span 1.9 m over 3.1 m of travel (1 reversals).
Recommendation: The robot is progressing normally - no intervention needed.
```

Show the *stuck* detector on synthetic data (guaranteed, no hardware needed):

```bash
python3 - <<'PY'
from src.ai.obstacle import analyze_obstacles
pts = [(1000, 1000 + (335 if i % 2 else 0)) for i in range(40)]  # oscillating on the spot
r = analyze_obstacles(pts)
print(r["reason"]); print("Recovery:", r["recovery_steps"])
PY
```

Expected:

```
STUCK AT AN OBSTACLE: the robot hit it ~13 times in a row (back-up and re-try). Recent 15 path points stayed within a 0.34 m area while travelling 4.7 m, with 13 direction reversals - it cannot pass and is not covering new ground.
Recovery: ['stop', 'go_home', 'wait_until_docked', 'restart_cleaning']
```

Talking point: *"The API has no 'nudge the robot' command, so the AI recovers the way the
robot always recovers: roll back to base and retry the area. This is the auto-recovery
(consent-gated): `make obstacles AUTO=1 YES=1`. We demo it read-only so we never surprise
the audience by restarting the vacuum mid-clean."*

### 4:15–4:45 — Clean up the robot

Terminal B:

```bash
make stop        # if still cleaning
make dock        # send it home to charge
make status      # show it docking / charging
```

### 4:45–5:00 — Close / pitch

- *"We treat the vacuum's raw telemetry (status, Zstd map, cleaning path, dock events)
  as data and put AI on top: it catches what the device hides — false empties, missed
  area, fake cleaning, and obstacle loops — and can recover the robot."*
- All of it is deterministic Python + unit-tested; the LLM layer (`make chat`) controls
  the same commands for natural-language demos.

---

## Fallback plan if the robot is uncooperative

- If the robot does not leave the dock: `make status` and re-run steps with `make dock`
  first, then `make start`.
- If the cleaning path is too short for a nice coverage number, still run
  `make coverage` — it prints an honest *"path too short"* and you can show `make test`
  (14 tests: false-empty, coverage %, circling→FAKE, sweep→normal) as *"the safety net
  we validated before touching the hardware"*.
- The `watch`/`coverage` commands are safe (read-only polling); only `start/stop/dock`
  touch the device.

## Reference

- Code: `src/ai/smart_empty.py`, `src/ai/coverage.py`, `src/ai/obstacle.py`,
  `src/ai/agent.py`, `src/cli.py`.
- Docs: `docs/ai-features.md`, `docs/home-connect-control.md`, `docs/architecture.md`.
- Tests: `make test` (`tests/`).
