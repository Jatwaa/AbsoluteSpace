"""
Deterministic weather simulation for launch sites.

Each (site, date) pair produces the same forecast, so the user can explore
launch windows consistently.  The model is seeded from (site_id, year,
day_of_year) and uses a simple layered noise approach:

  conditions = climate_baseline
             + seasonal_factor(month)
             + diurnal_factor(hour)
             + daily_noise(seed)
             + event(storm/fog probability)

All outputs are in SI units unless noted.
"""

from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import Optional

from .launch_sites import LaunchSite

DAY = 86400.0
HOUR = 3600.0


# ── Weather state ─────────────────────────────────────────────────────────────

@dataclass
class WeatherConditions:
    hour: int                    # 0-23 local time
    temp_c: float                # °C surface
    wind_speed: float            # m/s at 10m
    wind_dir: int                # degrees (0=N, 90=E)
    wind_upper: float            # m/s at ~18 km (upper atmosphere)
    cloud_cover: float           # 0-1 fraction
    cloud_base_ft: int           # ft AGL lowest cloud layer
    precipitation: str           # "None" | "Light" | "Moderate" | "Heavy"
    lightning: bool              # lightning within 10 nm
    visibility_km: float         # km
    humidity: float              # 0-1
    sea_state: Optional[str] = None  # for coastal sites

    @property
    def sky_text(self) -> str:
        if self.cloud_cover < 0.125:
            return "CLR"
        elif self.cloud_cover < 0.375:
            return f"FEW {self.cloud_base_ft:,}ft"
        elif self.cloud_cover < 0.625:
            return f"SCT {self.cloud_base_ft:,}ft"
        elif self.cloud_cover < 0.875:
            return f"BKN {self.cloud_base_ft:,}ft"
        else:
            return f"OVC {self.cloud_base_ft:,}ft"

    @property
    def wind_cardinal(self) -> str:
        dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
                "S","SSW","SW","WSW","W","WNW","NW","NNW"]
        return dirs[round(self.wind_dir / 22.5) % 16]

    @property
    def wind_kt(self) -> float:
        return self.wind_speed * 1.944

    @property
    def beaufort(self) -> int:
        ws = self.wind_speed
        for b, limit in enumerate([0.3,1.6,3.4,5.5,8.0,10.8,13.9,17.2,20.8,24.5,28.5,32.7]):
            if ws < limit:
                return b
        return 12


@dataclass
class LaunchRuleCheck:
    name: str
    go: bool
    value: str
    limit: str


# ── Climate baselines ─────────────────────────────────────────────────────────
# (temp_c, wind_mean, wind_var, cloud_base, rain_prob, storm_prob_pm)

_CLIMATE = {
    "tropical":     dict(temp=30, t_var=4, w_mean=6,  w_var=5,  cloud=0.50, rain=0.40, storm_pm=0.35, base_ft=2500),
    "subtropical":  dict(temp=26, t_var=7, w_mean=5,  w_var=6,  cloud=0.30, rain=0.25, storm_pm=0.20, base_ft=4000),
    "temperate":    dict(temp=14, t_var=9, w_mean=7,  w_var=8,  cloud=0.40, rain=0.35, storm_pm=0.08, base_ft=5000),
    "arid":         dict(temp=20, t_var=15,w_mean=8,  w_var=9,  cloud=0.10, rain=0.05, storm_pm=0.05, base_ft=8000),
    "continental":  dict(temp=8,  t_var=18,w_mean=9,  w_var=10, cloud=0.35, rain=0.30, storm_pm=0.10, base_ft=5000),
}

# Monthly seasonal offsets (temp delta, rain_multiplier) indexed 1-12
_SEASONAL: dict[str, list[tuple[float, float]]] = {
    "tropical":    [(-1,.6),(-1,.5),(.5,.8),(1,1.2),(2,1.5),(2,1.8),(2,2.0),(2,2.0),(1,1.8),(0,1.4),(-1,.9),(-1,.6)],
    "subtropical": [(-4,.7),(-3,.6),(-1,.8),(1,.9),(3,1.1),(4,1.3),(5,1.4),(5,1.3),(3,1.1),(1,.9),(-2,.7),(-3,.7)],
    "temperate":   [(-8,1.1),(-7,1.0),(-4,.9),(-1,.9),(2,.9),(5,.8),(7,.7),(7,.7),(4,.9),(1,1.0),(-3,1.2),(-6,1.2)],
    "arid":        [(-10,.8),(-8,.7),(-3,.8),(5,.9),(10,.6),(15,.4),(16,.5),(15,.5),(10,.6),(4,.7),(-3,.8),(-8,.9)],
    "continental": [(-20,.9),(-18,.8),(-10,.9),(-3,1.0),(3,1.0),(8,.9),(10,.8),(9,.8),(4,.9),(-2,1.0),(-10,1.1),(-17,1.0)],
}


