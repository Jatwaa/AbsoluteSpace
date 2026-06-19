"""
Real-time interactive reentry — the arrival counterpart to the launch sequence.

A craft that has to enter an atmosphere (a lander at its destination, or a crewed
/ sample-return mission coming home to Earth) flies the entry interactively. The
profile follows a real reentry from orbit down through the atmosphere:

  DEORBIT     Space          retrograde burn into the entry corridor
  INTERFACE   Thermosphere   entry interface — too steep burns up, too shallow skips out
  PEAK_HEAT   Mesosphere     maximum heating — heat-shield temperature peaks
  MAX_G       Stratosphere   maximum deceleration g-load
  DESCENT     Troposphere    blackout exit, guidance to target
  LANDING     Surface        drogues / parachutes / retro / touchdown

Telemetry tracks altitude, velocity, dynamic pressure, heat-shield temperature
and g-load. Event probabilities come from real physics: entry velocity (heating
~ v^3 and skip risk), ballistic coefficient, heat-shield adequacy, aerodynamic
stability, and crew composure. On an event the Director chooses an entry
countermeasure — adjust AoA / lift vector, bank, roll to distribute heating,
steepen/shallow the corridor, deploy backups — dampened by astronaut composure.
"""

from __future__ import annotations
import math

DECISION_SECONDS = 16.0

# (key, title, layer, alt_end_km, vfrac_end, dur_s, temp_factor, g_end)
PHASES = [
    ("DEORBIT",   "De-orbit Burn",                 "Low orbit / Space",   120.0, 1.00, 11.0, 0.02, 0.3),
    ("INTERFACE", "Entry Interface",               "Thermosphere",         80.0, 0.95, 14.0, 0.45, 1.8),
    ("PEAK_HEAT", "Peak Heating",                  "Mesosphere",           55.0, 0.65, 16.0, 1.00, 3.5),
    ("MAX_G",     "Peak Deceleration",             "Stratosphere",         32.0, 0.28, 14.0, 0.55, 1.00),  # g_end set to peak_g at runtime
    ("DESCENT",   "Descent & Blackout Exit",       "Troposphere",          12.0, 0.06, 14.0, 0.15, 1.5),
    ("LANDING",   "Terminal Descent & Landing",    "Surface",               0.0, 0.01, 12.0, 0.04, 1.2),
]


def _opt(oid, label, score, hint=""):
    return {"id": oid, "label": label, "score": score, "hint": hint}


