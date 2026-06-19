"""
Mission contracts, scheduled operations, and the launch economy.

Pipeline:
  AVAILABLE → ACCEPTED → PLANNED → VEHICLE_ASSIGNED → READY → LAUNCHED

Nothing is instant. Every test operation and every repair is a SCHEDULED TASK
that runs in real sim-time: you commit the funds when you schedule it, then it
progresses as the mission clock advances and applies its effect on completion.
A contract can run only one task at a time (a pad is serial).

Each surfaced ISSUE mirrors a real aerospace complication and carries a realistic
resolution time (days→weeks). You may schedule a CORRECTION (costs money + the
real time to fix) or fly with it (each carries a % chance of striking in flight).

Congressional budget: accepting a contract grants an allotment. Overspending it
by launch incurs a penalty that shrinks the *next* mission's allotment.
"""

from __future__ import annotations
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from sim.transfer import hohmann_windows, mission_delta_v_budget, seconds_to_date
from sim.launch_sites import SITES_BY_ID, LaunchSite
from sim.weather import simulator as weather

DAY = 86400.0

START_FUNDS  = 1000.0
LAUNCH_COST  = 50.0
LAUNCH_PREP_DAYS = 2.0     # terminal-count / range prep
BASE_HIDDEN  = 0.30
WEAR_PER_BURN = 14.0
BUDGET_FACTOR = 1.4        # allotment = reward * factor
MIN_BUDGET = 80.0
PAD_TURNAROUND_DAYS = 3.0  # exclusion window around a launch slot on one pad
MAX_SCHEDULED_LAUNCHES = 5 # per player

OP_COSTS = {
    "DRY_RUN":        5.0,
    "SYSTEMS_TEST":  15.0,
    "WET_RUN":       40.0,
    "STATIC_BURN":   60.0,
    "ASTRO_TRAINING":20.0,
}

# Realistic durations (days) for each scheduled operation
OP_DURATION_DAYS = {
    "DRY_RUN":         1.0,
    "SYSTEMS_TEST":    3.0,
    "WET_RUN":         4.0,
    "STATIC_BURN":     6.0,
    "ASTRO_TRAINING": 21.0,
}

OP_LABELS = {
    "DRY_RUN":        "Design Review",
    "SYSTEMS_TEST":   "Systems Test",
    "WET_RUN":        "Wet Dress Rehearsal",
    "STATIC_BURN":    "Static Fire",
    "ASTRO_TRAINING": "Astronaut Training",
}

RISK_AREAS = ["SYSTEMS_TEST", "WET_RUN", "STATIC_BURN"]


class ContractStatus(str, Enum):
    AVAILABLE        = "AVAILABLE"
    ACCEPTED         = "ACCEPTED"
    PLANNED          = "PLANNED"
    VEHICLE_ASSIGNED = "VEHICLE_ASSIGNED"
    READY            = "READY"
    LAUNCHED         = "LAUNCHED"


@dataclass
class ScheduledTask:
    id: str
    contract_id: str
    kind: str             # "OP" | "CORRECTION"
    label: str
    cost: float
    duration_days: float
    op: Optional[str] = None
    issue_id: Optional[str] = None
    status: str = "PENDING"          # "PENDING" | "RUNNING"
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    def start(self, now: float):
        self.status = "RUNNING"
        self.start_time = now
        self.end_time = now + self.duration_days * DAY

    def to_dict(self, now: float) -> dict:
        if self.status == "RUNNING" and self.start_time is not None:
            span = max(1.0, self.end_time - self.start_time)
            prog = max(0.0, min(1.0, (now - self.start_time) / span))
            remaining = max(0.0, (self.end_time - now) / DAY)
        else:
            prog, remaining = 0.0, self.duration_days
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "cost": round(self.cost, 1),
            "durationDays": round(self.duration_days, 1),
            "status": self.status,
            "progress": round(prog, 3),
            "remainingDays": round(remaining, 1),
            "op": self.op,
            "issueId": self.issue_id,
        }