class WeatherSimulator:
    """
    Produces deterministic weather conditions for a site at a given sim time
    (J2000 seconds).  Results are reproducible for the same site+day.
    """

    def __init__(self):
        self._cache: dict[tuple, WeatherConditions] = {}

    def _seed_for(self, site: LaunchSite, year: int, doy: int, hour: int) -> int:
        h = hash((site.id, year, doy, hour)) & 0xFFFF_FFFF
        return h if h > 0 else h + 0x8000_0000

    def conditions_at(self, site: LaunchSite, sim_time: float) -> WeatherConditions:
        """Conditions at a specific sim_time (J2000 seconds)."""
        year, month, doy, hour, minute = _j2000_to_calendar(sim_time)
        # Interpolate between two hourly samples
        c0 = self._hourly(site, year, month, doy, hour)
        c1 = self._hourly(site, year, month, doy, (hour + 1) % 24)
        t = minute / 60.0
        return _lerp_conditions(c0, c1, t)

    def daily_forecast(self, site: LaunchSite, sim_time: float) -> list[WeatherConditions]:
        """24-hour forecast, one entry per hour starting at midnight."""
        year, month, doy, _, _ = _j2000_to_calendar(sim_time)
        return [self._hourly(site, year, month, doy, h) for h in range(24)]

    def _hourly(self, site: LaunchSite, year: int, month: int,
                doy: int, hour: int) -> WeatherConditions:
        key = (site.id, year, doy, hour)
        if key in self._cache:
            return self._cache[key]

        rng = random.Random(self._seed_for(site, year, doy, hour))
        bl = _CLIMATE[site.climate]
        seas = _SEASONAL[site.climate][month - 1]
        seas_t, seas_rain = seas

        # ── Temperature ──
        diurnal_t = 4 * math.sin(math.pi * (hour - 6) / 12)
        temp = bl["temp"] + seas_t + diurnal_t + rng.gauss(0, 1.5)

        # ── Wind ──
        # Diurnal: calmer at dawn, stronger in afternoon
        diurnal_w = 1 + 0.4 * math.sin(math.pi * (hour - 4) / 12)
        w_base = bl["w_mean"] * diurnal_w * seas_rain
        wind_speed = max(0, rng.gauss(w_base, bl["w_var"] * 0.4))
        # Wind gusts / storm spikes
        if rng.random() < 0.05:  # 5% chance of windy spell
            wind_speed *= rng.uniform(1.5, 2.5)
        wind_dir = (rng.randint(0, 359) + int(site.latitude * 2)) % 360

        # Upper-level winds (jet stream influence)
        upper_base = 15 + abs(site.latitude) * 0.5
        wind_upper = max(0, rng.gauss(upper_base, 10))

        # ── Clouds ──
        # Afternoon convection in tropical/subtropical
        conv_hour = 15 if site.climate in ("tropical", "subtropical") else 14
        conv_factor = max(0, math.sin(math.pi * max(0, hour - 11) / 8)) if hour >= 11 else 0
        cloud_prob = (bl["cloud"] + bl["storm_pm"] * conv_factor) * seas_rain
        cloud_cover = min(1.0, rng.betavariate(2, 4) * cloud_prob * 2.5) if rng.random() < cloud_prob * 1.5 else rng.uniform(0, 0.2)
        cloud_base_ft = int(bl["base_ft"] * rng.uniform(0.7, 1.3))

        # ── Precipitation ──
        rain_base = bl["rain"] * seas_rain
        # Afternoon storms
        if hour >= 13 and hour <= 19 and site.climate in ("tropical", "subtropical"):
            rain_base *= 1.5 + conv_factor

        r = rng.random()
        if r < rain_base * 0.1:
            precipitation = "Heavy"
            cloud_cover = min(1.0, cloud_cover + 0.4)
        elif r < rain_base * 0.35:
            precipitation = "Moderate"
            cloud_cover = min(1.0, cloud_cover + 0.2)
        elif r < rain_base * 0.7:
            precipitation = "Light"
        else:
            precipitation = "None"

        # ── Lightning ──
        storm_prob = bl["storm_pm"] * seas_rain * conv_factor if hour >= 12 else bl["storm_pm"] * 0.1
        lightning = rng.random() < storm_prob * 0.6 and precipitation != "None"

        # ── Visibility ──
        vis_base = 20.0
        if precipitation == "Heavy":
            vis_base = rng.uniform(1, 5)
        elif precipitation == "Moderate":
            vis_base = rng.uniform(4, 10)
        elif precipitation == "Light":
            vis_base = rng.uniform(8, 15)
        elif cloud_cover > 0.8 and rng.random() < 0.2:
            vis_base = rng.uniform(4, 10)  # fog/haze
        vis = min(50, max(0.5, rng.gauss(vis_base, 2)))

        # ── Humidity ──
        humidity = 0.5 + 0.3 * math.sin(math.pi * (hour + 6) / 24)
        if site.climate == "tropical":
            humidity = min(1.0, humidity + 0.25)
        elif site.climate == "arid":
            humidity = max(0.05, humidity - 0.3)

        cond = WeatherConditions(
            hour=hour,
            temp_c=round(temp, 1),
            wind_speed=round(wind_speed, 1),
            wind_dir=wind_dir,
            wind_upper=round(wind_upper, 1),
            cloud_cover=cloud_cover,
            cloud_base_ft=cloud_base_ft,
            precipitation=precipitation,
            lightning=lightning,
            visibility_km=round(vis, 1),
            humidity=round(humidity, 2),
        )
        self._cache[key] = cond
        return cond

    def launch_rules(self, site: LaunchSite, cond: WeatherConditions) -> list[LaunchRuleCheck]:
        """Evaluate all launch weather rules. Returns list of checks."""
        checks = [
            LaunchRuleCheck(
                "Surface Winds",
                cond.wind_speed <= site.max_wind_surface,
                f"{cond.wind_speed:.1f} m/s ({cond.wind_kt:.0f} kt)",
                f"≤{site.max_wind_surface:.0f} m/s",
            ),
            LaunchRuleCheck(
                "Upper Winds",
                cond.wind_upper <= site.max_wind_upper,
                f"{cond.wind_upper:.0f} m/s",
                f"≤{site.max_wind_upper:.0f} m/s",
            ),
            LaunchRuleCheck(
                "Visibility",
                cond.visibility_km * 1000 >= site.min_visibility,
                f"{cond.visibility_km:.1f} km",
                f"≥{site.min_visibility/1000:.1f} km",
            ),
            LaunchRuleCheck(
                "Lightning",
                not cond.lightning,
                "DETECTED" if cond.lightning else "NONE",
                "NONE within 10 nm",
            ),
            LaunchRuleCheck(
                "Precipitation",
                cond.precipitation in ("None", "Light"),
                cond.precipitation,
                "None or Light only",
            ),
            LaunchRuleCheck(
                "Cloud Cover",
                not (cond.cloud_cover > 0.875 and cond.cloud_base_ft < 2500),
                cond.sky_text,
                "No OVC below 2500ft",
            ),
        ]
        return checks

    def is_go(self, site: LaunchSite, cond: WeatherConditions) -> tuple[bool, list[str]]:
        """Returns (go, [list of NO-GO reasons])."""
        checks = self.launch_rules(site, cond)
        reasons = [f"{c.name}: {c.value} (limit {c.limit})" for c in checks if not c.go]
        return len(reasons) == 0, reasons


