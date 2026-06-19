"""
Virtual wind tunnel — aerodynamic & flight-worthiness assessment of a craft.

The craft is a flat stack of parts (nose at index 0, engines at the bottom).
We have no explicit geometry, so each part is given a physically-motivated
size proxy from its mass and type, then we compute the classic rocket-stability
quantities:

  • Center of Mass (CoM)      — mass-weighted centroid along the body axis.
  • Center of Pressure (CoP)  — silhouette (side-area) centroid: the
                                aerodynamic center the airflow "pushes" on.
  • Static margin (calibers)  — (CoP - CoM) / diameter. Positive (CoP aft of
                                CoM, i.e. mass forward like a dart) = stable.
  • Fineness ratio            — length / diameter (slenderness).
  • TWR                       — liftoff thrust-to-weight (mass↔lift balance).
  • Drag / ballistic coef     — drives max dynamic pressure (max-Q).

It returns metrics, a list of noted flight-characteristic issues (the player
decides how to fix them), and a set of probabilistic flight events the launch
simulation rolls to decide what happens during ascent.
"""

from __future__ import annotations
import math
from .craft import ModuleType, G0

# Effective bulk densities (kg/m^3) per part type — turns mass into a volume.
_DENSITY = {
    ModuleType.ENGINE:      2500.0,
    ModuleType.FUEL_TANK:    850.0,
    ModuleType.COMMAND:      450.0,
    ModuleType.PAYLOAD:      600.0,
    ModuleType.SOLAR_PANEL:  350.0,
    ModuleType.COMMS:        350.0,
    ModuleType.DECOUPLER:   2200.0,
}

# Engines that cannot gimbal (no active steering authority).
_NON_GIMBAL_HINTS = ("SRB", "Solid", "Castor", "Zefiro", "P80", "Star-",
                     "RSRM", "S200", "GEM", "motor")


def _is_gimbaled(name: str, mtype) -> bool:
    if mtype != ModuleType.ENGINE:
        return False
    return not any(h.lower() in name.lower() for h in _NON_GIMBAL_HINTS)


def _part_mass(m) -> float:
    return m.dry_mass + m.fuel_capacity + m.life_support_mass * m.crew_capacity