@dataclass
class Issue:
    id: str
    op: str
    category: str
    description: str
    failure_chance: float
    correction_cost: float
    correction_days: float
    corrected: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id, "op": self.op, "category": self.category,
            "description": self.description,
            "failureChance": round(self.failure_chance, 3),
            "correctionCost": round(self.correction_cost, 1),
            "correctionDays": round(self.correction_days, 1),
            "corrected": self.corrected,
        }


@dataclass
class MissionContract:
    id: str
    title: str
    objective: str
    description: str
    origin: str
    destination: str
    required_delta_v: float
    required_crew: int
    payload_keywords: list[str]
    reward: int
    source: str

    status: ContractStatus = ContractStatus.AVAILABLE

    chosen_window: Optional[dict] = None
    craft_name: Optional[str] = None
    launch_site_id: Optional[str] = None
    planned_launch_time: Optional[float] = None

    design_ok: bool = False
    last_dry_run: Optional[dict] = None
    dry_run_count: int = 0

    issues: list[Issue] = field(default_factory=list)
    ops_run: list[str] = field(default_factory=list)
    op_log: list[dict] = field(default_factory=list)
    vehicle_wear: float = 0.0

    # ownership (which player accepted it)
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None

    # economy / scheduling
    budget: float = 0.0
    spent: float = 0.0
    active_task: Optional[dict] = None    # mirror of the running ScheduledTask
    queue: list = field(default_factory=list)   # mirror of pending tasks
    window_missed: bool = False
    conflict: Optional[dict] = None       # {withId, withTitle, withOwner, siteId}

    mission_name: Optional[str] = None
    outcome: Optional[str] = None

    def hidden_component(self) -> float:
        """Risk from subsystem areas not yet inspected by a test operation."""
        areas = list(RISK_AREAS)
        if self.required_crew > 0:
            areas.append("ASTRO_TRAINING")
        inspected = sum(1 for a in areas if a in self.ops_run)
        return BASE_HIDDEN * (len(areas) - inspected) / len(areas)

    def wear_risk(self) -> float:
        return min(0.30, self.vehicle_wear / 100.0 * 0.5)

    def mission_risk(self) -> float:
        surfaced = sum(i.failure_chance for i in self.issues if not i.corrected)
        return min(0.95, self.hidden_component() + surfaced + self.wear_risk())

    def open_issues(self) -> list[Issue]:
        return [i for i in self.issues if not i.corrected]

    def to_dict(self, now: float) -> dict:
        days_to_window = None
        if self.planned_launch_time is not None:
            days_to_window = round((self.planned_launch_time - now) / DAY, 1)
        return {
            "id": self.id, "title": self.title, "objective": self.objective,
            "description": self.description, "origin": self.origin,
            "destination": self.destination,
            "requiredDeltaV": round(self.required_delta_v),
            "requiredCrew": self.required_crew,
            "payloadKeywords": self.payload_keywords,
            "reward": self.reward, "source": self.source,
            "status": self.status.value,
            "chosenWindow": self.chosen_window,
            "craftName": self.craft_name,
            "launchSiteId": self.launch_site_id,
            "plannedLaunchTime": self.planned_launch_time,
            "plannedLaunchDate": seconds_to_date(self.planned_launch_time)
                                 if self.planned_launch_time else None,
            "daysToWindow": days_to_window,
            "windowMissed": self.window_missed,
            "designOk": self.design_ok,
            "dryRunCount": self.dry_run_count,
            "lastDryRun": self.last_dry_run,
            "issues": [i.to_dict() for i in self.issues],
            "opsRun": self.ops_run,
            "opLog": self.op_log[-6:],
            "vehicleWear": round(self.vehicle_wear, 1),
            "missionRisk": round(self.mission_risk(), 3),
            "budget": round(self.budget, 1),
            "spent": round(self.spent, 1),
            "activeTask": self.active_task,
            "queue": self.queue,
            "conflict": self.conflict,
            "ownerId": self.owner_id,
            "ownerName": self.owner_name,
            "missionName": self.mission_name,
            "outcome": self.outcome,
        }


# ── Generation ────────────────────────────────────────────────────────────────

