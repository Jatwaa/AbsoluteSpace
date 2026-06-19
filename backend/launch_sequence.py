"""
Real-time launch sequence — an interactive ascent that follows a real launch
profile through the atmosphere layers.

Phases (each an atmosphere layer with characteristic events):
  IGNITION   Ground        engine start, pad clear
  ASCENT     Troposphere   tower clear, pitch/roll program
  MAXQ       Tropopause    maximum dynamic pressure, throttle bucket
  STAGING    Stratosphere  MECO, stage separation
  UPPER      Mesosphere    upper-stage burn, fairing jettison
  INSERTION  Thermosphere  SECO, orbital insertion

The sequence runs in real (wall-clock) time so the Director can react. Each
phase rolls for a characteristic failure event whose probability comes from the
craft's real risk inputs — liftoff TWR, aerodynamic stability, max-Q level,
uncorrected test findings, un-inspected subsystems, and vehicle wear. When an
event fires the clock holds and the crew reports the situation; the Director
chooses a countermeasure (adjust AoA, throttle, manual staging, hold, or abort).
Resolution is dampened or exacerbated by astronaut composure & skill — and if
the Director freezes, the crew handles it alone on their composure.
"""

from __future__ import annotations
import math

# (key, title, layer, alt_end_km, vel_end_kms, duration_s)
PHASES = [
    ("IGNITION",  "Ignition & Liftoff",            "Ground level",         0.3,  0.05, 10.0),
    ("ASCENT",    "Tower Clear & Pitch Program",    "Troposphere",         11.0,  0.50, 18.0),
    ("MAXQ",      "Maximum Dynamic Pressure",       "Tropopause",          22.0,  1.20, 15.0),
    ("STAGING",   "MECO & Stage Separation",        "Stratosphere",        75.0,  2.80, 16.0),
    ("UPPER",     "Upper-Stage Burn & Fairing Jettison", "Mesosphere",    130.0,  5.50, 20.0),
    ("INSERTION", "Orbital Insertion",              "Thermosphere / Space", 200.0, 7.80, 18.0),
]

DECISION_SECONDS = 18.0


# ── option catalogue (id, label, hint) ───────────────────────────────────────
def _opt(oid, label, score, hint=""):
    return {"id": oid, "label": label, "score": score, "hint": hint}