class ReentrySequence:
    kind = "REENTRY"

    def __init__(self, *, mission_name, title, craft_name, owner_id, crew,
                 entry_velocity, ballistic, stability, has_heatshield, rng):
        self.mission_name = mission_name
        self.contract_id = mission_name          # used as the dict key / decision id
        self.title = title
        self.craft_name = craft_name
        self.owner_id = owner_id
        self.crewed = crew["crewed"]
        self.skill = crew["skill"]
        self.composure = crew["composure"]
        self.crew_label = crew["label"]
        self.rng = rng

        self.entry_v = entry_velocity            # km/s at interface
        self.ballistic = ballistic               # kg/m^2
        self.stability = stability
        self.has_heatshield = has_heatshield
        # peak heat-shield temperature (deg C) scales with entry speed; thin TPS = hotter
        self.peak_temp = 200.0 * entry_velocity * (1.25 if not has_heatshield else 1.0)
        self.peak_g = 4.0 + entry_velocity / 3.0

        self.phase_idx = 0
        self.t_phase = 0.0
        self.status = "RUNNING"
        self.decision = None
        self.degraded = False
        self.result = None
        self.outcome = None
        self._rolled = False
        self.log = []
        self.telemetry = {"altitudeKm": 200.0, "velocityKms": round(entry_velocity, 2),
                          "qKpa": 0.0, "tempC": 25.0, "gLoad": 0.0, "throttle": 0.0}
        self._a_start = 200.0
        self._v_start = entry_velocity
        self._say("FLIGHT", f"{craft_name} configured for entry. Entry velocity "
                            f"{entry_velocity:.1f} km/s.")
        if not has_heatshield:
            self._say("CAPCOM", "Flight, be advised — no dedicated entry/heat-shield "
                                "hardware on this vehicle.")

    def _say(self, who, msg):
        self.log.append({"who": who, "msg": msg})
        if len(self.log) > 60:
            self.log = self.log[-60:]

    @property
    def phase(self):
        return PHASES[self.phase_idx]

    # ── event generation from entry physics ──
    def _maybe_event(self):
        key = self.phase[0]
        r = self.rng.random
        hot = self.peak_temp > 2200 or not self.has_heatshield
        fast = self.entry_v >= 9.5

        if key == "DEORBIT":
            chance = 0.05 + (0.10 if self.stability != "STABLE" else 0)
            if r() < chance:
                return self._event(
                    "DEORBIT_LOW", "DE-ORBIT BURN UNDERPERFORMANCE",
                    "The retrograde burn is short — the entry corridor is trending shallow.",
                    "CAPCOM: Flight, residual velocity is high, we're shallow on the corridor.",
                    [_opt("EXTEND_BURN", "Extend the de-orbit burn", 0.72, "Tighten the corridor"),
                     _opt("WAVE_OFF", "Wave off — try the next orbit", 0.6, "Costs time, safe"),
                     _opt("HOLD", "Accept the corridor", 0.3)])

        elif key == "INTERFACE":
            shallow = 0.05 + (0.15 if not hot else 0)
            steep = 0.05 + (0.15 if fast else 0) + (0.12 if not self.has_heatshield else 0)
            if r() < shallow:
                return self._event(
                    "SKIP_OUT", "ENTRY ANGLE TOO SHALLOW — SKIP-OUT RISK",
                    "The flight-path angle is too shallow; the vehicle may skip back off the atmosphere.",
                    "CAPCOM: Flight, we're skipping — lift vector is bouncing us out!",
                    [_opt("LIFT_DOWN", "Roll lift vector down — bite into the atmosphere", 0.72),
                     _opt("AOA_STEEP", "Increase AoA / drag to steepen", 0.6),
                     _opt("HOLD", "Hold attitude and hope it captures", 0.25)],
                    severe=True)
            if r() < steep:
                return self._event(
                    "STEEP", "ENTRY ANGLE TOO STEEP — OVER-HEATING / G",
                    "The corridor is too steep — heating and deceleration are spiking.",
                    "CAPCOM: Flight, we're steep and hot, loads are climbing fast.",
                    [_opt("LIFT_UP", "Roll lift vector up — shallow the descent", 0.72),
                     _opt("AOA_SHALLOW", "Reduce AoA to extend the glide", 0.58),
                     _opt("HOLD", "Ride it down", 0.2)],
                    severe=True)

        elif key == "PEAK_HEAT":
            chance = 0.05 + (0.25 if not self.has_heatshield else 0) + (0.18 if self.peak_temp > 2400 else 0)
            if r() < chance:
                if not self.has_heatshield:
                    return self._event(
                        "TPS_BURN", "THERMAL PROTECTION FAILURE",
                        "Without an entry heat shield the structure is exceeding survivable temperatures.",
                        "CAPCOM: Flight, skin temps are off the scale — we're burning through!",
                        [_opt("ROLL_DISTRIB", "Maximize roll to spread the heating", 0.4),
                         _opt("AOA_SHALLOW", "Shallow the entry to cut heat rate", 0.45),
                         _opt("HOLD", "Brace and hold", 0.15)],
                        severe=True)
                return self._event(
                    "OVERTEMP", "HEAT-SHIELD OVER-TEMPERATURE",
                    "A heat-shield zone is approaching its limit at peak heating.",
                    "CAPCOM: Flight, we've got a hot zone on the shield — recommend roll.",
                    [_opt("ROLL_DISTRIB", "Increase roll rate to distribute heating", 0.72),
                     _opt("AOA_SHALLOW", "Reduce heat rate by shallowing", 0.6),
                     _opt("HOLD", "Hold — ride out the pulse", 0.35)],
                    severe=True)

        elif key == "MAX_G":
            chance = 0.05 + (0.15 if self.entry_v >= 9.5 else 0) + (0.10 if self.stability != "STABLE" else 0)
            if r() < chance:
                if self.stability != "STABLE":
                    return self._event(
                        "ROLL_LOSS", "LIFT-VECTOR / ROLL-REVERSAL CONTROL LOSS",
                        "Roll control is wandering — the lift vector isn't tracking the guidance.",
                        "CAPCOM: Flight, we've lost the roll program — she's oscillating.",
                        [_opt("ROLL_REVERSAL", "Command a manual roll reversal", 0.68),
                         _opt("DAMP", "Damp the rates, stabilize", 0.55),
                         _opt("HOLD", "Let the autopilot fight it", 0.25)],
                        severe=True)
                return self._event(
                    "HIGH_G", "EXCESSIVE DECELERATION G-LOAD",
                    "Deceleration is exceeding structural / crew g-limits.",
                    "CAPCOM: Flight, we're pulling heavy g's — above the red line.",
                    [_opt("LIFT_UP", "Lift vector up to reduce deceleration", 0.7),
                     _opt("HOLD", "Hold — push through the g-pulse", 0.35)],
                    severe=True)

        elif key == "DESCENT":
            chance = 0.05
            if r() < chance:
                return self._event(
                    "GUIDANCE_DRIFT", "POST-BLACKOUT GUIDANCE DRIFT",
                    "Coming out of plasma blackout the navigation has drifted off the target.",
                    "CAPCOM: Flight, nav re-acquired but we're long on the footprint.",
                    [_opt("BANK_CROSS", "Bank for cross-range correction", 0.7),
                     _opt("HOLD", "Accept an off-target landing", 0.45, "Degraded landing")])

        elif key == "LANDING":
            chance = 0.05 + self.ballistic / 60000.0
            if r() < chance:
                return self._event(
                    "CHUTE_FAIL", "PARACHUTE / DECELERATOR ANOMALY",
                    "The primary decelerator did not deploy cleanly — descent rate is high.",
                    "CAPCOM: Flight, no good chute! Descent rate is hot!",
                    [_opt("BACKUP_CHUTE", "Deploy the backup parachutes", 0.7),
                     _opt("RETRO", "Fire terminal retro-rockets", 0.6),
                     _opt("BRACE", "Brace for a hard landing", 0.3)],
                    severe=True)
        return None

    def _event(self, code, title, detail, feedback, options, severe=False):
        return {"code": code, "title": title, "detail": detail, "crewFeedback": feedback,
                "options": options, "timeLeft": DECISION_SECONDS, "deadline": DECISION_SECONDS,
                "severe": severe, "phase": self.phase[0]}

    def step(self, dt: float):
        if self.status == "DONE":
            return
        if self.status == "DECISION":
            self.decision["timeLeft"] = max(0.0, self.decision["timeLeft"] - dt)
            if self.decision["timeLeft"] <= 0.0:
                self._resolve(None)
            return

        key, title, layer, alt_end, vfrac_end, dur, temp_f, g_end = self.phase
        if key == "MAX_G":
            g_end = self.peak_g
        self.t_phase += dt
        p = min(1.0, self.t_phase / dur)
        ease = p * p * (3 - 2 * p)
        self.telemetry["altitudeKm"] = round(self._a_start + (alt_end - self._a_start) * ease, 1)
        v_end = vfrac_end * self.entry_v if key != "LANDING" else 0.05
        self.telemetry["velocityKms"] = round(self._v_start + (v_end - self._v_start) * ease, 2)
        v_ms = self.telemetry["velocityKms"] * 1000.0
        rho = 1.225 * math.exp(-self.telemetry["altitudeKm"] / 8.5)
        self.telemetry["qKpa"] = round(0.5 * rho * v_ms * v_ms / 1000.0, 1)
        self.telemetry["tempC"] = round(25 + (self.peak_temp - 25) * temp_f * (0.5 + 0.5 * ease), 0)
        self.telemetry["gLoad"] = round(g_end * ease, 1)

        if not self._rolled and p >= 0.4:
            self._rolled = True
            ev = self._maybe_event()
            if ev:
                self.status = "DECISION"
                self.decision = ev
                self._say("CAPCOM", ev["crewFeedback"])
                self._say("FLIGHT", f"*** {ev['title']} — Director, your call. ***")
                return
            self._say("CAPCOM", f"{title}: nominal.")

        if p >= 1.0:
            self._advance_phase()

    def _advance_phase(self):
        self._a_start = self.phase[3]
        self._v_start = (self.phase[4] * self.entry_v) if self.phase[0] != "LANDING" else 0.05
        self.phase_idx += 1
        self._rolled = False
        self.t_phase = 0.0
        if self.phase_idx >= len(PHASES):
            self._finish()
            return
        self._say("FLIGHT", f"{self.phase[1]} — {self.phase[2]}.")

    def _finish(self):
        self.status = "DONE"
        if self.degraded:
            self.result = "DEGRADED"
            self.outcome = "DEGRADED: survived entry but landed off-nominal / off-target."
            self._say("FLIGHT", "Touchdown — off-nominal, but the vehicle is down intact.")
        else:
            self.result = "SUCCESS"
            self.outcome = "SUCCESS: nominal entry, descent, and landing."
            self._say("FLIGHT", "Touchdown confirmed. Textbook entry, all stations.")

    def decide(self, option_id):
        if self.status != "DECISION" or not self.decision:
            return
        self._resolve(option_id)

    def _resolve(self, option_id):
        ev = self.decision
        opt = next((o for o in ev["options"] if o["id"] == option_id), None)

        # de-orbit wave-off is a safe retry, not a failure
        if opt and opt["id"] == "WAVE_OFF":
            self.degraded = True
            self._say("FLIGHT", "Waving off — recycling for a later entry opportunity.")
            self.status = "RUNNING"
            self.decision = None
            self.t_phase = self.phase[5] * 0.55
            return

        if opt is None:
            recovery = self.composure * 0.6 + self.skill * 0.1
            self._say("CAPCOM", "No call from the ground — crew is flying it manually!")
        else:
            recovery = opt["score"] + self.composure * 0.20 + self.skill * 0.10
        recovery = max(0.02, min(0.96, recovery))

        if self.rng.random() < recovery:
            partial = (opt is None) or opt["score"] < 0.6
            if partial:
                self.degraded = True
            self._say("CAPCOM", "Back in the corridor — we're tracking nominal again.")
            self.status = "RUNNING"
            self.decision = None
            self.t_phase = max(self.t_phase, self.phase[5] * 0.55)
        else:
            self.status = "DONE"
            self.result = "FAILURE"
            who = ev["title"].split(" — ")[0].lower()
            if self.crewed:
                self.outcome = f"FAILURE: {who} — loss of vehicle and crew during entry."
            else:
                self.outcome = f"FAILURE: {who} — vehicle destroyed during entry."
            self._say("FLIGHT", f"We've lost the vehicle during entry. {ev['title']}.")

    def to_dict(self):
        key, title, layer, alt_end, vfrac, dur, *_ = self.phase
        return {
            "kind": "REENTRY",
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
