"""
Spacecraft assembly: flat parts list with decoupler-defined staging.

A rocket is a single ordered list of Module objects (payload at index 0,
first-stage booster at the end).  Any DECOUPLER module in the list marks a
stage boundary.  Stages are computed on-the-fly from the parts list —
there is no manual stage management.

Firing order: the group of parts below the lowest decoupler fires first
(stage 0), then the next group up, etc.  This matches real-world convention.
"""

import math
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

G0 = 9.80665  # standard gravity for Isp calculations


class ModuleType(Enum):
    COMMAND    = "Command"
    ENGINE     = "Engine"
    FUEL_TANK  = "Fuel Tank"
    PAYLOAD    = "Payload"
    SOLAR_PANEL= "Solar Panel"
    COMMS      = "Comms Array"
    DECOUPLER  = "Decoupler"


@dataclass
class Module:
    name: str
    module_type: ModuleType
    dry_mass: float           # kg
    description: str = ""

    # Engine-specific
    thrust: float = 0.0       # N
    isp: float = 0.0          # s
    min_throttle: float = 0.0
    max_throttle: float = 1.0

    # Tank-specific
    fuel_capacity: float = 0.0   # kg propellant

    # Power
    power_output: float = 0.0    # W
    power_draw: float = 0.0      # W

    # Crew / life support
    crew_capacity: int = 0
    life_support_mass: float = 0.0  # kg per crew member per year


# ── SpacecraftStage — computed view over a group of modules ──────────────────

class SpacecraftStage:
    """A computed, read-only view of a group of modules between two decouplers."""

    def __init__(self, modules: list[Module]):
        self.modules = modules

    @property
    def engines(self) -> list[Module]:
        return [m for m in self.modules if m.module_type == ModuleType.ENGINE]

    @property
    def tanks(self) -> list[Module]:
        return [m for m in self.modules if m.module_type == ModuleType.FUEL_TANK]

    @property
    def total_thrust(self) -> float:
        return sum(e.thrust for e in self.engines)

    @property
    def effective_isp(self) -> float:
        """Mass-flow-weighted average Isp across all engines in this stage."""
        engines = self.engines
        if not engines:
            return 0.0
        total_mdot = sum(e.thrust / (e.isp * G0) for e in engines if e.isp > 0)
        if total_mdot == 0:
            return 0.0
        return sum(e.thrust for e in engines) / (total_mdot * G0)

    @property
    def propellant_mass(self) -> float:
        return sum(t.fuel_capacity for t in self.tanks)

    @property
    def dry_mass(self) -> float:
        return sum(m.dry_mass for m in self.modules)

    @property
    def wet_mass(self) -> float:
        return self.dry_mass + self.propellant_mass


# ── Spacecraft ────────────────────────────────────────────────────────────────