def assess(sc) -> dict:
    """Full aerodynamic / flight-worthiness assessment of a Spacecraft."""
    parts = [p for p in sc.parts]
    if not parts:
        return _empty()

    # ── Per-part size proxies ──
    # A part of volume V is modelled as a cylinder whose own length:diameter
    # is ~STAGE_FINENESS, so D = (4V / (pi * STAGE_FINENESS))^(1/3).
    STAGE_FINENESS = 4.0
    vols, masses, widths = [], [], []
    for p in parts:
        rho = _DENSITY.get(p.module_type, 800.0)
        mass = _part_mass(p)
        vol = max(mass / rho, 0.05)
        masses.append(mass)
        vols.append(vol)
        widths.append(max(0.4, (4 * vol / (math.pi * STAGE_FINENESS)) ** (1 / 3)))

    # Body diameter = widest structural element (tanks/command define the body)
    body_d = max(
        [widths[i] for i, p in enumerate(parts)
         if p.module_type in (ModuleType.FUEL_TANK, ModuleType.COMMAND, ModuleType.PAYLOAD)]
        or widths)
    body_d = max(body_d, 0.6)

    # Lengths at the body diameter; positions measured from the nose (top).
    area = math.pi / 4 * body_d ** 2
    lengths, centers = [], []
    cum = 0.0
    for vol in vols:
        l = max(0.3, vol / area)
        lengths.append(l)
        centers.append(cum + l / 2)
        cum += l
    total_len = cum

    # ── CoM (mass-weighted) and CoP (side-area-weighted) ──
    msum = sum(masses) or 1.0
    com = sum(m * c for m, c in zip(masses, centers)) / msum
    side_areas = [min(widths[i], body_d) * lengths[i] for i in range(len(parts))]
    asum = sum(side_areas) or 1.0
    cop = sum(a * c for a, c in zip(side_areas, centers)) / asum

    static_margin_cal = (cop - com) / body_d
    fineness = total_len / body_d

    # ── Lift balance ──
    twr = sc.twr
    gimbal_thrust = sum(p.thrust for p in parts if _is_gimbaled(p.name, p.module_type))
    total_thrust = sum(p.thrust for p in parts if p.module_type == ModuleType.ENGINE)
    gimbal_frac = (gimbal_thrust / total_thrust) if total_thrust > 0 else 0.0

    # ── Drag / max-Q ──
    cd = 0.40
    if fineness < 6:
        cd += 0.35 * (6 - fineness) / 6        # stubby = bluff body
    if fineness > 22:
        cd += 0.05
    total_mass = sc.total_mass
    ballistic = total_mass / (cd * area) if area > 0 else 0.0
    # Max-Q is driven mainly by liftoff TWR (how fast you build speed low in the
    # atmosphere), nudged up for very dense (high-ballistic) vehicles.
    dense = min(1.0, ballistic / 12000.0)
    maxq_index = twr * (0.9 + 0.25 * dense)
    maxq_level = ("SEVERE" if maxq_index > 2.6 else "HIGH" if maxq_index > 1.9
                  else "MODERATE" if maxq_index > 1.25 else "LOW")

    # ── Stability classification ──
    # Thresholds calibrated to this silhouette-centroid model: mass-forward
    # (dart-like) designs read positive; tail-heavy designs read negative.
    if static_margin_cal >= 0.12:
        stability = "STABLE"
    elif static_margin_cal >= -0.08:
        stability = "MARGINAL"
    else:
        stability = "UNSTABLE"

    if gimbal_frac >= 0.6:
        control = "OK"
    elif gimbal_frac > 0.1:
        control = "LIMITED"
    else:
        control = "NONE"

    # ── Issues (noted only) ──
    issues, events = [], []

    def issue(code, sev, title, detail):
        issues.append({"code": code, "severity": sev, "title": title, "detail": detail})

    def event(code, chance, desc):
        events.append({"code": code, "chance": round(min(0.95, chance), 3), "description": desc})

    if stability == "UNSTABLE":
        if control in ("NONE", "LIMITED"):
            issue("UNSTABLE_NOCTRL", "CRITICAL", "Aerodynamically unstable, low control authority",
                  f"Center of pressure is {abs(static_margin_cal):.1f} cal ahead of the center "
                  f"of mass and gimballed thrust is only {gimbal_frac*100:.0f}% — the vehicle "
                  f"will tend to tumble.")
            event("LOSS_OF_CONTROL", 0.6, "Loss of control during ascent (aerodynamic instability)")
        else:
            issue("UNSTABLE", "WARN", "Aerodynamically unstable (relies on active control)",
                  f"CoP {abs(static_margin_cal):.1f} cal ahead of CoM. Flyable only on "
                  f"thrust-vector control; corrections will be aggressive.")
            event("LOSS_OF_CONTROL", 0.2, "Departure from controlled flight during a gust")
    elif stability == "MARGINAL":
        issue("MARGINAL_STABILITY", "WARN", "Marginal static stability",
              f"Static margin {static_margin_cal:.1f} cal. Sensitive to winds; needs steady "
              f"thrust-vector control.")
        event("PITCH_OSCILLATION", 0.1, "Pitch oscillation through max-Q")
    elif static_margin_cal > 3.0:
        issue("OVERSTABLE", "INFO", "Over-stable (weathercocks strongly)",
              f"Static margin {static_margin_cal:.1f} cal. Vehicle will turn hard into the "
              f"relative wind, risking high angle-of-attack loads.")
        event("WEATHERCOCK", 0.08, "Strong weathercock into crosswind")

    if control == "NONE" and stability != "STABLE":
        issue("NO_TVC", "CRITICAL", "No gimballed thrust for steering",
              "All engines are fixed (no thrust-vector control); the vehicle cannot "
              "actively correct attitude.")

    if fineness > 18:
        issue("SLENDER", "WARN", "Very slender airframe",
              f"Fineness ratio {fineness:.0f}:1. Prone to aeroelastic bending and pogo "
              f"coupling under load.")
        event("AEROELASTIC", 0.12 + 0.01 * (fineness - 18),
              "Structural bending / pogo at max-Q")
    elif fineness < 5:
        issue("STUBBY", "WARN", "Stubby, high-drag airframe",
              f"Fineness ratio {fineness:.1f}:1. Bluff shape raises drag and max-Q losses.")

    if twr < 1.0:
        issue("NO_LIFT", "CRITICAL", "Insufficient thrust to lift off",
              f"Liftoff TWR {twr:.2f} < 1.0 — the vehicle cannot leave the pad.")
        event("FAILS_TO_LIFT", 0.95, "Fails to clear the tower (TWR below 1)")
    elif twr < 1.2:
        issue("LOW_TWR", "WARN", "Low liftoff TWR",
              f"TWR {twr:.2f}. Sluggish ascent and heavy gravity losses.")
        event("GRAVITY_LOSS", 0.08, "Excessive gravity losses, downrange shortfall")
    elif twr > 3.8:
        issue("HIGH_TWR", "WARN", "Very high TWR",
              f"TWR {twr:.2f}. Rapid acceleration drives high dynamic pressure and aero loads.")
        event("HIGH_AERO_LOADS", 0.12, "Airframe over-stress from high acceleration")

    if maxq_level in ("HIGH", "SEVERE"):
        sev = "CRITICAL" if maxq_level == "SEVERE" else "WARN"
        issue("MAXQ", sev, f"{maxq_level.title()} dynamic pressure at max-Q",
              f"Estimated max-Q is {maxq_level.lower()}; structural margins at transonic "
              f"flight are reduced.")
        event("MAXQ_STRUCT", 0.10 if maxq_level == "HIGH" else 0.22,
              "Structural failure at max-Q")

    # Blunt nose drag (large bluff payload/command at the very top)
    top = parts[0]
    if top.module_type in (ModuleType.PAYLOAD, ModuleType.COMMAND) and widths[0] >= body_d * 0.95:
        issue("BLUNT_NOSE", "INFO", "Blunt forward section",
              "The nose payload/capsule is near full body diameter with no fairing — "
              "elevated forward drag.")

    # ── Verdict ──
    sev_rank = {"CRITICAL": 3, "WARN": 2, "INFO": 1}
    worst = max((sev_rank[i["severity"]] for i in issues), default=0)
    verdict = ("NOT FLIGHT-WORTHY" if worst >= 3 else
               "MARGINAL" if worst == 2 else "FLIGHT-WORTHY")

    return {
        "length": round(total_len, 1),
        "diameter": round(body_d, 2),
        "finenessRatio": round(fineness, 1),
        "comFromNose": round(com, 2),
        "copFromNose": round(cop, 2),
        "comFraction": round(com / total_len, 3) if total_len else 0,
        "copFraction": round(cop / total_len, 3) if total_len else 0,
        "staticMarginCal": round(static_margin_cal, 2),
        "stability": stability,
        "stable": stability == "STABLE",
        "twr": round(twr, 2),
        "dragCoef": round(cd, 2),
        "ballisticCoef": round(ballistic),
        "maxQLevel": maxq_level,
        "controlAuthority": control,
        "gimbalFraction": round(gimbal_frac, 2),
        "verdict": verdict,
        "issues": issues,
        "flightEvents": events,
        # silhouette for drawing (nose→tail)
        "profile": [
            {
                "name": parts[i].name,
                "type": parts[i].module_type.name,
                "width": round(min(widths[i], body_d), 2),
                "length": round(lengths[i], 2),
                "posFrac": round(centers[i] / total_len, 3) if total_len else 0,
                "massFrac": round(masses[i] / msum, 3),
            }
            for i in range(len(parts))
        ],
    }


def _empty() -> dict:
    return {
        "length": 0, "diameter": 0, "finenessRatio": 0,
        "comFromNose": 0, "copFromNose": 0, "comFraction": 0, "copFraction": 0,
        "staticMarginCal": 0, "stability": "UNSTABLE", "stable": False,
        "twr": 0, "dragCoef": 0, "ballisticCoef": 0, "maxQLevel": "LOW",
        "controlAuthority": "NONE", "gimbalFraction": 0,
        "verdict": "NOT FLIGHT-WORTHY",
        "issues": [{"code": "EMPTY", "severity": "CRITICAL", "title": "No parts",
                    "detail": "Add parts to assess flight worthiness."}],
        "flightEvents": [], "profile": [],
    }
