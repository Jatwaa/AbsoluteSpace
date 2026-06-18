"""
Authoritative game state for the multiplayer server.

Wraps the existing pure-Python simulation (sim/*) without modifying it.
A single GameState instance is the source of truth; the server advances it
on a fixed tick and broadcasts snapshots to all connected players.
"""

from __future__ import annotations
import time
import itertools
from dataclasses import dataclass, field
from typing import Optional

from sim.bodies import build_solar_system
from sim.mission import MissionControl, Mission
from sim.transfer import hohmann_windows, seconds_to_date
from sim.craft import Spacecraft

DAY = 86400.0
J2000_START = 8035 * DAY        # ~Jan 2022, matches the pygame build
WARP_LEVELS = [1, 10, 100, 1_000, 10_000, 86_400, 864_000]


@dataclass
class ChatMessage:
    id: int
    author: str
    role: str          # DIRECTOR | SYSTEM | CAPCOM | FLIGHT | ...
    text: str
    sim_time: float

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "author": self.author,
            "role": self.role,
            "text": self.text,
            "date": seconds_to_date(self.sim_time),
        }


class GameState:
    def __init__(self):
        self.bodies = build_solar_system()
        self.sim_time = J2000_START
        self.warp_idx = 4          # ×10,000 default — fleet evolves visibly
        self.paused = False

        self.mc = MissionControl(self.bodies, self.sim_time)

        # Chat / players
        self._chat_id = itertools.count(1)
        self.chat: list[ChatMessage] = []
        self.players: dict[str, str] = {}   # connection_id -> display name

        # Saved craft designs (from the Vehicle Assembly builder)
        self.saved_crafts: list[Spacecraft] = []

        # Mission contracts pipeline + economy
        self.contracts = []          # list[MissionContract]
        self._contract_counter = 1
        from .contracts import START_FUNDS
        self.funds = START_FUNDS     # §M available funding
        self.tasks = []              # list[ScheduledTask] (in-progress ops/repairs)
        self._task_counter = 1
        self.budget_penalty = 0.0    # congressional penalty applied to next allotment
        self.congress_note = ""      # last congressional action, for display

        # Background controller chatter
        self._chatter_timer = 0.0
        self._chatter_idx = 0
        self._chatter = [
            ("CAPCOM",  "Telemetry lock confirmed on all active vehicles."),
            ("FLIGHT",  "Trajectory team, stand by for window update."),
            ("GUIDANCE","Nav solution converged. Residuals nominal."),
            ("PROP",    "Tank pressures holding steady fleet-wide."),
            ("NETWORK", "Deep Space Network handover complete."),
        ]

        self._seed()

    # ── Seeding ───────────────────────────────────────────────────────────────

    def _seed(self):
        self.system_msg("Global comms channel online.")
        self.add_chat("FLIGHT", "Welcome to Mission Control, Director.", role="FLIGHT")
        self._seed_demo_mission()
        self._seed_contracts()
        self._seed_demo_craft()

    def _seed_contracts(self):
        from .contracts import generate_contracts
        new = generate_contracts(self.bodies, self.sim_time, self._contract_counter)
        self._contract_counter += len(new)
        self.contracts.extend(new)

    def _seed_demo_craft(self):
        """Provide ready-made crafts so the pipeline is usable immediately."""
        from sim.module_db import build_flat_catalog
        cat = build_flat_catalog()

        def build(name, names):
            try:
                self.saved_crafts.append(
                    Spacecraft(name=name, parts=[cat[n] for n in names]))
            except Exception:
                pass

        # Modest relay carrier — under-powered on purpose (dry runs will flag it).
        build("Relay-Carrier", [
            "GEO Comsat (generic)", "DSN-compatible Dish", "Dawn Triple-Junction",
            "Falcon 9 Stage Sep System", "Falcon 9 S2 Tank", "Merlin 1D Vac",
            "Falcon 9 Stage Sep System", "Falcon 9 S1 Tanks",
            "Merlin 1D SL", "Merlin 1D SL", "Merlin 1D SL",
        ])

        # Heavy lifter (Saturn-V class) — clears interplanetary ΔV with margin.
        build("Heavy-Lifter", [
            "GEO Comsat (generic)", "DSN-compatible Dish", "Dawn Triple-Junction",
            "SLS Core/ICPS Interstage", "ICPS (SLS Block 1)", "RL-10C-3", "RL-10C-3",
            "Saturn V Interstage (S-II/S-IVB)", "S-II Stage Tanks",
            "RS-25D/E", "RS-25D/E", "RS-25D/E", "RS-25D/E", "RS-25D/E",
            "Saturn V Interstage (S-IC/S-II)", "S-IC Stage Tanks",
            "F-1", "F-1", "F-1", "F-1", "F-1",
        ])

    def _seed_demo_mission(self):
        try:
            from sim.module_db import build_flat_catalog
            cat = build_flat_catalog()
            parts = [
                cat["Generic 100kg Probe"], cat["Dawn Triple-Junction"],
                cat["DSN-compatible Dish"], cat["Psyche Xenon Tank"],
                cat["Falcon 9 Stage Sep System"], cat["Falcon 9 S2 Tank"],
                cat["Merlin 1D Vac"], cat["Falcon 9 Stage Sep System"],
                cat["Falcon 9 S1 Tanks"], cat["Merlin 1D SL"],
                cat["Merlin 1D SL"], cat["Merlin 1D SL"],
            ]
            sc = Spacecraft(name="Pathfinder-1", parts=parts)
            wins = hohmann_windows(self.bodies["Earth"], self.bodies["Mars"],
                                   self.bodies["Sun"], self.sim_time, n_windows=3)
            if wins:
                self.mc.create_mission(sc, "Earth", "Mars", wins[0])
        except Exception as e:
            self.system_msg(f"Demo mission seed failed: {e}")

    # ── Tick ──────────────────────────────────────────────────────────────────

    def tick(self, dt_real: float):
        if not self.paused:
            dt_sim = dt_real * WARP_LEVELS[self.warp_idx]
            self.sim_time += dt_sim
            self.mc.sim_time = self.sim_time
            self.mc.step(dt_sim)
            self._process_schedule()

        # Background chatter on a wall-clock cadence
        self._chatter_timer += dt_real
        if self._chatter_timer > 20.0:
            self._chatter_timer = 0.0
            role, msg = self._chatter[self._chatter_idx % len(self._chatter)]
            self._chatter_idx += 1
            self.add_chat(role, msg, role=role)

    # ── Commands ──────────────────────────────────────────────────────────────

    @property
    def warp(self) -> int:
        return WARP_LEVELS[self.warp_idx]

    def set_warp_idx(self, idx: int):
        self.warp_idx = max(0, min(len(WARP_LEVELS) - 1, idx))

    def warp_up(self):
        self.set_warp_idx(self.warp_idx + 1)

    def warp_down(self):
        self.set_warp_idx(self.warp_idx - 1)

    def toggle_pause(self):
        self.paused = not self.paused

    # ── Players & chat ────────────────────────────────────────────────────────

    def join(self, conn_id: str, name: str):
        self.players[conn_id] = name
        self.system_msg(f"{name} joined Mission Control.")

    def leave(self, conn_id: str):
        name = self.players.pop(conn_id, None)
        if name:
            self.system_msg(f"{name} left Mission Control.")

    def add_chat(self, author: str, text: str, role: str = "DIRECTOR") -> ChatMessage:
        msg = ChatMessage(next(self._chat_id), author, role, text, self.sim_time)
        self.chat.append(msg)
        if len(self.chat) > 200:
            self.chat = self.chat[-200:]
        return msg

    def system_msg(self, text: str):
        return self.add_chat("SYSTEM", text, role="SYSTEM")

    # ── Craft assembly ────────────────────────────────────────────────────────

    def save_craft(self, name: str, part_names: list[str]) -> dict:
        """Build a Spacecraft from module names (top→bottom) and store it."""
        from sim.module_db import build_flat_catalog
        cat = build_flat_catalog()
        parts = []
        for pn in part_names:
            m = cat.get(pn)
            if m is None:
                return {"error": f"unknown module: {pn}"}
            parts.append(m)
        sc = Spacecraft(name=name, parts=parts)
        self.saved_crafts.append(sc)
        stages = sc.compute_stages()
        self.system_msg(
            f"Vehicle '{name}' assembled — {len(stages)} stage(s), "
            f"{sc.total_mass/1000:.1f} t, ΔV {sc.total_delta_v:,.0f} m/s."
        )
        return {
            "name": name,
            "stages": len(stages),
            "totalMassTons": round(sc.total_mass / 1000, 2),
            "totalDeltaV": round(sc.total_delta_v),
            "crew": sc.crew,
        }

    def craft_spec(self, sc: Spacecraft) -> dict:
        """Computed specs for a saved craft, used by the launch pipeline."""
        from sim.craft import ModuleType
        part_names = [p.name for p in sc.parts if p.module_type != ModuleType.DECOUPLER]
        return {
            "name": sc.name,
            "stages": len(sc.compute_stages()),
            "totalMass": sc.total_mass,
            "totalMassTons": round(sc.total_mass / 1000, 2),
            "totalDeltaV": round(sc.total_delta_v),
            "twr": round(sc.twr, 2),
            "crew": sc.crew,
            "partNames": part_names,
        }

    def craft_by_name(self, name: str) -> Optional[Spacecraft]:
        return next((c for c in self.saved_crafts if c.name == name), None)

    # ── Contract pipeline ─────────────────────────────────────────────────────

    def contract_by_id(self, cid: str):
        return next((c for c in self.contracts if c.id == cid), None)

    def accept_contract(self, cid: str, player_id: str = "", player_name: str = "") -> dict:
        from .contracts import ContractStatus, BUDGET_FACTOR, MIN_BUDGET
        c = self.contract_by_id(cid)
        if not c or c.status != ContractStatus.AVAILABLE:
            return {"error": "cannot accept"}
        c.status = ContractStatus.ACCEPTED
        c.owner_id = player_id or "solo"
        c.owner_name = player_name or self.players.get(player_id, "Director")
        # Congressional allotment, reduced by any pending overrun penalty
        base = round(c.reward * BUDGET_FACTOR)
        c.budget = max(MIN_BUDGET, base - self.budget_penalty)
        if self.budget_penalty > 0:
            self.system_msg(f"CONGRESS: {c.title} allotment cut by §{self.budget_penalty:.0f}M "
                            f"(prior overrun). Budget §{c.budget:.0f}M.")
            self.congress_note = (f"Allotment reduced §{self.budget_penalty:.0f}M "
                                  f"due to the previous mission's overrun.")
            self.budget_penalty = 0.0
        else:
            self.system_msg(f"Contract accepted: {c.title} → {c.destination}. "
                            f"Budget §{c.budget:.0f}M.")
        self._refill_contracts()
        return {"ok": True}

    def _refill_contracts(self):
        from .contracts import ContractStatus, generate_contracts
        avail = sum(1 for c in self.contracts if c.status == ContractStatus.AVAILABLE)
        if avail < 2:
            new = generate_contracts(self.bodies, self.sim_time,
                                     self._contract_counter, count=2)
            self._contract_counter += len(new)
            self.contracts.extend(new)

    def plan_contract(self, cid: str, window_index: int) -> dict:
        from .contracts import ContractStatus
        c = self.contract_by_id(cid)
        if not c or c.status not in (ContractStatus.ACCEPTED, ContractStatus.PLANNED,
                                     ContractStatus.VEHICLE_ASSIGNED, ContractStatus.READY):
            return {"error": "cannot plan"}
        wins = hohmann_windows(self.bodies[c.origin], self.bodies[c.destination],
                               self.bodies["Sun"], self.sim_time, n_windows=5)
        if not wins:
            return {"error": "no windows"}
        idx = max(0, min(len(wins) - 1, window_index))
        w = wins[idx]
        c.chosen_window = {
            "departTime": w.departure_time,
            "departDate": w.departure_date_str,
            "arriveDate": w.arrival_date_str,
            "durationDays": round(w.duration_days),
            "dvTotal": round(w.dv_total),
            "quality": w.quality,
        }
        # Default the planned launch time to the window
        if c.planned_launch_time is None:
            c.planned_launch_time = w.departure_time
        if c.status == ContractStatus.ACCEPTED:
            c.status = ContractStatus.PLANNED
        self.system_msg(f"{c.title}: planned for {w.departure_date_str} "
                        f"(ΔV {w.dv_total:,.0f} m/s, {w.duration_days:.0f} d).")
        return {"ok": True}

    def assign_craft(self, cid: str, craft_name: str) -> dict:
        from .contracts import ContractStatus
        c = self.contract_by_id(cid)
        if not c or c.status not in (ContractStatus.PLANNED, ContractStatus.VEHICLE_ASSIGNED,
                                     ContractStatus.READY):
            return {"error": "plan the mission first"}
        if not self.craft_by_name(craft_name):
            return {"error": "unknown craft"}
        c.craft_name = craft_name
        c.status = ContractStatus.VEHICLE_ASSIGNED
        c.last_dry_run = None
        self.system_msg(f"{c.title}: vehicle '{craft_name}' assigned.")
        return {"ok": True}

    def _scheduled_launch_count(self, owner_id, exclude_id=None) -> int:
        """How many slots this owner currently holds (reserved, not launched)."""
        return sum(1 for c in self.contracts
                   if c.owner_id == owner_id and c.id != exclude_id and self._holds_slot(c))

    def set_launch(self, cid: str, site_id: str, launch_time: float) -> dict:
        from .contracts import ContractStatus, MAX_SCHEDULED_LAUNCHES
        from sim.launch_sites import SITES_BY_ID
        c = self.contract_by_id(cid)
        if not c or c.status not in (ContractStatus.VEHICLE_ASSIGNED, ContractStatus.READY):
            return {"error": "assign a vehicle first"}
        if site_id not in SITES_BY_ID:
            return {"error": "unknown site"}
        # Per-player cap of 5 reserved launch slots (only when claiming a NEW slot)
        if not self._holds_slot(c):
            if self._scheduled_launch_count(c.owner_id) >= MAX_SCHEDULED_LAUNCHES:
                return {"error": f"limit reached: {MAX_SCHEDULED_LAUNCHES} scheduled launches per player"}
        c.launch_site_id = site_id
        if launch_time:
            c.planned_launch_time = float(launch_time)
        c.window_missed = False
        c.status = ContractStatus.VEHICLE_ASSIGNED
        c.last_dry_run = None
        c.design_ok = False
        self._recompute_conflicts()
        if c.conflict:
            self.system_msg(f"SLOT CONFLICT: {c.title} and {c.conflict['withTitle']} "
                            f"(owner {c.conflict['withOwner']}) both want pad {site_id} near "
                            f"{seconds_to_date(c.planned_launch_time)} — one must move.")
        return {"ok": True}

    # ── Scheduling (per-craft queue; many crafts run concurrently) ────────────

    def _tasks_for(self, cid):
        return [t for t in self.tasks if t.contract_id == cid]

    def _running_for(self, cid):
        return next((t for t in self.tasks
                     if t.contract_id == cid and t.status == "RUNNING"), None)

    def _enqueue(self, cid, kind, label, cost, duration_days, op=None, issue_id=None):
        from .contracts import ScheduledTask
        tid = f"T{self._task_counter:04d}"
        self._task_counter += 1
        t = ScheduledTask(id=tid, contract_id=cid, kind=kind, label=label,
                          cost=cost, duration_days=duration_days, op=op, issue_id=issue_id)
        self.tasks.append(t)
        self._promote(cid)
        return t

    def _promote(self, cid):
        """Start the next pending task for a contract if nothing is running."""
        if self._running_for(cid):
            return
        pending = [t for t in self.tasks if t.contract_id == cid and t.status == "PENDING"]
        if pending:
            pending[0].start(self.sim_time)

    def schedule_operation(self, cid: str, op: str) -> dict:
        from .contracts import (ContractStatus, OP_COSTS, OP_LABELS, OP_DURATION_DAYS)
        c = self.contract_by_id(cid)
        if not c or c.status not in (ContractStatus.VEHICLE_ASSIGNED, ContractStatus.READY):
            return {"error": "assign a vehicle and launch slot first"}
        if not c.launch_site_id or c.planned_launch_time is None:
            return {"error": "select a launch site and time"}
        if op not in OP_COSTS:
            return {"error": "unknown operation"}
        cost = OP_COSTS[op]
        if self.funds < cost:
            return {"error": f"insufficient funds (need §{cost:.0f}M)"}
        dur = OP_DURATION_DAYS[op]
        self.funds -= cost
        c.spent += cost
        self._enqueue(cid, "OP", OP_LABELS[op], cost, dur, op=op)
        self._sync_task_mirrors()
        queued = len([t for t in self.tasks if t.contract_id == cid and t.status == "PENDING"])
        where = "started" if self._running_for(cid) and self._running_for(cid).op == op and queued == 0 else "queued"
        self.system_msg(f"{c.title}: {OP_LABELS[op]} {where} (§{cost:.0f}M, {dur:.0f} d).")
        return {"ok": True}

    def schedule_correction(self, cid: str, issue_id: str) -> dict:
        c = self.contract_by_id(cid)
        if not c:
            return {"error": "no contract"}
        iss = next((i for i in c.issues if i.id == issue_id and not i.corrected), None)
        if not iss:
            return {"error": "issue not found"}
        # avoid double-queuing the same repair
        if any(t.issue_id == issue_id for t in self.tasks if t.contract_id == cid):
            return {"error": "repair already scheduled"}
        if self.funds < iss.correction_cost:
            return {"error": f"insufficient funds (need §{iss.correction_cost:.0f}M)"}
        self.funds -= iss.correction_cost
        c.spent += iss.correction_cost
        self._enqueue(cid, "CORRECTION", f"Repair: {iss.category}",
                      iss.correction_cost, iss.correction_days, issue_id=issue_id)
        self._sync_task_mirrors()
        self.system_msg(f"{c.title}: repair of '{iss.category}' queued "
                        f"(§{iss.correction_cost:.0f}M, {iss.correction_days:.0f} d).")
        return {"ok": True}

    def cancel_task(self, cid: str, task_id: str) -> dict:
        t = next((t for t in self.tasks if t.id == task_id and t.contract_id == cid), None)
        if not t:
            return {"error": "task not found"}
        c = self.contract_by_id(cid)
        self.tasks.remove(t)
        if t.status == "PENDING":
            # full refund for un-started work
            self.funds += t.cost
            if c:
                c.spent -= t.cost
            self.system_msg(f"{c.title if c else cid}: cancelled queued {t.label} (refunded §{t.cost:.0f}M).")
        else:
            # running task aborted — funds already spent
            self.system_msg(f"{c.title if c else cid}: aborted in-progress {t.label} (no refund).")
            self._promote(cid)
        self._sync_task_mirrors()
        return {"ok": True}

    def _sync_task_mirrors(self):
        for c in self.contracts:
            run = self._running_for(c.id)
            c.active_task = run.to_dict(self.sim_time) if run else None
            c.queue = [t.to_dict(self.sim_time) for t in self.tasks
                       if t.contract_id == c.id and t.status == "PENDING"]

    def _process_schedule(self):
        """Advance scheduled tasks; complete finished ones; promote queues."""
        from .contracts import ContractStatus
        done = [t for t in self.tasks
                if t.status == "RUNNING" and t.end_time is not None and self.sim_time >= t.end_time]
        for t in done:
            self.tasks.remove(t)
            c = self.contract_by_id(t.contract_id)
            if c:
                if t.kind == "OP":
                    self._complete_op(c, t.op)
                elif t.kind == "CORRECTION":
                    self._complete_correction(c, t.issue_id)
            self._promote(t.contract_id)

        self._sync_task_mirrors()

        # Window-miss detection (only when nothing is running/queued for the craft)
        for c in self.contracts:
            busy = c.active_task or c.queue
            if (c.status in (ContractStatus.PLANNED, ContractStatus.VEHICLE_ASSIGNED,
                             ContractStatus.READY)
                    and c.planned_launch_time is not None
                    and not busy and not c.window_missed
                    and self.sim_time > c.planned_launch_time + DAY):
                c.window_missed = True
                c.design_ok = False
                if c.status == ContractStatus.READY:
                    c.status = ContractStatus.VEHICLE_ASSIGNED
                self.system_msg(f"{c.title}: LAUNCH WINDOW MISSED — re-plan to a later window.")

        self._recompute_conflicts()

    # ── Launch-slot conflicts (shared across all players) ─────────────────────

    def _holds_slot(self, c) -> bool:
        from .contracts import ContractStatus
        return (c.launch_site_id is not None and c.planned_launch_time is not None
                and c.status in (ContractStatus.VEHICLE_ASSIGNED, ContractStatus.READY))

    def _recompute_conflicts(self):
        from .contracts import PAD_TURNAROUND_DAYS
        holders = [c for c in self.contracts if self._holds_slot(c)]
        for c in holders:
            c.conflict = None
        win = PAD_TURNAROUND_DAYS * DAY
        for i, a in enumerate(holders):
            for b in holders[i + 1:]:
                if (a.launch_site_id == b.launch_site_id
                        and abs(a.planned_launch_time - b.planned_launch_time) < win):
                    a.conflict = {"withId": b.id, "withTitle": b.title,
                                  "withOwner": b.owner_name or "another player",
                                  "siteId": a.launch_site_id}
                    b.conflict = {"withId": a.id, "withTitle": a.title,
                                  "withOwner": a.owner_name or "another player",
                                  "siteId": b.launch_site_id}

    def _complete_op(self, c, op):
        from .contracts import (ContractStatus, OP_LABELS, evaluate_design,
                                run_test, Issue, OP_COSTS)
        from sim.launch_sites import SITES_BY_ID
        sc = self.craft_by_name(c.craft_name)
        site = SITES_BY_ID.get(c.launch_site_id) if c.launch_site_id else None
        if not sc or not site:
            return
        if op == "DRY_RUN":
            c.dry_run_count += 1
            res = evaluate_design(c, self.craft_spec(sc), site,
                                  c.planned_launch_time, c.dry_run_count)
            c.last_dry_run = res
            c.design_ok = res["ready"]
            c.status = ContractStatus.READY if c.design_ok else ContractStatus.VEHICLE_ASSIGNED
            tag = "design OK" if c.design_ok else f"{res['fails']} blocking fault(s)"
            c.op_log.append({"op": op, "label": OP_LABELS[op], "cost": OP_COSTS[op],
                             "summary": tag, "date": seconds_to_date(self.sim_time)})
            self.system_msg(f"{c.title}: Design Review complete — {tag}.")
            return
        attempt = sum(1 for e in c.op_log if e.get("op") == op) + 1
        res = run_test(op, c, self.craft_spec(sc), attempt)
        c.issues = [i for i in c.issues if not (i.op == op and not i.corrected)]
        for iss in res["issues"]:
            if not any(i.id == iss.id and i.corrected for i in c.issues):
                c.issues.append(iss)
        if op not in c.ops_run:
            c.ops_run.append(op)
        c.vehicle_wear = min(100.0, c.vehicle_wear + res["wear"])
        if res["wear"] > 0 and not any(i.id == "STATIC_BURN:Refurbishment" and not i.corrected
                                       for i in c.issues):
            c.issues.append(Issue("STATIC_BURN:Refurbishment", "STATIC_BURN", "Refurbishment",
                                  f"Engine refurbishment to clear {c.vehicle_wear:.0f}% wear.",
                                  0.0, round(c.vehicle_wear * 2, 0), max(3, c.vehicle_wear / 2)))
        found = len(res["issues"])
        summary = f"{found} finding(s)" if found else "no findings"
        c.op_log.append({"op": op, "label": OP_LABELS[op], "cost": OP_COSTS[op],
                         "summary": summary, "note": res.get("note", ""),
                         "date": seconds_to_date(self.sim_time)})
        if c.status == ContractStatus.READY and not c.design_ok:
            c.status = ContractStatus.VEHICLE_ASSIGNED
        self.system_msg(f"{c.title}: {OP_LABELS[op]} complete — {summary}. "
                        f"Mission risk {c.mission_risk()*100:.0f}%.")

    def _complete_correction(self, c, issue_id):
        iss = next((i for i in c.issues if i.id == issue_id and not i.corrected), None)
        if not iss:
            return
        iss.corrected = True
        if iss.category == "Refurbishment":
            c.vehicle_wear = 0.0
        self.system_msg(f"{c.title}: repair complete — '{iss.category}' resolved. "
                        f"Mission risk {c.mission_risk()*100:.0f}%.")

    def launch_contract(self, cid: str) -> dict:
        import copy, random
        from .contracts import ContractStatus, LAUNCH_COST
        c = self.contract_by_id(cid)
        if not c or c.status != ContractStatus.READY or not c.design_ok:
            return {"error": "pass a design review (dry run) with no blocking faults first"}
        if c.active_task or c.queue:
            return {"error": "operations still in the queue — wait or cancel them first"}
        if c.window_missed:
            return {"error": "launch window missed — re-plan first"}
        if c.conflict:
            return {"error": f"slot conflict with {c.conflict['withTitle']} "
                             f"({c.conflict['withOwner']}) — one of you must move the slot"}
        sc = self.craft_by_name(c.craft_name)
        if not sc or not c.chosen_window:
            return {"error": "craft/window missing"}
        if self.funds < LAUNCH_COST:
            return {"error": f"insufficient funds for launch ops (need §{LAUNCH_COST:.0f}M)"}
        self.funds -= LAUNCH_COST
        c.spent += LAUNCH_COST

        # ── Congressional budget close-out ──
        overrun = max(0.0, c.spent - c.budget)
        if overrun > 0:
            self.budget_penalty += overrun
            self.congress_note = (f"{c.title} overran its §{c.budget:.0f}M allotment by "
                                  f"§{overrun:.0f}M — next mission's budget will be cut.")
            self.system_msg(f"CONGRESS: {c.title} OVER BUDGET by §{overrun:.0f}M "
                            f"(spent §{c.spent:.0f}M / §{c.budget:.0f}M). Penalty applied to next mission.")
        else:
            self.system_msg(f"CONGRESS: {c.title} on budget "
                            f"(§{c.spent:.0f}M / §{c.budget:.0f}M).")

        # Resolve mission risk: each uncorrected issue rolls its failure chance.
        risk = c.mission_risk()
        triggered = []
        for iss in c.open_issues():
            if iss.failure_chance > 0 and random.random() < iss.failure_chance:
                triggered.append(iss)
        # Hidden-risk roll (untested areas)
        hidden_hit = random.random() < max(0.0, risk - sum(i.failure_chance for i in c.open_issues()))

        flying = copy.deepcopy(sc)
        wins = hohmann_windows(self.bodies[c.origin], self.bodies[c.destination],
                               self.bodies["Sun"], self.sim_time, n_windows=5)
        win = wins[0] if wins else None
        if win is None:
            self.funds += LAUNCH_COST
            return {"error": "no launch window"}
        mission = self.mc.create_mission(flying, c.origin, c.destination, win)
        c.mission_name = mission.name
        c.status = ContractStatus.LAUNCHED
        c.conflict = None
        self._recompute_conflicts()   # this contract released its slot

        if triggered or hidden_hit:
            who = triggered[0].category if triggered else "an un-inspected subsystem"
            c.outcome = f"ANOMALY: {who} failure in flight — partial reward."
            payout = int(c.reward * 0.35)
            self.system_msg(f"LAUNCH: {c.title} away — IN-FLIGHT ANOMALY ({who}). "
                            f"Partial payout §{payout}M.")
        else:
            c.outcome = "NOMINAL: all systems performed within limits — full reward."
            payout = c.reward
            self.system_msg(f"LAUNCH: {c.title} away from {c.launch_site_id}. "
                            f"NOMINAL — reward §{payout}M. Mission {mission.name} active.")
        self.funds += payout
        return {"ok": True, "mission": mission.name, "outcome": c.outcome}
