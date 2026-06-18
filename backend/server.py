"""
AbsoluteSpace multiplayer server.

FastAPI app exposing:
  REST  /api/state         — one-shot state snapshot
        /api/bodies        — solar-system bodies (for the map)
        /api/modules       — full module tree (craft builder)
        /api/launch-sites  — launch sites
        /api/windows       — transfer windows for origin→dest
  WS    /ws                — live bidirectional channel
                             server → client: state + chat ticks
                             client → server: chat, warp, pause commands

A single background task advances the authoritative GameState and broadcasts
state to every connected client ~5×/sec.  Chat is broadcast on receipt, so
multiple browsers connected to this server share one live game + chat room.
"""

from __future__ import annotations
import asyncio
import uuid
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .game_state import GameState
from .serializers import (
    serialize_state, serialize_bodies, serialize_chat,
)

from sim.module_db import build_module_tree, TreeNode
from sim.launch_sites import LAUNCH_SITES
from sim.transfer import hohmann_windows, mission_delta_v_budget

TICK_HZ = 5.0


# ── Connection manager ────────────────────────────────────────────────────────

class Hub:
    def __init__(self):
        self.connections: dict[str, WebSocket] = {}

    async def connect(self, ws: WebSocket) -> str:
        await ws.accept()
        cid = uuid.uuid4().hex[:8]
        self.connections[cid] = ws
        return cid

    def disconnect(self, cid: str):
        self.connections.pop(cid, None)

    async def broadcast(self, payload: dict):
        dead = []
        for cid, ws in self.connections.items():
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.connections.pop(cid, None)


game = GameState()
hub = Hub()


# ── Background game loop ───────────────────────────────────────────────────────

async def game_loop():
    last = time.monotonic()
    while True:
        await asyncio.sleep(1.0 / TICK_HZ)
        now = time.monotonic()
        dt = now - last
        last = now
        game.tick(dt)
        await hub.broadcast(serialize_state(game))


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(game_loop())
    yield
    task.cancel()


