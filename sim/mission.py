"""Mission state machine, mission control, active spacecraft tracking."""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from .bodies import CelestialBody, G
from .craft import Spacecraft
from .physics import orbit_from_state, vec_add, vec_scale, vec_mag, vec_norm, vec_sub
from .transfer import TransferWindow, seconds_to_date

DAY = 86400.0


class MissionPhase(Enum):
    PLANNING   = "Planning"
    LAUNCH     = "Launch"
    PARKING    = "Parking Orbit"
    TRANSFER   = "Heliocentric Transfer"
    ARRIVAL    = "Arrival Burn"
    ORBIT      = "Target Orbit"
    LANDED     = "Landed"
    ABORTED    = "Aborted"
    COMPLETE   = "Complete"


@dataclass
class MissionEvent:
    time: float
    description: str
    phase: MissionPhase

    @property
    def time_str(self) -> str:
        return seconds_to_date(self.time)


@dataclass
class Mission:
    name: str
    spacecraft: Spacecraft
    origin: CelestialBody
    destination: CelestialBody
    window: TransferWindow
    created_at: float                        # sim time

    phase: MissionPhase = MissionPhase.PLANNING
    events: list[MissionEvent] = field(default_factory=list)
    log: list[str] = field(default_factory=list)

    # Set at launch
    launch_time: float = 0.0

    def log_event(self, t: float, msg: str, phase: Optional[MissionPhase] = None):
        p = phase or self.phase
        self.events.append(MissionEvent(t, msg, p))
        self.log.append(f"[{seconds_to_date(t)}] {msg}")

    def advance_phase(self, t: float, new_phase: MissionPhase):
        self.phase = new_phase
        self.log_event(t, f"Phase transition → {new_phase.value}")

    @property
    def is_active(self) -> bool:
        return self.phase not in (MissionPhase.COMPLETE, MissionPhase.ABORTED)

    @property
    def elapsed_days(self) -> float:
        return (self.launch_time - self.created_at) / DAY if self.launch_time else 0.0

    def status_lines(self) -> list[str]:
        sc = self.spacecraft
        lines = [
            f"{self.name}",
            f"  Phase: {self.phase.value}",
            f"  {sc.origin} → {sc.destination}",
            f"  dV rem: {sc.remaining_delta_v:.0f} m/s",
            f"  Fuel:   {sc.fuel_remaining/1000:.1f} t",
            f"  Depart: {self.window.departure_date_str}",
            f"  Arrive: {self.window.arrival_date_str}",
        ]
        return lines

    def next_attention(self, now: float) -> "AttentionInfo":
        """
        Compute when this mission next needs operator attention, the reason,
        and an urgency level. Used by the Command Center listing.
        """
        # Aborted missions always need attention immediately.
        if self.phase == MissionPhase.ABORTED:
            return AttentionInfo(now, "MISSION ABORTED — review required",
                                 Urgency.CRITICAL)
        if self.phase == MissionPhase.COMPLETE:
            return AttentionInfo(float("inf"), "Mission complete",
                                 Urgency.NONE)

        sc = self.spacecraft

        # Fuel / delta-v shortfall flags an issue regardless of phase.
        if sc.remaining_delta_v < self.window.dv_total * 0.5 and self.phase in (
                MissionPhase.PLANNING, MissionPhase.PARKING):
            return AttentionInfo(now, "Insufficient ΔV for planned burn",
                                 Urgency.CRITICAL)

        # Phase-driven next event.
        if self.phase in (MissionPhase.PLANNING, MissionPhase.LAUNCH,
                          MissionPhase.PARKING):
            t_event = self.window.departure_time
            label = "Departure burn"
        elif self.phase in (MissionPhase.TRANSFER, MissionPhase.ARRIVAL):
            t_event = self.window.arrival_time
            label = "Arrival / capture burn"
        elif self.phase in (MissionPhase.ORBIT, MissionPhase.LANDED):
            return AttentionInfo(float("inf"), "Stable — monitoring",
                                 Urgency.NONE)
        else:
            t_event = self.window.departure_time
            label = "Next maneuver"

        dt = t_event - now
        if dt < 0:
            # Event window has passed but phase hasn't advanced — needs attention.
            return AttentionInfo(now, f"{label} OVERDUE", Urgency.CRITICAL)
        elif dt < 2 * DAY:
            urg = Urgency.SOON
        elif dt < 30 * DAY:
            urg = Urgency.UPCOMING
        else:
            urg = Urgency.NOMINAL
        return AttentionInfo(t_event, label, urg)


