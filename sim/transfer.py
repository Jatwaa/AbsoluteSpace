"""Transfer window calculations: phase angles, optimal launch timing, delta-v tables."""

import math
from dataclasses import dataclass
from typing import Optional
from .bodies import CelestialBody, G, AU
from .physics import (
    hohmann_delta_v, hohmann_transfer_time, phase_angle_required,
    escape_delta_v, launch_delta_v, parking_to_transfer_dv,
)

DAY = 86400.0
YEAR = 365.25 * DAY


@dataclass
class TransferWindow:
    origin: str
    destination: str
    departure_time: float          # seconds from J2000
    arrival_time: float
    dv_departure: float            # m/s  (includes escape from origin)
    dv_arrival: float              # m/s  (capture into destination orbit)
    dv_total: float
    transfer_duration: float       # seconds
    phase_angle_at_departure: float  # rad (actual)
    phase_angle_required: float      # rad (ideal)

    @property
    def departure_date_str(self) -> str:
        return seconds_to_date(self.departure_time)

    @property
    def arrival_date_str(self) -> str:
        return seconds_to_date(self.arrival_time)

    @property
    def duration_days(self) -> float:
        return self.transfer_duration / DAY

    @property
    def quality(self) -> str:
        """Qualitative window quality based on dv_total."""
        if self.dv_total < 5000:
            return "OPTIMAL"
        elif self.dv_total < 6500:
            return "GOOD"
        elif self.dv_total < 8000:
            return "FAIR"
        else:
            return "COSTLY"

    def summary(self) -> str:
        return (
            f"  Window   : {self.origin} → {self.destination}\n"
            f"  Depart   : {self.departure_date_str}\n"
            f"  Arrive   : {self.arrival_date_str}\n"
            f"  Duration : {self.duration_days:.0f} days\n"
            f"  ΔV total : {self.dv_total:.0f} m/s\n"
            f"  Quality  : {self.quality}"
        )


def seconds_to_date(t: float) -> str:
    """Convert J2000 seconds to a human-readable approximate date."""
    # J2000 = Jan 1, 2000, 12:00 UTC
    days = t / DAY
    year = 2000 + int(days / 365.25)
    day_of_year = int(days % 365.25)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    days_per_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    month_idx = 0
    for i, d in enumerate(days_per_month):
        if day_of_year <= d:
            month_idx = i
            break
        day_of_year -= d
    return f"{max(1, day_of_year):02d} {months[month_idx]} {year}"


def current_phase_angle(origin: CelestialBody, dest: CelestialBody, t: float) -> float:
    """Actual phase angle of destination ahead of origin at time t."""
    ox, oy = origin.position_at(t)
    dx, dy = dest.position_at(t)
    angle_o = math.atan2(oy, ox) % (2 * math.pi)
    angle_d = math.atan2(dy, dx) % (2 * math.pi)
    return (angle_d - angle_o) % (2 * math.pi)


