"""
Launch success-probability model.

Combines every risk source into a single mission success probability, shown
before launch and used to resolve the flight:

  • test-run findings (uncorrected issues)   — each carries a failure chance
  • un-inspected subsystems (hidden risk)     — risk you never tested for
  • vehicle wear                              — from static fires
  • flight characteristics (wind tunnel)      — aerodynamic flight events

Astronaut skill modulates the odds: a calm, skilled crew averts a fraction of
anomalies (composure) and improves overall reliability (skill). Astronauts are
not modelled yet, so crew_profile() returns a placeholder; when real astronauts
are added, only that function needs to change.
"""

from __future__ import annotations
from dataclasses import dataclass

BASE_RELIABILITY = 0.985   # irreducible "good day at the Cape" factor


@dataclass
class CrewProfile:
    label: str
    skill: float        # 0..1 overall competence (reliability bonus)
    composure: float    # 0..1 calmness under pressure (anomaly recovery)
    crewed: bool

    def to_dict(self) -> dict:
        return {"label": self.label, "skill": round(self.skill, 2),
                "composure": round(self.composure, 2), "crewed": self.crewed}


def crew_profile(contract, craft_spec: dict) -> CrewProfile:
    """
    PLACEHOLDER until astronauts are modelled. Crewed missions get a nominal
    flight crew; uncrewed missions rely on automated flight systems.
    """
    if contract.required_crew > 0 and craft_spec.get("crew", 0) > 0:
        return CrewProfile("Flight crew (placeholder values)", 0.65, 0.60, True)
    return CrewProfile("Automated flight systems", 0.70, 0.50, False)


# How recoverable each kind of failure is by a composed crew (0 = unrecoverable).
_RECOVERY = {
    "systems": 0.45,
    "hidden":  0.30,
    "wear":    0.35,
    "aero_soft": 0.40,   # control upsets, oscillations
    "aero_hard": 0.15,   # structural / fails-to-lift
}
_AERO_HARD = {"MAXQ_STRUCT", "AEROELASTIC", "FAILS_TO_LIFT"}


def success_odds(contract, craft_spec: dict, aero: dict) -> dict:
    """Return successProbability (0..1), per-source breakdown, and crew profile."""
    crew = crew_profile(contract, craft_spec)
    sources = []

    def add(label, kind, base_chance, recover_key):
        if base_chance <= 0.0005:
            return
        rec = _RECOVERY[recover_key] * crew.composure
        eff = base_chance * (1.0 - rec)
        sources.append({
            "label": label, "kind": kind,
            "baseChance": round(base_chance, 3),
            "chance": round(eff, 3),
        })

    # Test-run findings still open
    for iss in contract.open_issues():
        if iss.failure_chance > 0:
            add(f"{iss.category} anomaly", "systems", iss.failure_chance, "systems")

    # Un-inspected subsystems + vehicle wear
    add("Un-inspected subsystems", "hidden", contract.hidden_component(), "hidden")
    add("Vehicle wear", "wear", contract.wear_risk(), "wear")

    # Flight characteristics (wind tunnel)
    for ev in aero.get("flightEvents", []):
        hard = ev["code"] in _AERO_HARD
        add(ev["description"], "aero", ev["chance"], "aero_hard" if hard else "aero_soft")

    # Combine independent failure chances; skill nudges the base reliability up.
    base = BASE_RELIABILITY + 0.01 * crew.skill
    p = min(0.999, base)
    for s in sources:
        p *= (1.0 - s["chance"])

    return {
        "successProbability": round(p, 4),
        "crew": crew.to_dict(),
        "sources": sources,
    }


def resolve_launch(odds: dict, rng) -> dict:
    """
    Roll the launch outcome from the odds. Returns
      {result: "SUCCESS"|"DEGRADED"|"FAILURE", culprit, rewardFactor}
    A composed crew can downgrade a would-be failure to a recovered (DEGRADED)
    outcome rather than a total loss.
    """
    p = odds["successProbability"]
    if rng.random() < p:
        return {"result": "SUCCESS", "culprit": None, "rewardFactor": 1.0}

    sources = odds["sources"] or []
    if not sources:
        return {"result": "FAILURE", "culprit": "unknown systems failure", "rewardFactor": 0.0}

    # The most likely culprit drives the failure.
    culprit = max(sources, key=lambda s: s["chance"])
    composure = odds["crew"]["composure"]
    hard = culprit["kind"] == "aero" and culprit["chance"] >= 0.0  # severity handled below
    # crew recovery roll — calmer crews salvage a degraded mission
    recovered = rng.random() < composure * 0.6
    if recovered:
        return {"result": "DEGRADED", "culprit": culprit["label"], "rewardFactor": 0.4}
    # severe aero/structural losses pay nothing; other failures pay a little
    severe = culprit["kind"] in ("aero", "wear")
    return {"result": "FAILURE", "culprit": culprit["label"],
            "rewardFactor": 0.0 if severe else 0.15}