_TEMPLATES = [
    dict(title="Mars Telecom Relay", objective="Comsat", destination="Mars",
         crew=0, reward=180,
         payload=["Comsat", "Relay", "Comms", "GEO", "Dish", "TDRSS"],
         desc="Deliver a communications relay to Mars orbit to support surface assets."),
    dict(title="Venus Atmospheric Orbiter", objective="Science Orbiter", destination="Venus",
         crew=0, reward=160,
         payload=["Science", "Spectrometer", "CRISM", "HiRISE", "NIRCam", "ACS", "Camera", "SAR"],
         desc="Insert a science platform into Venus orbit and return atmospheric data."),
    dict(title="Crewed Mars Flyby", objective="Crewed Flyby", destination="Mars",
         crew=2, reward=420,
         payload=["Capsule", "Dragon", "Orion", "Soyuz", "Hab", "Starliner", "Shenzhou", "Gaganyaan", "CM"],
         desc="Carry a crew of 2 on a free-return flyby of Mars. Crewed capsule required."),
    dict(title="Jupiter Science Probe", objective="Flyby Probe", destination="Jupiter",
         crew=0, reward=300,
         payload=["Science", "Suite", "Camera", "Probe"],
         desc="Send an instrumented probe to Jupiter. High-energy transfer."),
    dict(title="Mars Sample Lander", objective="Lander", destination="Mars",
         crew=0, reward=350,
         payload=["Lander", "Descent", "Sky Crane", "Hayabusa", "Sample"],
         desc="Land a sample-collection package on the Martian surface."),
]


def generate_contracts(bodies, sim_time, start_id, count=4):
    out = []
    sun, earth = bodies["Sun"], bodies["Earth"]
    for i in range(count):
        t = _TEMPLATES[i % len(_TEMPLATES)]
        dest = bodies[t["destination"]]
        budget = mission_delta_v_budget(earth, dest, sun)
        out.append(MissionContract(
            id=f"C{start_id + i:03d}",
            title=t["title"], objective=t["objective"], description=t["desc"],
            origin="Earth", destination=t["destination"],
            required_delta_v=budget["total_one_way"],
            required_crew=t["crew"], payload_keywords=t["payload"],
            reward=t["reward"], source="CONGRESS",
        ))
    return out


# ── Design review ─────────────────────────────────────────────────────────────

def evaluate_design(contract, craft_spec, site, launch_time, attempt):
    checks = []
    req, have = contract.required_delta_v, craft_spec["totalDeltaV"]
    margin = (have - req) / req if req > 0 else 1.0
    if have < req:
        checks.append(("Delta-V Budget", "FAIL",
                       f"Craft dV {have:,.0f} < required {req:,.0f} m/s",
                       "Add fuel/stages or fly a lighter payload."))
    elif margin < 0.08:
        checks.append(("Delta-V Budget", "WARN",
                       f"Thin margin {margin*100:.0f}% ({have:,.0f}/{req:,.0f})",
                       "Add dV margin for corrections."))
    else:
        checks.append(("Delta-V Budget", "PASS",
                       f"{have:,.0f} m/s vs {req:,.0f} (+{margin*100:.0f}%)", ""))

    twr = craft_spec["twr"]
    if twr < 1.05:
        checks.append(("Liftoff TWR", "FAIL", f"TWR {twr:.2f} below 1.05 - cannot lift off",
                       "Add first-stage thrust or cut mass."))
    elif twr < 1.2:
        checks.append(("Liftoff TWR", "WARN", f"Low TWR {twr:.2f}", "Raise toward 1.3."))
    else:
        checks.append(("Liftoff TWR", "PASS", f"TWR {twr:.2f}", ""))

    if contract.required_crew > 0:
        ok = craft_spec["crew"] >= contract.required_crew
        checks.append(("Crew Capacity", "PASS" if ok else "FAIL",
                       f"{craft_spec['crew']} crew" + ("" if ok else f" < required {contract.required_crew}"),
                       "" if ok else "Add a crewed capsule or habitat."))

    if contract.payload_keywords:
        blob = " ".join(craft_spec["partNames"]).lower()
        ok = any(k.lower() in blob for k in contract.payload_keywords)
        checks.append(("Payload Fit", "PASS" if ok else "FAIL",
                       "Required payload present" if ok else
                       f"Missing payload ({' / '.join(contract.payload_keywords[:3])})",
                       "" if ok else "Add a matching payload in Vehicle Assembly."))

    win_t = (contract.chosen_window or {}).get("departTime", launch_time)
    off_days = abs(launch_time - win_t) / DAY
    sev = "FAIL" if off_days > 20 else "WARN" if off_days > 3 else "PASS"
    checks.append(("Launch Window", sev, f"{off_days:.1f} d from optimal",
                   "" if sev == "PASS" else "Move the launch time onto the window."))

    cond = weather.conditions_at(site, launch_time)
    go, reasons = weather.is_go(site, cond)
    checks.append(("Weather Outlook", "PASS" if go else "WARN",
                   f"GO - {cond.sky_text}, {cond.wind_kt:.0f} kt" if go else f"NO-GO: {reasons[0]}",
                   "" if go else "Slip to a GO day or accept risk."))

    design_ok = not any(c[1] == "FAIL" for c in checks)
    return {
        "attempt": attempt, "ready": design_ok,
        "fails": sum(1 for c in checks if c[1] == "FAIL"),
        "warnings": sum(1 for c in checks if c[1] == "WARN"),
        "launchDate": seconds_to_date(launch_time), "siteId": site.id,
        "checks": [{"name": n, "severity": s, "message": m, "fix": f}
                   for (n, s, m, f) in checks],
    }


