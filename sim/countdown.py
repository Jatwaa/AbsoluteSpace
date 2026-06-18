"""
Launch countdown state machine.

The countdown script is a sequence of timed events (negative seconds = before
T-0, positive = after).  Each event can:
  - Add a line to the comm log
  - Trigger an auto-hold (requires user to RESUME)
  - Mark a significant event that pauses the simulation

The controller is advanced by calling step(dt_sim) each frame.  It returns
a list of CountdownEvent objects that fired since the last step so the UI
can react to them.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable
import random


class CountdownPhase(Enum):
    PRECOUNT   = "Pre-terminal Count"
    PROPLOAD   = "Propellant Loading"
    TERMINAL   = "Terminal Countdown"
    AUTOSEQUENCE = "Auto-Sequence"
    IGNITION   = "Engine Start"
    LIFTOFF    = "LIFTOFF"
    MAXQ       = "Max-Q"
    MECO       = "MECO"
    STAGING    = "Stage Separation"
    FAIRING    = "Fairing Sep"
    ORBIT      = "Orbital Insertion"
    COMPLETE   = "Mission Complete"
    HOLD       = "HOLD"
    SCRUBBED   = "SCRUBBED"


@dataclass
class CountdownEvent:
    t: float             # seconds from T-0 (negative = before liftoff)
    phase: CountdownPhase
    message: str         # comm log line
    auto_hold: bool = False    # pause sim and require user RESUME
    hold_reason: str = ""      # displayed in the HOLD banner
    is_milestone: bool = False # bold in comm log


# ── Countdown script ──────────────────────────────────────────────────────────
# Scripted as (t_seconds, phase, message, auto_hold, hold_reason, is_milestone)

def _ev(t, phase, msg, hold=False, reason="", mile=False):
    return CountdownEvent(t, phase, msg, hold, reason, mile)

_BASE_SCRIPT: list[CountdownEvent] = [
    # T-3600 (T-1h): Terminal countdown begins
    _ev(-3600, CountdownPhase.PRECOUNT,
        "NTD: Initiating terminal countdown. T minus 60 minutes.", mile=True),
    _ev(-3600, CountdownPhase.PRECOUNT,
        "RANGE: All range assets nominal. Range is GO.", hold=True,
        reason="T-60 min HOLD — Awaiting range clearance", mile=True),

    _ev(-3540, CountdownPhase.PRECOUNT,
        "FLIGHT: Resume. Vehicle status nominal."),
    _ev(-3480, CountdownPhase.PROPLOAD,
        "PROP: Initiating final propellant load. LOX topping begins.", mile=True),
    _ev(-3360, CountdownPhase.PROPLOAD,
        "PROP: LOX loading at 40%."),
    _ev(-3240, CountdownPhase.PROPLOAD,
        "PROP: LOX loading at 70%."),
    _ev(-3120, CountdownPhase.PROPLOAD,
        "PROP: LOX loading at 90%. RP-1 at flight level."),
    _ev(-3000, CountdownPhase.PROPLOAD,
        "PROP: All propellants at flight level. PROP is GO."),

    _ev(-2700, CountdownPhase.PRECOUNT,
        "GUIDANCE: Inertial navigation system aligned. GUIDANCE is GO."),
    _ev(-2400, CountdownPhase.PRECOUNT,
        "RANGE SAFETY: FTS armed and ready. RSO is GO."),
    _ev(-2100, CountdownPhase.PRECOUNT,
        "WEATHER: Final weather brief. All parameters within limits."),
    _ev(-1800, CountdownPhase.PRECOUNT,
        "NTD: T minus 30 minutes. GO/NO-GO poll commencing.", mile=True,
        hold=True, reason="T-30 min HOLD — Director GO/NO-GO poll"),

    _ev(-1740, CountdownPhase.TERMINAL,
        "FLIGHT: Resuming. All stations GO. Terminal countdown proceeds."),
    _ev(-1680, CountdownPhase.TERMINAL,
        "RANGE: Downrange stations GO."),
    _ev(-1620, CountdownPhase.TERMINAL,
        "VEH: Vehicle GO for launch."),
    _ev(-1200, CountdownPhase.TERMINAL,
        "NTD: T minus 20 minutes. All systems nominal."),
    _ev(-900, CountdownPhase.TERMINAL,
        "NTD: T minus 15 minutes. Range is GO."),
    _ev(-600, CountdownPhase.TERMINAL,
        "NTD: T minus 10 minutes. Initiating engine chill-down."),
    _ev(-600, CountdownPhase.TERMINAL,
        "NTD: T-10 final GO/NO-GO poll.", hold=True,
        reason="T-10 min HOLD — Final GO/NO-GO Poll", mile=True),

    _ev(-540, CountdownPhase.TERMINAL,
        "FLIGHT: All systems confirmed GO. Resuming count."),
    _ev(-480, CountdownPhase.TERMINAL,
        "PROP: Engine purge and chill-down complete."),
    _ev(-420, CountdownPhase.AUTOSEQUENCE,
        "NTD: T minus 7 minutes. Strongback retract commanded.", mile=True),
    _ev(-360, CountdownPhase.AUTOSEQUENCE,
        "VEH: Vehicle to internal power. Umbilical retracting."),
    _ev(-300, CountdownPhase.AUTOSEQUENCE,
        "NTD: T minus 5 minutes. Flight computer armed."),
    _ev(-270, CountdownPhase.AUTOSEQUENCE,
        "PROP: LOX tank pressurised to flight pressure."),
    _ev(-180, CountdownPhase.AUTOSEQUENCE,
        "NTD: T minus 3 minutes. Auto-sequence start — computers in control."),
    _ev(-120, CountdownPhase.AUTOSEQUENCE,
        "FLIGHT: T minus 2. Vehicle is GO."),
    _ev(-60, CountdownPhase.AUTOSEQUENCE,
        "NTD: T minus 60 seconds. FINAL RANGE GO.", mile=True),
    _ev(-45, CountdownPhase.AUTOSEQUENCE,
        "RANGE: Flight, Range is GO and clear."),
    _ev(-30, CountdownPhase.AUTOSEQUENCE,
        "NTD: T minus 30 seconds."),
    _ev(-15, CountdownPhase.IGNITION,
        "NTD: T minus 15. Engine start sequence initiating.", mile=True,
        hold=True, reason="T-15 sec — Engine start sequence", ),
    _ev(-10, CountdownPhase.IGNITION,
        "FLIGHT: Ignition sequence confirmed. All engines starting."),
    _ev(-6, CountdownPhase.IGNITION,
        "NTD: T minus 6. Engines at partial thrust."),
    _ev(-3, CountdownPhase.IGNITION,
        "NTD: T minus 3... 2... 1..."),

    # T=0 LIFTOFF
    _ev(0, CountdownPhase.LIFTOFF,
        "NTD: IGNITION — WE HAVE LIFTOFF.", hold=True,
        reason="LIFTOFF — Vehicle ascending", mile=True),

    # Post-liftoff ascent events
    _ev(12,  CountdownPhase.LIFTOFF,
        "FLIGHT: Vehicle pitching downrange. Flight trajectory nominal."),
    _ev(60,  CountdownPhase.LIFTOFF,
        "FLIGHT: Vehicle supersonic."),
    _ev(80,  CountdownPhase.MAXQ,
        "FLIGHT: Approaching Max-Q. Throttling down.", hold=True,
        reason="MAX-Q — Maximum aerodynamic pressure", mile=True),
    _ev(90,  CountdownPhase.MAXQ,
        "FLIGHT: Throttle up. Max-Q passed."),
    _ev(160, CountdownPhase.MECO,
        "FLIGHT: MECO. Main engine cutoff confirmed.", hold=True,
        reason="MECO — Main Engine Cutoff", mile=True),
    _ev(163, CountdownPhase.STAGING,
        "FLIGHT: Stage separation confirmed.", hold=True,
        reason="STAGE SEP — Separation confirmed", mile=True),
    _ev(165, CountdownPhase.STAGING,
        "FLIGHT: Second stage ignition confirmed."),
    _ev(210, CountdownPhase.FAIRING,
        "FLIGHT: Fairing separation confirmed.", hold=True,
        reason="FAIRING SEP — Payload exposed", mile=True),
    _ev(480, CountdownPhase.ORBIT,
        "FLIGHT: SECO — Second engine cutoff. Coasting to apogee.", mile=True),
    _ev(530, CountdownPhase.ORBIT,
        "FLIGHT: Orbital insertion burn complete. Vehicle in parking orbit.", hold=True,
        reason="ORBITAL INSERTION — Parking orbit achieved", mile=True),
    _ev(600, CountdownPhase.COMPLETE,
        "FLIGHT: Mission success. Vehicle tracking nominal.", mile=True),
]


# ── Countdown controller ──────────────────────────────────────────────────────

class CountdownController:
    """
    Manages the countdown clock and script.

    Advance with step(dt_sim).  Returns list of events that fired this step.
    """

    def __init__(self, mission_name: str = ""):
        self.mission_name = mission_name
        self._script: list[CountdownEvent] = sorted(
            _BASE_SCRIPT, key=lambda e: e.t)
        self._next_idx = 0

        self.t: float = -3600.0     # seconds from T-0 (starts at T-1h)
        self.phase = CountdownPhase.PRECOUNT
        self.is_held: bool = True   # start held so user can review
        self.hold_reason: str = "AWAITING LAUNCH DIRECTOR GO"
        self.is_scrubbed: bool = False
        self.liftoff_time: Optional[float] = None   # sim_time when liftoff occurred

        self.log: list[str] = []
        self.pending_events: list[CountdownEvent] = []

        # Propellant loading progress (0-1)
        self.lox_level: float = 0.0
        self.fuel_level: float = 0.0

    def hold(self, reason: str = "MANUAL HOLD"):
        self.is_held = True
        self.hold_reason = reason
        self.log.append(f"[{_fmt_t(self.t)}] *** HOLD: {reason} ***")

    def resume(self):
        self.is_held = False
        self.hold_reason = ""
        self.log.append(f"[{_fmt_t(self.t)}] HOLD released. Countdown resuming.")

    def scrub(self):
        self.is_scrubbed = True
        self.phase = CountdownPhase.SCRUBBED
        self.is_held = True
        self.hold_reason = "MISSION SCRUBBED"
        self.log.append(f"[{_fmt_t(self.t)}] *** SCRUB: Launch attempt cancelled ***")

    def step(self, dt_sim: float) -> list[CountdownEvent]:
        """Advance clock by dt_sim seconds. Returns fired events."""
        self.pending_events = []

        if self.is_held or self.is_scrubbed:
            return []

        self.t += dt_sim

        # Propellant loading simulation
        if -3480 <= self.t <= -2970:
            progress = (self.t + 3480) / (3480 - 2970)
            self.lox_level = min(1.0, progress * 1.05)
            if self.fuel_level < 1.0:
                self.fuel_level = min(1.0, (self.t + 3600) / 600)
        elif self.t > -2970:
            self.lox_level = 1.0
            self.fuel_level = 1.0

        # Fire scripted events
        while self._next_idx < len(self._script):
            ev = self._script[self._next_idx]
            if self.t >= ev.t:
                self._fire(ev)
                self._next_idx += 1
            else:
                break

        return list(self.pending_events)

    def _fire(self, ev: CountdownEvent):
        self.phase = ev.phase
        self.log.append(f"[{_fmt_t(ev.t)}] {ev.message}")
        self.pending_events.append(ev)
        if ev.auto_hold:
            self.hold(ev.hold_reason)
        if ev.phase == CountdownPhase.LIFTOFF and self.t >= 0 and self.liftoff_time is None:
            self.liftoff_time = self.t  # signals main loop

    @property
    def t_display(self) -> str:
        return _fmt_t(self.t)

    @property
    def post_liftoff(self) -> bool:
        return self.t >= 0

    @property
    def complete(self) -> bool:
        return self.phase == CountdownPhase.COMPLETE


def _fmt_t(t: float) -> str:
    sign = "+" if t >= 0 else "-"
    s = abs(int(t))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"T{sign}{h:02d}:{m:02d}:{sec:02d}"
