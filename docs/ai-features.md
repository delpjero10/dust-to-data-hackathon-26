# AI features — problem list and solutions (Bosch Hackathon 2026)

This is the running list of device weaknesses/bugs we observed on the real BCRD2W and the
AI-layer features we add to fix them. Implementation lives in `src/ai/`, docs in
`docs/`, and each entry is verified against the real device where possible.

Legend:
- **Observed**: what the device actually does (the problem).
- **AI feature**: what our layer adds on top of the raw Home Connect data/API.
- **Status**: `todo` / `implemented` / `verified`.

---

## 1. Dust box is emptied on every return to base (even without cleaning)

- **Observed**: The station empties the dust box every time the robot returns to its
  base, including cases where it barely cleaned (e.g. it only docked after a very short
  session, so there is little to no dust in the box). Result: wasted energy, extra noise,
  premature wear of the emptying mechanism and the dust bag.
- **Cause**: The empty happens automatically at the docking station and today's Home
  Connect API does **not** expose an endpoint to trigger/suppress it
  (`GET .../commands` only offers `PauseProgram`, `ResumeProgram`, `AcknowledgeEvent`).
- **AI feature — Smart Emptying**: The AI layer tracks how long a cleaning session
  actually ran (`BSH.Common.Option.ElapsedProgramTime` while a program is active) and
  applies a policy: an empty is only considered **justified** when the robot cleaned
  for at least **2 minutes** (configurable via `AI_MIN_CLEAN_SECONDS`, default `120`).
  The layer reports the verdict so the team can see which empties were unnecessary
  ("false empties"), and it is ready to gate a real empty command if/when the API
  exposes one.
- **Status**: `implemented` (policy + reporting + live detection), `verified` against
  the real device.
- **Where**: `src/ai/smart_empty.py`; CLI `smart-empty` (current-session verdict) and
  `watch` (live detection); agent `empty` action.

### Demo-able part: real-time false-empty detection (`watch`)

The API cannot suppress the station's auto-empty, but we CAN detect it live. `make watch`
polls the status stream; when the robot returns to base after a cleaning session it
prints whether that dock-triggered empty was justified or a **FALSE EMPTY**, with the
actual cleaning duration (wall-clock, from `OperationState=Run` until dock/charge):

```bash
make watch                 # watched live; Ctrl+C to stop
make watch ARGS="--interval 3"   # tune polling (default 5 s)
```

Example output:

```
Watching for a false empty: waiting for the robot to start cleaning...
Cleaning in progress... 0:12 (min 2 min 0 s)
Robot docked after only 0:35 of cleaning - FALSE EMPTY: the station emptied although that was unnecessary (min 2 min 0 s required).
{
  "cleaning_seconds": 35,
  "empty_justified": false,
  "min_clean_seconds": 120
}
```

The state machine is pure and unit-tested (`tests/test_smart_empty.py`, `make test`).

---

## Placeholder for the next issues

(new bugs / weaknesses we find while testing the device go here, e.g. map quality,
missed rooms, autonomy quirks, ...)