@dataclass
class Spacecraft:
    """
    A rocket described as a flat, ordered list of modules.
    Index 0 = top of rocket (payload / command capsule).
    Last index = bottom (first-stage boosters).
    DECOUPLER modules between groups define staging boundaries.
    """
    name: str
    parts: list[Module] = field(default_factory=list)

    # Runtime state
    position: tuple[float, float] = (0.0, 0.0)
    velocity: tuple[float, float] = (0.0, 0.0)
    fuel_remaining: float = 0.0
    current_stage_idx: int = 0       # index into compute_stages() firing order
    mission_name: str = ""
    origin: str = "Earth"
    destination: str = ""
    status: str = "Assembled"
    time_launched: float = 0.0
    trajectory_points: list[tuple[float, float]] = field(default_factory=list)

    def __post_init__(self):
        stages = self.compute_stages()
        if stages:
            # First stage to fire = groups[-1] in parts order = groups[0] firing order
            self.fuel_remaining = stages[0].propellant_mass

    # ── Staging ───────────────────────────────────────────────────────────────

    def compute_stages(self) -> list[SpacecraftStage]:
        """
        Split parts at DECOUPLER modules and return stages in firing order
        (first group to fire at index 0 = bottom section of the rocket).
        Decouplers themselves are excluded from stage module lists.
        """
        groups: list[list[Module]] = []
        current: list[Module] = []

        # Walk bottom-to-top (reversed) so the first group collected is the
        # bottom of the rocket = first to fire.
        for part in reversed(self.parts):
            if part.module_type == ModuleType.DECOUPLER:
                if current:
                    groups.append(current)
                    current = []
            else:
                current.append(part)
        if current:
            groups.append(current)

        return [SpacecraftStage(g) for g in groups]

    @property
    def stages(self) -> list[SpacecraftStage]:
        """Alias for mission.py compatibility."""
        return self.compute_stages()

    @property
    def stage_count(self) -> int:
        return len(self.compute_stages())

    # ── Mass / performance ────────────────────────────────────────────────────

    @property
    def total_mass(self) -> float:
        return sum(
            m.dry_mass + m.fuel_capacity + m.life_support_mass * m.crew_capacity
            for m in self.parts
            if m.module_type != ModuleType.DECOUPLER
        )

    @property
    def payload_mass(self) -> float:
        """Non-propulsive mass carried throughout the whole flight."""
        return sum(
            m.dry_mass + m.life_support_mass * m.crew_capacity
            for m in self.parts
            if m.module_type in (ModuleType.COMMAND, ModuleType.PAYLOAD,
                                  ModuleType.SOLAR_PANEL, ModuleType.COMMS)
        )

    @property
    def extra_modules(self) -> list[Module]:
        """Non-propulsive parts (command, payload, solar, comms) — for UI display."""
        return [m for m in self.parts
                if m.module_type in (ModuleType.COMMAND, ModuleType.PAYLOAD,
                                      ModuleType.SOLAR_PANEL, ModuleType.COMMS)]

    @property
    def crew(self) -> int:
        return sum(m.crew_capacity for m in self.parts
                   if m.module_type != ModuleType.DECOUPLER)

    def stage_delta_v(self, firing_idx: int) -> float:
        """
        Tsiolkovsky ΔV for one stage (firing_idx 0 = first to fire).
        Payload for this stage = mass of all stages that fire later (higher indices).
        """
        stages = self.compute_stages()
        if firing_idx >= len(stages):
            return 0.0
        s = stages[firing_idx]
        if s.effective_isp == 0:
            return 0.0
        # "above" mass = stages that fire after this one
        above = sum(st.wet_mass for st in stages[firing_idx + 1:])
        m0 = s.wet_mass + above
        mf = s.dry_mass  + above
        if mf <= 0 or m0 <= mf:
            return 0.0
        return s.effective_isp * G0 * math.log(m0 / mf)

    @property
    def total_delta_v(self) -> float:
        stages = self.compute_stages()
        return sum(self.stage_delta_v(i) for i in range(len(stages)))

    # ── Current-stage runtime properties ─────────────────────────────────────

    @property
    def current_stage(self) -> Optional[SpacecraftStage]:
        stages = self.compute_stages()
        if self.current_stage_idx < len(stages):
            return stages[self.current_stage_idx]
        return None

    @property
    def current_dry_mass(self) -> float:
        stages = self.compute_stages()
        if self.current_stage_idx >= len(stages):
            return 0.0
        above = sum(st.wet_mass for st in stages[self.current_stage_idx + 1:])
        return stages[self.current_stage_idx].dry_mass + above

    @property
    def current_wet_mass(self) -> float:
        return self.current_dry_mass + self.fuel_remaining

    @property
    def thrust(self) -> float:
        s = self.current_stage
        return s.total_thrust if s else 0.0

    @property
    def isp(self) -> float:
        s = self.current_stage
        return s.effective_isp if s else 0.0

    @property
    def twr(self) -> float:
        wet = self.current_wet_mass
        return self.thrust / (wet * 9.81) if wet > 0 else 0.0

    @property
    def remaining_delta_v(self) -> float:
        s = self.current_stage
        if s is None or s.effective_isp == 0:
            return 0.0
        m0 = self.current_wet_mass
        mf = self.current_dry_mass
        if mf <= 0 or m0 <= mf:
            return 0.0
        cur_dv = (s.effective_isp * G0 * math.log(m0 / mf)
                  * (self.fuel_remaining / max(s.propellant_mass, 1)))
        future_dv = sum(self.stage_delta_v(i)
                        for i in range(self.current_stage_idx + 1,
                                       len(self.compute_stages())))
        return cur_dv + future_dv

    # ── Actions ───────────────────────────────────────────────────────────────

    def burn(self, delta_v: float) -> bool:
        """Consume propellant for delta_v. Returns False if insufficient."""
        s = self.current_stage
        if s is None or s.effective_isp == 0:
            return False
        m0 = self.current_wet_mass
        mf = m0 / math.exp(delta_v / (s.effective_isp * G0))
        fuel_used = m0 - mf
        if fuel_used > self.fuel_remaining + 0.1:
            return False
        self.fuel_remaining = max(0.0, self.fuel_remaining - fuel_used)
        return True

    def separate_stage(self):
        stages = self.compute_stages()
        if self.current_stage_idx < len(stages) - 1:
            self.current_stage_idx += 1
            self.fuel_remaining = stages[self.current_stage_idx].propellant_mass

    def summary(self) -> str:
        stages = self.compute_stages()
        return "\n".join([
            f"  Craft    : {self.name}",
            f"  Parts    : {len([p for p in self.parts if p.module_type != ModuleType.DECOUPLER])}",
            f"  Stages   : {len(stages)}",
            f"  Mass     : {self.total_mass/1000:.1f} t",
            f"  Total dV : {self.total_delta_v:.0f} m/s",
            f"  TWR      : {self.twr:.2f}",
            f"  Crew     : {self.crew}",
            f"  Status   : {self.status}",
        ])


# ── Legacy catalog for panels.py / main.py compat ────────────────────────────
# (kept small; the real catalog lives in sim/module_db.py)

MODULE_CATALOG: list[Module] = []   # populated below
CATALOG_BY_NAME: dict[str, Module] = {}

def _populate_legacy_catalog():
    try:
        from sim.module_db import build_flat_catalog
        cat = build_flat_catalog()
        MODULE_CATALOG.extend(cat.values())
        CATALOG_BY_NAME.update(cat)
    except Exception:
        pass

_populate_legacy_catalog()