# ── Test operations (realistic complications + resolution times) ──────────────

# (category, description, failure_chance, correction_cost §M, correction_days)
_TEST_POOLS = {
    "SYSTEMS_TEST": [
        ("Avionics", "Flight computer single-event upset under vibration - board swap & revalidation.", 0.12, 22, 7),
        ("Telemetry", "S-band transponder output 2 dB low - unit replacement.", 0.08, 14, 5),
        ("Power", "Battery pack cell imbalance beyond spec - reconditioning.", 0.10, 18, 6),
    ],
    "WET_RUN": [
        ("Propellant", "LOX fill-and-drain valve fails to seat - valve removal & replacement.", 0.15, 28, 9),
        ("Pressurization", "Helium COPV pressure decay - composite tank inspection/replacement.", 0.18, 40, 14),
        ("GSE", "Ground umbilical quick-disconnect leak - seal replacement.", 0.07, 9, 3),
    ],
    "STATIC_BURN": [
        ("Engine", "Turbopump bearing spalling on engine 3 - engine removal & replacement.", 0.20, 60, 21),
        ("Combustion", "Chamber-pressure (pogo) oscillation - suppressor retrofit.", 0.16, 48, 16),
        ("TVC", "Gimbal actuator response lag - actuator replacement & recalibration.", 0.10, 30, 8),
    ],
    "ASTRO_TRAINING": [
        ("Crew", "Crew timeline overruns in a contingency sim - additional training cycle.", 0.10, 16, 10),
    ],
}


def run_test(op, contract, craft_spec, attempt):
    rng = random.Random(hash((contract.id, op, attempt)) & 0xFFFFFFFF)
    checks, new_issues, wear = [], [], 0.0
    for (cat, desc, chance, cost, days) in _TEST_POOLS.get(op, []):
        if rng.random() < 0.5:
            new_issues.append(Issue(f"{op}:{cat}", op, cat, desc, chance, cost, days))
            checks.append((cat, "WARN", desc))
        else:
            checks.append((cat, "PASS", f"{cat} checks nominal."))
    note = ""
    if op == "STATIC_BURN":
        wear = WEAR_PER_BURN
        note = f"Static fire consumed propellant and added {WEAR_PER_BURN:.0f}% engine wear."
    elif op == "ASTRO_TRAINING" and contract.required_crew == 0:
        note = "No crew assigned - training had limited value."
    return {"op": op, "label": OP_LABELS[op], "checks": [
        {"name": n, "severity": s, "message": m} for (n, s, m) in checks],
        "issues": new_issues, "wear": wear, "note": note}