def hohmann_windows(
    origin: CelestialBody,
    dest: CelestialBody,
    sun: CelestialBody,
    t_start: float,
    n_windows: int = 5,
    search_days: float = 5000,
) -> list[TransferWindow]:
    """Find next N Hohmann transfer windows by scanning phase angle alignment."""
    mu_sun = G * sun.mass
    r1 = origin.semi_major_axis
    r2 = dest.semi_major_axis
    if r1 == 0 or r2 == 0:
        return []

    # Heliocentric v-infinity at each planet
    dv1_helio, dv2_helio = hohmann_delta_v(r1, r2, mu_sun)
    tof = hohmann_transfer_time(r1, r2, mu_sun)

    # Departure: single Oberth burn from parking orbit with v_inf = dv1_helio
    dv_depart = parking_to_transfer_dv(dv1_helio, G * origin.mass,
                                       body_radius=origin.radius)
    # Arrival capture: brake from hyperbola into parking orbit
    dv_arrive = parking_to_transfer_dv(dv2_helio, G * dest.mass,
                                       body_radius=dest.radius)
    dv_total_base = dv_depart + dv_arrive

    phi_req = phase_angle_required(r1, r2, mu_sun)

    # Synodic period = time between windows
    if origin.orbital_period and dest.orbital_period:
        synodic = abs(1 / (1/origin.orbital_period - 1/dest.orbital_period))
    else:
        synodic = search_days * DAY

    windows: list[TransferWindow] = []
    step = DAY * 2  # 2-day scan resolution
    t = t_start
    last_diff = None
    t_end = t_start + search_days * DAY

    while t < t_end and len(windows) < n_windows:
        phi_actual = current_phase_angle(origin, dest, t)
        diff = (phi_actual - phi_req + math.pi) % (2 * math.pi) - math.pi  # [-pi, pi]

        if last_diff is not None and last_diff * diff < 0 and abs(last_diff) < 0.3:
            # Sign change in difference → window crossing; refine with bisection
            t_lo, t_hi = t - step, t
            for _ in range(30):
                t_mid = (t_lo + t_hi) / 2
                d = (current_phase_angle(origin, dest, t_mid) - phi_req + math.pi) % (2*math.pi) - math.pi
                if d * (current_phase_angle(origin, dest, t_lo) - phi_req + math.pi - math.pi*2) < 0:
                    t_hi = t_mid
                else:
                    t_lo = t_mid
            t_dep = (t_lo + t_hi) / 2
            phi_at_dep = current_phase_angle(origin, dest, t_dep)

            win = TransferWindow(
                origin=origin.name,
                destination=dest.name,
                departure_time=t_dep,
                arrival_time=t_dep + tof,
                dv_departure=dv_depart,
                dv_arrival=dv_arrive,
                dv_total=dv_total_base,
                transfer_duration=tof,
                phase_angle_at_departure=phi_at_dep,
                phase_angle_required=phi_req,
            )
            windows.append(win)
            t += synodic * 0.8  # skip forward past this window

        last_diff = diff
        t += step

    return windows


def porkchop_sample(
    origin: CelestialBody,
    dest: CelestialBody,
    sun: CelestialBody,
    t_start: float,
    days_range: int = 800,
    samples: int = 40,
) -> list[dict]:
    """
    Sample delta-v over a range of departure times for a pork-chop plot.
    Returns list of {t_dep, dv_total, duration_days}.
    """
    mu = G * sun.mass
    r1 = origin.semi_major_axis
    r2 = dest.semi_major_axis
    if r1 == 0 or r2 == 0:
        return []

    dv1_base, dv2_base = hohmann_delta_v(r1, r2, mu)
    tof_base = hohmann_transfer_time(r1, r2, mu)
    dv_esc = escape_delta_v(origin.radius, G * origin.mass)
    dv_cap = escape_delta_v(dest.radius, G * dest.mass)
    phi_req = phase_angle_required(r1, r2, mu)

    results = []
    for i in range(samples):
        t = t_start + i * (days_range * DAY / samples)
        phi_actual = current_phase_angle(origin, dest, t)
        phi_err = abs((phi_actual - phi_req + math.pi) % (2*math.pi) - math.pi)
        # Penalty for non-optimal phase: crude linear model
        penalty = phi_err * 500  # ~500 m/s per radian off
        dv_total = dv1_base + dv_esc + dv2_base + dv_cap * 0.4 + penalty
        results.append({
            "t_dep": t,
            "dv_total": dv_total,
            "duration_days": tof_base / DAY,
        })
    return results


def mission_delta_v_budget(
    origin: CelestialBody,
    dest: CelestialBody,
    sun: CelestialBody,
    include_return: bool = False,
    parking_orbit_alt: float = 200_000,
) -> dict:
    """Full mission delta-v breakdown."""
    mu = G * sun.mass
    r1 = origin.semi_major_axis
    r2 = dest.semi_major_axis

    dv_launch  = launch_delta_v(origin, parking_orbit_alt)
    dv1_helio, dv2_helio = hohmann_delta_v(r1, r2, mu)
    dv_depart  = parking_to_transfer_dv(dv1_helio, G * origin.mass,
                                        parking_orbit_alt, origin.radius)
    dv_arrive  = parking_to_transfer_dv(dv2_helio, G * dest.mass,
                                        parking_orbit_alt, dest.radius)
    tof = hohmann_transfer_time(r1, r2, mu)

    budget = {
        "surface_to_LEO":    dv_launch,
        "LEO_to_transfer":   dv_depart,
        "arrival_capture":   dv_arrive,
        "total_one_way":     dv_launch + dv_depart + dv_arrive,
        "transfer_days":     tof / DAY,
    }
    if include_return:
        budget["return_total"] = budget["total_one_way"] * 0.9
        budget["total_mission"] = budget["total_one_way"] + budget["return_total"]
    return budget
