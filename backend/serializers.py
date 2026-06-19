"""JSON serialization of simulation objects → plain dicts for the API."""

from __future__ import annotations
from sim.mission import Mission, MissionControl, Urgency
from sim.transfer import seconds_to_date
from sim.bodies import AU

DAY = 86400.0


def serialize_mission(m: Mission, now: float) -> dict:
    sc = m.spacecraft
    info = m.next_attention(now)
    return {
        "name": m.name,
        "origin": m.origin.name,
        "destination": m.destination.name,
        "phase": m.phase.value,
        "phaseId": m.phase.name,
        "isActive": m.is_active,
        "crew": sc.crew,
        "deltaV": round(sc.remaining_delta_v),
        "fuelTons": round(sc.fuel_remaining / 1000, 1),
        "status": sc.status,
        "departDate": m.window.departure_date_str,
        "arriveDate": m.window.arrival_date_str,
        "attention": {
            "urgency": info.urgency.value,
            "label": info.label,
            "countdown": info.countdown_str(now),
            "time": None if info.time == float("inf") else info.time,
        },
    }


def serialize_body(name: str, body, now: float) -> dict:
    x, y = body.position_at(now) if body.parent else (0.0, 0.0)
    return {
        "name": name,
        "color": list(body.color),
        "displayRadius": body.display_radius,
        "x_au": x / AU,
        "y_au": y / AU,
        "semiMajorAxisAu": body.semi_major_axis / AU if body.semi_major_axis else 0,
        "eccentricity": body.eccentricity,
        "argPeriapsis": body.arg_periapsis,
        "isStar": body.parent is None,
    }


def serialize_state(gs) -> dict:
    """Full game-state snapshot broadcast to clients."""
    now = gs.sim_time
    missions = [serialize_mission(m, now) for m in gs.mc.missions]
    crit = sum(1 for m in gs.mc.missions
               if m.next_attention(now).urgency == Urgency.CRITICAL)
    return {
        "type": "state",
        "simTime": now,
        "date": seconds_to_date(now),
        "warp": gs.warp,
        "warpIdx": gs.warp_idx,
        "paused": gs.paused,
        "playersOnline": len(gs.players),
        "playerNames": list(gs.players.values()),
        "missionCount": len(missions),
        "criticalCount": crit,
        "missions": missions,
        "funds": round(gs.funds, 1),
        "budgetPenalty": round(gs.budget_penalty, 1),
        "congressNote": gs.congress_note,
        "contracts": [_contract_dict(gs, c, now) for c in gs.contracts],
        "crafts": [gs.craft_spec(sc) for sc in gs.saved_crafts],
        "launches": ([seq.to_dict() for seq in gs.launch_sequences.values()]
                     + [seq.to_dict() for seq in gs.reentry_sequences.values()]),
    }


def _contract_dict(gs, c, now) -> dict:
    """Contract dict, with launch odds attached for vehicles at the pad."""
    from .contracts import ContractStatus
    d = c.to_dict(now)
    if c.craft_name and c.status in (ContractStatus.VEHICLE_ASSIGNED, ContractStatus.READY):
        d["launchOdds"] = gs.launch_odds(c)
    return d


def serialize_bodies(gs) -> dict:
    now = gs.sim_time
    return {
        "type": "bodies",
        "simTime": now,
        "bodies": [serialize_body(n, b, now) for n, b in gs.bodies.items()],
    }


def serialize_chat(gs, limit: int = 80) -> dict:
    return {
        "type": "chat",
        "messages": [c.to_dict() for c in gs.chat[-limit:]],
    }