app = FastAPI(title="AbsoluteSpace Server", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get("/api/state")
def get_state():
    return serialize_state(game)


@app.get("/api/bodies")
def get_bodies():
    return serialize_bodies(game)


def _tree_to_dict(node: TreeNode) -> dict:
    if node.is_leaf:
        m = node.module
        return {
            "type": "module",
            "name": m.name,
            "moduleType": m.module_type.value,
            "moduleTypeId": m.module_type.name,
            "dryMass": m.dry_mass,
            "thrust": m.thrust,
            "isp": m.isp,
            "fuelCapacity": m.fuel_capacity,
            "lifeSupportMass": m.life_support_mass,
            "powerOutput": m.power_output,
            "powerDraw": m.power_draw,
            "crew": m.crew_capacity,
            "description": m.description,
        }
    return {
        "type": "branch",
        "label": node.label,
        "expanded": node.expanded,
        "children": [_tree_to_dict(c) for c in node.children],
    }


@app.get("/api/modules")
def get_modules():
    root = build_module_tree()
    return {"tree": [_tree_to_dict(c) for c in root.children]}


@app.get("/api/launch-sites")
def get_launch_sites():
    return {
        "sites": [
            {
                "id": s.id, "name": s.name, "short": s.short,
                "agency": s.agency, "country": s.country,
                "latitude": s.latitude, "longitude": s.longitude,
                "altitude": s.altitude, "climate": s.climate,
                "pads": s.pads, "maxWindSurface": s.max_wind_surface,
            }
            for s in LAUNCH_SITES
        ]
    }


@app.get("/api/windows")
def get_windows(origin: str = Query("Earth"), dest: str = Query("Mars")):
    bodies = game.bodies
    if origin not in bodies or dest not in bodies:
        return JSONResponse({"error": "unknown body"}, status_code=400)
    wins = hohmann_windows(bodies[origin], bodies[dest], bodies["Sun"],
                           game.sim_time, n_windows=5)
    budget = mission_delta_v_budget(bodies[origin], bodies[dest], bodies["Sun"])
    return {
        "origin": origin, "dest": dest,
        "windows": [
            {
                "departDate": w.departure_date_str,
                "arriveDate": w.arrival_date_str,
                "departTime": w.departure_time,
                "durationDays": round(w.duration_days),
                "dvTotal": round(w.dv_total),
                "quality": w.quality,
            }
            for w in wins
        ],
        "budget": {k: round(v) for k, v in budget.items()},
    }


@app.post("/api/craft")
async def save_craft(payload: dict):
    """Assemble and store a craft from an ordered list of module names."""
    name = (payload.get("name") or "Spacecraft").strip()[:40]
    part_names = payload.get("parts") or []
    if not part_names:
        return JSONResponse({"error": "no parts"}, status_code=400)
    summary = game.save_craft(name, part_names)
    if "error" in summary:
        return JSONResponse(summary, status_code=400)
    await hub.broadcast(serialize_state(game))
    await hub.broadcast(serialize_chat(game))
    return summary


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    cid = await hub.connect(ws)
    name = f"Director-{cid[:4]}"
    game.join(cid, name)

    # Initial burst: identity, full state, chat history
    await ws.send_json({"type": "welcome", "playerId": cid, "name": name})
    await ws.send_json(serialize_state(game))
    await ws.send_json(serialize_chat(game))
    await hub.broadcast(serialize_chat(game))

    try:
        while True:
            data = await ws.receive_json()
            await handle_client_message(cid, name, data)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.disconnect(cid)
        game.leave(cid)
        await hub.broadcast(serialize_chat(game))
        await hub.broadcast(serialize_state(game))


async def handle_client_message(cid: str, name: str, data: dict):
    action = data.get("action")

    if action == "chat":
        text = (data.get("text") or "").strip()
        if text:
            author = game.players.get(cid, name)
            game.add_chat(author, text, role="DIRECTOR")
            await hub.broadcast(serialize_chat(game))

    elif action == "setName":
        new = (data.get("name") or "").strip()[:24]
        if new:
            old = game.players.get(cid, name)
            game.players[cid] = new
            game.system_msg(f"{old} is now known as {new}.")
            await hub.broadcast(serialize_chat(game))
            await hub.broadcast(serialize_state(game))

    elif action == "warpUp":
        game.warp_up()
    elif action == "warpDown":
        game.warp_down()
    elif action == "setWarpIdx":
        game.set_warp_idx(int(data.get("idx", game.warp_idx)))
    elif action == "togglePause":
        game.toggle_pause()

    # ── Launch pipeline actions ──
    elif action == "acceptContract":
        game.accept_contract(data.get("id", ""), cid, game.players.get(cid, name))
        await _broadcast_all()
    elif action == "planContract":
        game.plan_contract(data.get("id", ""), int(data.get("windowIndex", 0)))
        await _broadcast_all()
    elif action == "assignCraft":
        game.assign_craft(data.get("id", ""), data.get("craftName", ""))
        await _broadcast_all()
    elif action == "setLaunch":
        game.set_launch(data.get("id", ""), data.get("siteId", ""),
                        float(data.get("launchTime", 0)) or 0)
        await _broadcast_all()
    elif action == "runOperation":
        game.schedule_operation(data.get("id", ""), data.get("op", "DRY_RUN"))
        await _broadcast_all()
    elif action == "cancelTask":
        game.cancel_task(data.get("id", ""), data.get("taskId", ""))
        await _broadcast_all()
    elif action == "correctIssue":
        game.schedule_correction(data.get("id", ""), data.get("issueId", ""))
        await _broadcast_all()
    elif action == "launchContract":
        game.launch_contract(data.get("id", ""))
        await _broadcast_all()

    # Echo updated state immediately for snappy controls
    if action in ("warpUp", "warpDown", "setWarpIdx", "togglePause"):
        await hub.broadcast(serialize_state(game))


async def _broadcast_all():
    await hub.broadcast(serialize_state(game))
    await hub.broadcast(serialize_chat(game))
