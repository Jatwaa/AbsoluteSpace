# AbsoluteSpace — Web (React + FastAPI) build

A migration of the pygame UI to a **standard, resizable, movable** web interface
backed by a **multiplayer game server**. Your entire `sim/` simulation is reused
unchanged — it now runs inside a FastAPI server instead of the pygame loop.

```
┌──────────────┐     REST /api/*        ┌───────────────────────────┐
│  React app   │ ───────────────────►   │  FastAPI server (:8000)   │
│  (Vite :5173)│ ◄══ WebSocket /ws ══►   │  · authoritative GameState│
│  resizable   │   state + chat ticks    │  · wraps sim/* unchanged  │
└──────────────┘                         │  · 5 Hz broadcast loop    │
                                         └───────────────────────────┘
```

## Run it

**One command (Windows):**
```powershell
./run_web.ps1
```

**Or manually, in two terminals:**
```powershell
# Terminal 1 — game server
python -m backend.run

# Terminal 2 — web UI
cd frontend
npm install      # first time only
npm run dev
```

Then open **http://localhost:5173**. Open it in **multiple browser windows** to
see real multiplayer: shared game clock, shared fleet, and a live chat room.

## What works in this slice

- **Command Center home screen** — live fleet listing with per-craft phase,
  destination, next-attention countdown and urgency flags (sorted critical-first).
- **Global Comms** — real multiplayer chat. Every connected browser shares one
  room; messages broadcast to all.
- **Live game clock** — the server advances the simulation authoritatively;
  warp/pause controls sync to every client.
- **Facilities** — Vehicle Assembly + Mission Map buttons (wired next),
  Congress / Astronaut Corps / Technologies placeholders.

## Backend API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/state` | One-shot state snapshot |
| GET | `/api/bodies` | Solar-system bodies (for the map) |
| GET | `/api/modules` | Full module tree (craft builder) |
| GET | `/api/launch-sites` | Launch sites |
| GET | `/api/windows?origin=Earth&dest=Mars` | Transfer windows + ΔV budget |
| WS  | `/ws` | Live state + chat; client sends chat / warp / pause |

## Next steps (not yet ported)

- Craft Builder view (consumes `/api/modules`, posts assembled craft)
- Mission Map view (canvas/SVG, consumes `/api/bodies`)
- Launch Control view (consumes `/api/launch-sites` + weather, drives countdown)

The original pygame app (`main.py`) still runs and remains the reference
implementation until the web build reaches parity.
