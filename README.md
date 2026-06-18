# AbsoluteSpace

A multiplayer space-program operations simulator — deep simulation, simple UI.
Design real launch vehicles from a catalog of actual hardware, accept mission
contracts, run a realistic launch campaign (schedule tests, surface and resolve
faults, manage budget and risk), then fly them on n-body-aware transfer
trajectories. Inspired by the depth of Kerbal Space Program and Dwarf Fortress,
rendered as a clean terminal-style control center.

> Status: **MVP, under active development.** A FastAPI game server drives an
> authoritative simulation; a React/TypeScript client renders a resizable,
> multiplayer Mission Operations Center. A legacy single-player pygame build is
> kept as a reference (`main.py`).

## Features

- **Solar system & orbital mechanics** — real Keplerian elements, vis-viva,
  Hohmann transfers, phase-angle launch windows, ΔV budgets.
- **Vehicle Assembly** — KSP-style stacks built from ~150 real modules
  (NASA, SpaceX, ESA, Roscosmos, JAXA, ISRO, CNSA, …) with decoupler-defined
  staging, computed ΔV/TWR/mass.
- **Mission contracts** — accept generated jobs with ΔV / crew / payload
  requirements; plan a transfer window; assign a qualifying vehicle.
- **Launch Pad campaign** — scheduled, real-time test operations (design review,
  systems test, wet rehearsal, static fire, astronaut training) that surface
  realistic complications with realistic resolution times.
- **Risk vs. reward economy** — funds, costed operations, a congressional budget
  with overrun penalties, and a mission-risk model: correct an issue (cost +
  schedule slip) or fly with it (a % chance of an in-flight anomaly).
- **Multiplayer** — one authoritative server, shared clock and fleet, live chat,
  concurrent per-craft operation queues, and shared launch slots: pad/date
  conflicts between any players block both until one moves (max 5 scheduled
  launches per player).

## Architecture

```
React (Vite/TS) ──REST /api/*──▶ FastAPI server ──wraps──▶ sim/ (pure-Python)
  resizable UI  ◀═ WebSocket /ws ═▶  authoritative GameState   physics · craft
                  state + chat ticks                            transfer · weather
```

- `sim/` — pure-Python simulation (no UI deps): bodies, physics, transfer,
  craft, module database, missions, weather, countdown, launch sites.
- `backend/` — FastAPI + WebSocket server, authoritative `GameState`, contracts
  and launch economy.
- `frontend/` — React + TypeScript client (Command Center, Vehicle Assembly,
  Launch Pad).
- `main.py` + `ui/` — original single-player pygame build (reference).

## Quick start

Requires **Python 3.11+** and **Node 18+**.

```bash
# 1. Backend (game server on :8000)
pip install -r requirements-web.txt
python -m backend.run

# 2. Frontend (web UI on :5173)
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Open it in multiple windows to play multiplayer
(shared game state, chat, and launch-slot contention). On Windows you can launch
both with `./run_web.ps1`.

See [WEB_README.md](WEB_README.md) for the full API and run details.

## License

[MIT](LICENSE) © 2026 Billy Winn Jr.
