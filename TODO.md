# TODO — Dust to Data (Bosch Hackathon 2026)

- [x] Connect device to mobile (Home Connect app) — **DONE**
- [x] Connect device via laptop (Home Connect API + OAuth2) — **DONE**
- [x] Add AI layer (mapping, automation, NLP control) — **DONE**
- [x] Home Connect portal — contact support — **DONE**
- [x] Architecture research — how to add AI layer into communication — **DONE**
- [x] Define our team's goals and objectives — **DONE**
- [x] Investigate how to access the data the vacuum works with (map data, status, events) — **DONE**
- [ ] Make the presentation — **IN PROGRESS**
- [x] Contact service technicians — **DONE**
- [x] Test the device in reality room by room and record its weaknesses — **DONE**
- [x] Investigate the best on-prem AI model among those offered for our system — **DONE**
- [x] Smart Emptying: don't empty the dust box on every return to base — only when the
      robot actually cleaned (default > 2 min). See `docs/ai-features.md` — **IMPLEMENTED**
      (`src/ai/smart_empty.py`, `python -m src.cli smart-empty`, agent `empty` action)
- [x] Coverage analysis: how much of the area the robot actually covered — **IMPLEMENTED**
      (`src/ai/coverage.py`, `python -m src.cli coverage[ --collect]`, agent)
- [x] Fake-cleaning detection: flag long "cleaning" that never covers new cells —
      **IMPLEMENTED** (`src/ai/coverage.py`, `python -m src.cli coverage`)
- [x] Obstacle-loop detection & auto-recovery: detect "hit N times in a row" and roll
      back (stop -> dock -> restart) — **IMPLEMENTED** (`src/ai/obstacle.py`,
      `python -m src.cli obstacles [--auto [--yes]]`)

## Status legend
- `[ ]` — pending
- `[x]` — done