# ── Calendar helpers ──────────────────────────────────────────────────────────

def _j2000_to_calendar(t: float) -> tuple[int, int, int, int, int]:
    """Convert J2000 seconds to (year, month, day_of_year, hour, minute)."""
    # J2000 epoch = 2000-01-01 12:00 UTC
    days_since = t / DAY + 0.5  # shift 12h so day 0 = Jan 1 2000 00:00
    year = 2000
    while True:
        dy = 366 if _is_leap(year) else 365
        if days_since < dy:
            break
        days_since -= dy
        year += 1
    doy = int(days_since) + 1
    frac_day = days_since - int(days_since)
    hour = int(frac_day * 24)
    minute = int((frac_day * 24 - hour) * 60)

    # Approximate month
    month_days = [31, 29 if _is_leap(year) else 28, 31, 30, 31, 30,
                  31, 31, 30, 31, 30, 31]
    month = 1
    remaining = doy - 1
    for md in month_days:
        if remaining < md:
            break
        remaining -= md
        month += 1

    return year, month, doy, hour, minute


def _is_leap(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or year % 400 == 0


def _lerp_conditions(a: WeatherConditions, b: WeatherConditions,
                     t: float) -> WeatherConditions:
    def l(x, y):
        return x + (y - x) * t
    return WeatherConditions(
        hour=a.hour,
        temp_c=round(l(a.temp_c, b.temp_c), 1),
        wind_speed=round(l(a.wind_speed, b.wind_speed), 1),
        wind_dir=a.wind_dir,
        wind_upper=round(l(a.wind_upper, b.wind_upper), 1),
        cloud_cover=l(a.cloud_cover, b.cloud_cover),
        cloud_base_ft=int(l(a.cloud_base_ft, b.cloud_base_ft)),
        precipitation=a.precipitation,
        lightning=a.lightning,
        visibility_km=round(l(a.visibility_km, b.visibility_km), 1),
        humidity=round(l(a.humidity, b.humidity), 2),
    )


# Module-level singleton
simulator = WeatherSimulator()