class Urgency(Enum):
    CRITICAL = "CRITICAL"   # needs attention ASAP (red)
    SOON     = "SOON"       # within ~2 days (orange)
    UPCOMING = "UPCOMING"   # within ~30 days (yellow)
    NOMINAL  = "NOMINAL"    # far out (green)
    NONE     = "NONE"       # nothing pending (dim)


@dataclass
class AttentionInfo:
    time: float          # sim time of next event (inf = none)
    label: str           # what the event is
    urgency: "Urgency"

    def countdown_str(self, now: float) -> str:
        if self.time == float("inf"):
            return "—"
        dt = self.time - now
        if dt < 0:
            return "OVERDUE"
        days = dt / DAY
        if days < 1:
            hours = dt / 3600
            return f"in {hours:.0f}h"
        if days < 60:
            return f"in {days:.0f}d"
        return f"in {days/365.25:.1f}y"


class MissionControl:
    """Central hub managing all missions and spacecraft."""

    def __init__(self, solar_system: dict[str, CelestialBody], sim_time: float = 0.0):
        self.solar_system = solar_system
        self.sim_time = sim_time
        self.missions: list[Mission] = []
        self.mission_counter = 0
        self.event_log: list[str] = []

    # ── Mission creation ─────────────────────────────────────────────

    def create_mission(self, spacecraft: Spacecraft, origin_name: str,
                       dest_name: str, window: TransferWindow) -> Mission:
        self.mission_counter += 1
        name = f"M{self.mission_counter:03d}-{dest_name[:3].upper()}"
        spacecraft.mission_name = name
        spacecraft.origin = origin_name
        spacecraft.destination = dest_name
        m = Mission(
            name=name,
            spacecraft=spacecraft,
            origin=self.solar_system[origin_name],
            destination=self.solar_system[dest_name],
            window=window,
            created_at=self.sim_time,
        )
        m.log_event(self.sim_time, f"Mission {name} created: {origin_name} → {dest_name}")
        self.missions.append(m)
        self._log(f"NEW MISSION: {name}")
        return m

    # ── Simulation step ──────────────────────────────────────────────

    def step(self, dt: float):
        self.sim_time += dt
        t = self.sim_time
        for m in self.missions:
            if not m.is_active:
                continue
            self._update_mission(m, t, dt)

    def _update_mission(self, m: Mission, t: float, dt: float):
        sc = m.spacecraft
        w = m.window

        if m.phase == MissionPhase.PLANNING:
            # Auto-launch when within 1 day of window
            if t >= w.departure_time - DAY:
                self._launch(m, t)

        elif m.phase == MissionPhase.LAUNCH:
            # Immediate (simplified: no ascent simulation)
            m.advance_phase(t, MissionPhase.PARKING)
            self._set_parking_orbit(m, t)

        elif m.phase == MissionPhase.PARKING:
            # Execute departure burn at window time
            if t >= w.departure_time:
                self._execute_departure_burn(m, t)

        elif m.phase == MissionPhase.TRANSFER:
            # Propagate position along transfer orbit
            self._propagate_spacecraft(m, t, dt)
            # Check arrival
            if t >= w.arrival_time - dt/2:
                self._execute_arrival_burn(m, t)

        elif m.phase == MissionPhase.ARRIVAL:
            m.advance_phase(t, MissionPhase.ORBIT)
            m.log_event(t, f"Captured into {m.destination.name} orbit.")
            sc.status = "Orbiting"

        elif m.phase == MissionPhase.ORBIT:
            self._propagate_spacecraft(m, t, dt)

    def _launch(self, m: Mission, t: float):
        sc = m.spacecraft
        dv_launch = 9300  # ~9.3 km/s to LEO for Earth-like
        origin = m.origin
        if origin.name != "Earth":
            dv_launch = origin.surface_gravity / 9.81 * 9300
        if not sc.burn(dv_launch):
            m.advance_phase(t, MissionPhase.ABORTED)
            m.log_event(t, "ABORT: insufficient delta-v for launch.")
            return
        m.launch_time = t
        m.advance_phase(t, MissionPhase.LAUNCH)
        m.log_event(t, f"Launch from {m.origin.name}. dV used: {dv_launch:.0f} m/s")

    def _set_parking_orbit(self, m: Mission, t: float):
        origin = m.origin
        r_park = origin.radius + 200_000
        # Position at origin's location in solar system
        ox, oy = origin.position_at(t)
        ovx, ovy = origin.velocity_at(t)
        # Circular parking orbit velocity (perpendicular to radial)
        v_park = math.sqrt(G * origin.mass / r_park)
        # Spacecraft inherits planet's heliocentric velocity + parking orbit velocity
        # (Simplified: parking orbit velocity added tangentially to Sun direction)
        angle = math.atan2(oy, ox) + math.pi / 2  # tangential to solar orbit
        m.spacecraft.position = (ox + r_park * math.cos(angle + math.pi/2),
                                  oy + r_park * math.sin(angle + math.pi/2))
        m.spacecraft.velocity = (ovx + v_park * math.cos(angle),
                                  ovy + v_park * math.sin(angle))
        m.log_event(t, f"Parking orbit around {m.origin.name} at {r_park/1000:.0f} km altitude.")

    def _execute_departure_burn(self, m: Mission, t: float):
        w = m.window
        sc = m.spacecraft
        if not sc.burn(w.dv_departure):
            m.advance_phase(t, MissionPhase.ABORTED)
            m.log_event(t, f"ABORT: insufficient dV for departure burn ({w.dv_departure:.0f} m/s needed).")
            return

        # Set spacecraft onto heliocentric transfer trajectory
        origin = m.origin
        dest = m.destination
        sun = [b for b in self.solar_system.values() if b.parent is None][0]

        r1 = origin.semi_major_axis
        r2 = dest.semi_major_axis
        ox, oy = origin.position_at(t)
        ovx, ovy = origin.velocity_at(t)

        # Transfer orbit: tangential burn from r1
        mu_sun = G * sun.mass
        a_transfer = (r1 + r2) / 2
        v_transfer = math.sqrt(mu_sun * (2/r1 - 1/a_transfer))
        # Direction: tangential to origin orbit
        angle = math.atan2(oy, ox) + math.pi / 2
        sc.position = (ox, oy)
        sc.velocity = (v_transfer * math.cos(angle), v_transfer * math.sin(angle))
        sc.status = "In Transfer"
        sc.trajectory_points = [sc.position]

        m.advance_phase(t, MissionPhase.TRANSFER)
        m.log_event(t, f"Departure burn complete. dV={w.dv_departure:.0f} m/s. En route to {dest.name}.")

    def _execute_arrival_burn(self, m: Mission, t: float):
        w = m.window
        sc = m.spacecraft
        if not sc.burn(w.dv_arrival):
            m.log_event(t, "WARNING: insufficient dV for arrival capture. Flyby.")
            sc.status = "Flyby"
        else:
            sc.status = "Captured"
        # Snap spacecraft to destination position
        dest = m.destination
        dx, dy = dest.position_at(t)
        sc.position = (dx, dy)
        m.advance_phase(t, MissionPhase.ARRIVAL)

    def _propagate_spacecraft(self, m: Mission, t: float, dt: float):
        sc = m.spacecraft
        if m.phase == MissionPhase.TRANSFER:
            # Simple Keplerian propagation along transfer ellipse
            sun = [b for b in self.solar_system.values() if b.parent is None][0]
            mu = G * sun.mass
            frac = (t - m.window.departure_time) / m.window.transfer_duration
            frac = max(0.0, min(1.0, frac))

            origin = m.origin
            dest = m.destination
            r1 = origin.semi_major_axis
            r2 = dest.semi_major_axis
            a = (r1 + r2) / 2

            # Departure position angle
            dep_pos = origin.position_at(m.window.departure_time)
            dep_angle = math.atan2(dep_pos[1], dep_pos[0])

            # Parametric half-ellipse interpolation
            # True anomaly goes from 0 to pi along transfer
            nu = frac * math.pi
            e = (r2 - r1) / (r2 + r1)
            r = a * (1 - e**2) / (1 + e * math.cos(nu))
            theta = dep_angle + nu  # approximate
            sc.position = (r * math.cos(theta), r * math.sin(theta))

            if len(sc.trajectory_points) < 500:
                sc.trajectory_points.append(sc.position)

    # ── Helpers ──────────────────────────────────────────────────────

    def _log(self, msg: str):
        self.event_log.append(f"[{seconds_to_date(self.sim_time)}] {msg}")
        if len(self.event_log) > 200:
            self.event_log = self.event_log[-200:]

    @property
    def active_missions(self) -> list[Mission]:
        return [m for m in self.missions if m.is_active]

    @property
    def completed_missions(self) -> list[Mission]:
        return [m for m in self.missions if not m.is_active]

    def mission_by_name(self, name: str) -> Optional[Mission]:
        return next((m for m in self.missions if m.name == name), None)