class LaunchSequence:
    def __init__(self, contract, craft_spec, aero, crew, rng):
        self.contract_id = contract.id
        self.title = contract.title
        self.craft_name = contract.craft_name
        self.owner_id = contract.owner_id
        self.crewed = crew["crewed"]
        self.skill = crew["skill"]
        self.composure = crew["composure"]
        self.crew_label = crew["label"]
        self.rng = rng

        # ── risk inputs (real craft characteristics) ──
        self.twr = craft_spec.get("twr", 1.0)
        self.stability = aero.get("stability", "STABLE")
        self.maxq = aero.get("maxQLevel", "LOW")
        self.control = aero.get("controlAuthority", "OK")
        self.hidden = contract.hidden_component()
        self.wear = contract.vehicle_wear / 100.0
        self.issue_chance = sum(i.failure_chance for i in contract.open_issues())
        self.aero_codes = {e["code"] for e in aero.get("flightEvents", [])}

        # ── state ──
        self.phase_idx = 0
        self.t_phase = 0.0
        self.status = "RUNNING"          # RUNNING | DECISION | DONE
        self.decision = None
        self.degraded = False
        self.result = None               # SUCCESS | DEGRADED | FAILURE | ABORT
        self.outcome = None
        self._rolled = False
        self.log: list[str] = []
        self.telemetry = {"altitudeKm": 0.0, "velocityKms": 0.0,
                          "qKpa": 0.0, "throttle": 1.0, "aoaOk": True}
        self._v_start = 0.0
        self._a_start = 0.0
        self._say("FLIGHT", f"Terminal count complete. {self.craft_name} is GO for launch.")

    # ── helpers ──
    def _say(self, who, msg):
        self.log.append({"who": who, "msg": msg})
        if len(self.log) > 60:
            self.log = self.log[-60:]

    @property
    def phase(self):
        return PHASES[self.phase_idx]

    # ── per-phase event generation from real risk inputs ──
    def _maybe_event(self):
        key = self.phase[0]
        r = self.rng.random
        comp_pen = 0.0  # difficulty is in the chance; recovery handles crew

        if key == "IGNITION":
            if self.twr < 1.0:
                return self._event(
                    "NO_LIFT", "INSUFFICIENT THRUST",
                    "Liftoff thrust is below vehicle weight — the stack is not rising.",
                    "CAPCOM: We are not climbing! Hold-down detect, thrust is red.",
                    [_opt("ABORT", "Abort / shut down on pad", 0.0, "Safe the vehicle"),
                     _opt("THROTTLE_UP", "Command engines to redline", 0.25, "Risk overstress")],
                    severe=True)
            chance = 0.03 + self.wear * 0.30 + (0.15 if "engine" in str(self.aero_codes).lower() else 0)
            if r() < chance:
                return self._event(
                    "HARD_START", "ENGINE START TRANSIENT",
                    "A chamber-pressure spike on engine start — possible hard start.",
                    "CAPCOM: Flight, we saw a pressure spike on the start sequence.",
                    [_opt("HOLD", "Continue — monitor engine health", 0.55),
                     _opt("THROTTLE_DOWN", "Throttle to safe level", 0.6, "Costs performance"),
                     _opt("ABORT", "Abort the launch", 0.0)])

        elif key == "ASCENT":
            chance = 0.04 + self.hidden * 0.25
            if self.stability != "STABLE":
                chance += 0.15
            if r() < chance:
                return self._event(
                    "DRIFT", "GUIDANCE DISPERSION",
                    "The vehicle is drifting off its planned azimuth; attitude error is growing.",
                    "CAPCOM: Flight, guidance is showing increasing cross-range error.",
                    [_opt("AOA", "Pitch to null the angle of attack", 0.7, "Right call for control"),
                     _opt("HOLD", "Hold and let the autopilot recover", 0.4),
                     _opt("ABORT", "Abort before it diverges", 0.0)])

        elif key == "MAXQ":
            chance = 0.04
            if self.maxq == "HIGH":
                chance += 0.18
            elif self.maxq == "SEVERE":
                chance += 0.34
            if "MAXQ_STRUCT" in self.aero_codes or "AEROELASTIC" in self.aero_codes:
                chance += 0.12
            structural = self.maxq in ("HIGH", "SEVERE")
            if r() < chance:
                if self.stability != "STABLE" or "LOSS_OF_CONTROL" in self.aero_codes:
                    return self._event(
                        "AOA_DIVERGE", "AERODYNAMIC INSTABILITY",
                        "Angle of attack is diverging through max-Q — aerodynamic loads building fast.",
                        "CAPCOM: Flight, she's getting away from us — AoA is climbing!",
                        [_opt("AOA", "Pitch down, reduce angle of attack", 0.72),
                         _opt("THROTTLE_DOWN", "Throttle down to cut dynamic pressure", 0.55),
                         _opt("ABORT", "Abort — structural limits", 0.0)],
                        severe=True)
                return self._event(
                    "MAXQ_LOADS", "STRUCTURAL LOADS AT MAX-Q",
                    "Dynamic pressure is exceeding structural margins on the airframe.",
                    "CAPCOM: Flight, we're seeing loads above the red line at max-Q.",
                    [_opt("THROTTLE_DOWN", "Throttle bucket — reduce dynamic pressure", 0.72),
                     _opt("HOLD", "Ride it out, push through max-Q", 0.35),
                     _opt("ABORT", "Abort the ascent", 0.0)],
                    severe=structural)

        elif key == "STAGING":
            chance = 0.04 + self.issue_chance * 0.4 + self.wear * 0.15
            if r() < chance:
                return self._event(
                    "STAGE_FAIL", "STAGE SEPARATION ANOMALY",
                    "Stage separation indication is not clean — possible failure to separate.",
                    "CAPCOM: Flight, we do not have a clean sep confirmation.",
                    [_opt("MANUAL_STAGE", "Command manual separation", 0.7),
                     _opt("HOLD", "Wait for automatic recycle", 0.35),
                     _opt("ABORT", "Abort the mission", 0.05)])

        elif key == "UPPER":
            chance = 0.04 + self.issue_chance * 0.3 + self.hidden * 0.2
            if r() < chance:
                return self._event(
                    "UPPER_IGNITION", "UPPER-STAGE IGNITION DELAY",
                    "Upper-stage engine is slow to reach thrust after separation.",
                    "CAPCOM: Flight, second-stage chamber pressure is lagging.",
                    [_opt("RESTART", "Command an ignition retry", 0.65),
                     _opt("HOLD", "Wait — give it time to build", 0.45),
                     _opt("ABORT", "Safe the stage", 0.1)])

        elif key == "INSERTION":
            chance = 0.04 + self.issue_chance * 0.25 + self.hidden * 0.15
            if r() < chance:
                return self._event(
                    "SECO_DISP", "INSERTION CUTOFF DISPERSION",
                    "Guidance is predicting an off-nominal cutoff — orbit may be wrong.",
                    "CAPCOM: Flight, we're trending toward an under-burn at SECO.",
                    [_opt("THROTTLE_UP", "Extend the burn to make up velocity", 0.68),
                     _opt("HOLD", "Accept the orbit as-is", 0.4, "Likely a degraded orbit"),
                     _opt("ABORT", "Abort to a safe trajectory", 0.15)])
        return None

    def _event(self, code, title, detail, feedback, options, severe=False):
        return {
            "code": code, "title": title, "detail": detail,
            "crewFeedback": feedback, "options": options,
            "timeLeft": DECISION_SECONDS, "deadline": DECISION_SECONDS,
            "severe": severe, "phase": self.phase[0],
        }

    # ── stepping ──
    def step(self, dt: float):
        if self.status == "DONE":
            return
        if self.status == "DECISION":
            self.decision["timeLeft"] = max(0.0, self.decision["timeLeft"] - dt)
            if self.decision["timeLeft"] <= 0.0:
                self._resolve(None)   # crew handles it alone
            return

        # RUNNING — advance telemetry within the phase
        key, title, layer, alt_end, vel_end, dur = self.phase
        self.t_phase += dt
        p = min(1.0, self.t_phase / dur)
        ease = p * p * (3 - 2 * p)  # smoothstep
        self.telemetry["altitudeKm"] = round(self._a_start + (alt_end - self._a_start) * ease, 1)
        self.telemetry["velocityKms"] = round(self._v_start + (vel_end - self._v_start) * ease, 2)
        v_ms = self.telemetry["velocityKms"] * 1000.0
        rho = 1.225 * math.exp(-self.telemetry["altitudeKm"] / 8.5)
        self.telemetry["qKpa"] = round(0.5 * rho * v_ms * v_ms / 1000.0, 1)
        self.telemetry["throttle"] = 0.70 if key == "MAXQ" and 0.2 < p < 0.8 else 1.0

        # roll the phase event around mid-phase
        if not self._rolled and p >= 0.4:
            self._rolled = True
            ev = self._maybe_event()
            if ev:
                self.status = "DECISION"
                self.decision = ev
                self._say("CAPCOM", ev["crewFeedback"])
                self._say("FLIGHT", f"*** {ev['title']} — Director, your call. ***")
                return
            else:
                self._say("CAPCOM", f"{title}: nominal.")

        if p >= 1.0:
            self._advance_phase()

    def _advance_phase(self):
        key = self.phase[0]
        self._a_start = self.phase[3]
        self._v_start = self.phase[4]
        self.phase_idx += 1
        self._rolled = False
        self.t_phase = 0.0
        if self.phase_idx >= len(PHASES):
            self._finish()
            return
        nk, nt, nl, *_ = self.phase
        self._say("FLIGHT", f"{nt} — entering {nl}.")

    def _finish(self):
        self.status = "DONE"
        if self.degraded:
            self.result = "DEGRADED"
            self.outcome = "DEGRADED: vehicle reached a non-nominal orbit after in-flight anomalies."
            self._say("FLIGHT", "Spacecraft separation confirmed — degraded but alive.")
        else:
            self.result = "SUCCESS"
            self.outcome = "SUCCESS: clean ascent and nominal orbital insertion."
            self._say("FLIGHT", "Orbital insertion confirmed. Outstanding flight, all stations.")

    # ── decision resolution ──
    def decide(self, option_id):
        if self.status != "DECISION" or not self.decision:
            return
        self._resolve(option_id)

    def _resolve(self, option_id):
        ev = self.decision
        opt = next((o for o in ev["options"] if o["id"] == option_id), None)

        if opt and opt["id"] == "ABORT":
            self.status = "DONE"
            self.result = "ABORT"
            if self.crewed:
                self.outcome = ("ABORT: launch escape commanded — crew recovered safely, "
                                "vehicle and mission lost.")
                self._say("CAPCOM", "Abort! Abort! — escape system nominal, crew is safe.")
            else:
                self.outcome = "ABORT: flight termination commanded — vehicle destroyed, range safe."
                self._say("FLIGHT", "Flight termination system activated. Vehicle is gone.")
            return

        if opt is None:
            # Director froze — the crew handles it on composure alone.
            recovery = self.composure * 0.6 + self.skill * 0.1
            self._say("CAPCOM", "No call from the ground — crew is taking it manually!")
        else:
            recovery = opt["score"] + self.composure * 0.20 + self.skill * 0.10
        recovery = max(0.02, min(0.96, recovery))

        if self.rng.random() < recovery:
            # recovered — continue, possibly degraded if it wasn't a clean save
            partial = (opt is None) or opt["score"] < 0.6
            if partial:
                self.degraded = True
            self._say("CAPCOM", "We've got it back under control. Pressing on.")
            self.status = "RUNNING"
            self.decision = None
            # nudge past the event point so it doesn't immediately re-trigger
            self.t_phase = max(self.t_phase, self.phase[5] * 0.55)
        else:
            self.status = "DONE"
            self.result = "FAILURE"
            who = ev["title"].lower()
            if self.crewed and ev.get("severe"):
                self.outcome = f"FAILURE: {who} — loss of vehicle and crew."
            else:
                self.outcome = f"FAILURE: {who} — vehicle lost."
            self._say("FLIGHT", f"We've lost the vehicle. {ev['title']}.")

    # ── serialization ──
    def to_dict(self) -> dict:
        key, title, layer, alt_end, vel_end, dur = self.phase
        return {
            "contractId": self.contract_id,
            "title": self.title,
            "craftName": self.craft_name,
            "ownerId": self.owner_id,
            "crewed": self.crewed,
            "crewLabel": self.crew_label,
            "status": self.status,
            "phaseIndex": self.phase_idx if self.phase_idx < len(PHASES) else len(PHASES) - 1,
            "phaseKey": key,
            "phaseTitle": title,
            "layer": layer,
            "phaseProgress": round(min(1.0, self.t_phase / dur), 3),
            "phaseCount": len(PHASES),
            "telemetry": self.telemetry,
            "decision": self.decision,
            "log": self.log[-14:],
            "result": self.result,
            "outcome": self.outcome,
        }
