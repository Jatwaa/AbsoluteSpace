"""Celestial bodies: Keplerian orbital mechanics for the solar system."""

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple

G = 6.674e-11       # m^3 kg^-1 s^-2
AU = 1.496e11       # meters per AU
YEAR = 365.25 * 24 * 3600   # seconds
J2000 = 0.0         # reference epoch (seconds)


@dataclass
class CelestialBody:
    name: str
    mass: float                  # kg
    radius: float                # m
    soi_radius: float            # m  (sphere of influence)
    color: Tuple[int, int, int]
    display_radius: int          # pixels for rendering (visual only)

    # Keplerian elements relative to Sun at J2000
    semi_major_axis: float = 0.0     # m
    eccentricity: float = 0.0
    orbital_period: float = 0.0      # s
    mean_anomaly_epoch: float = 0.0  # rad at J2000
    arg_periapsis: float = 0.0       # rad (longitude of perihelion offset)

    surface_gravity: float = 9.81    # m/s^2
    atmosphere_height: float = 0.0   # m

    parent: Optional["CelestialBody"] = field(default=None, repr=False)

    @property
    def mu(self) -> float:
        return G * self.mass

    def mean_anomaly_at(self, t: float) -> float:
        if self.orbital_period == 0:
            return 0.0
        n = 2 * math.pi / self.orbital_period
        return (self.mean_anomaly_epoch + n * t) % (2 * math.pi)

    def eccentric_anomaly(self, M: float) -> float:
        """Newton-Raphson solve of M = E - e*sin(E)."""
        e = self.eccentricity
        E = M
        for _ in range(100):
            dE = (M - E + e * math.sin(E)) / (1.0 - e * math.cos(E))
            E += dE
            if abs(dE) < 1e-12:
                break
        return E

    def true_anomaly(self, E: float) -> float:
        e = self.eccentricity
        return 2.0 * math.atan2(
            math.sqrt(1 + e) * math.sin(E / 2),
            math.sqrt(1 - e) * math.cos(E / 2),
        )

    def position_at(self, t: float) -> Tuple[float, float]:
        if self.parent is None:
            return (0.0, 0.0)
        M = self.mean_anomaly_at(t)
        E = self.eccentric_anomaly(M)
        nu = self.true_anomaly(E)
        r = self.semi_major_axis * (1 - self.eccentricity * math.cos(E))
        theta = nu + self.arg_periapsis
        return (r * math.cos(theta), r * math.sin(theta))

    def velocity_at(self, t: float) -> Tuple[float, float]:
        """Inertial velocity vector (vx, vy) m/s."""
        if self.parent is None:
            return (0.0, 0.0)
        mu = G * self.parent.mass
        M = self.mean_anomaly_at(t)
        E = self.eccentric_anomaly(M)
        nu = self.true_anomaly(E)
        r = self.semi_major_axis * (1 - self.eccentricity * math.cos(E))
        p = self.semi_major_axis * (1 - self.eccentricity ** 2)
        h = math.sqrt(mu * p)
        vr = (mu / h) * self.eccentricity * math.sin(nu)
        vt = (mu / h) * (1 + self.eccentricity * math.cos(nu))
        theta = nu + self.arg_periapsis
        vx = vr * math.cos(theta) - vt * math.sin(theta)
        vy = vr * math.sin(theta) + vt * math.cos(theta)
        return (vx, vy)

    def orbital_speed_at_radius(self, r: float) -> float:
        """Vis-viva: v = sqrt(mu*(2/r - 1/a))"""
        if self.parent is None or self.semi_major_axis == 0:
            return 0.0
        mu = G * self.parent.mass
        return math.sqrt(mu * (2.0 / r - 1.0 / self.semi_major_axis))

    def circular_speed_at(self, r: float) -> float:
        """Speed for circular orbit at radius r around THIS body."""
        return math.sqrt(self.mu / r)

    def escape_speed_at(self, r: float) -> float:
        return math.sqrt(2 * self.mu / r)


def build_solar_system() -> dict[str, CelestialBody]:
    """Real approximate orbital elements (J2000, ecliptic plane)."""
    sun = CelestialBody(
        name="Sun",
        mass=1.989e30,
        radius=6.96e8,
        soi_radius=float("inf"),
        color=(255, 220, 50),
        display_radius=12,
        surface_gravity=274.0,
    )

    mercury = CelestialBody(
        name="Mercury",
        mass=3.301e23,
        radius=2.44e6,
        soi_radius=1.12e8,
        color=(180, 170, 155),
        display_radius=3,
        semi_major_axis=0.387 * AU,
        eccentricity=0.2056,
        orbital_period=87.97 * 24 * 3600,
        mean_anomaly_epoch=math.radians(174.8),
        arg_periapsis=math.radians(29.1),
        surface_gravity=3.7,
        parent=sun,
    )

    venus = CelestialBody(
        name="Venus",
        mass=4.867e24,
        radius=6.052e6,
        soi_radius=6.16e8,
        color=(220, 200, 130),
        display_radius=5,
        semi_major_axis=0.723 * AU,
        eccentricity=0.0068,
        orbital_period=224.7 * 24 * 3600,
        mean_anomaly_epoch=math.radians(50.4),
        arg_periapsis=math.radians(54.9),
        surface_gravity=8.87,
        atmosphere_height=250000,
        parent=sun,
    )

    earth = CelestialBody(
        name="Earth",
        mass=5.972e24,
        radius=6.371e6,
        soi_radius=9.24e8,
        color=(70, 130, 200),
        display_radius=5,
        semi_major_axis=1.0 * AU,
        eccentricity=0.0167,
        orbital_period=365.25 * 24 * 3600,
        mean_anomaly_epoch=math.radians(357.5),
        arg_periapsis=math.radians(102.9),
        surface_gravity=9.81,
        atmosphere_height=100000,
        parent=sun,
    )

    mars = CelestialBody(
        name="Mars",
        mass=6.417e23,
        radius=3.39e6,
        soi_radius=5.77e8,
        color=(200, 100, 60),
        display_radius=4,
        semi_major_axis=1.524 * AU,
        eccentricity=0.0934,
        orbital_period=686.97 * 24 * 3600,
        mean_anomaly_epoch=math.radians(19.4),
        arg_periapsis=math.radians(286.5),
        surface_gravity=3.72,
        atmosphere_height=11000,
        parent=sun,
    )

    jupiter = CelestialBody(
        name="Jupiter",
        mass=1.898e27,
        radius=7.149e7,
        soi_radius=4.82e10,
        color=(200, 170, 120),
        display_radius=9,
        semi_major_axis=5.203 * AU,
        eccentricity=0.0489,
        orbital_period=4332.6 * 24 * 3600,
        mean_anomaly_epoch=math.radians(20.0),
        arg_periapsis=math.radians(273.9),
        surface_gravity=24.79,
        parent=sun,
    )

    saturn = CelestialBody(
        name="Saturn",
        mass=5.683e26,
        radius=6.027e7,
        soi_radius=5.48e10,
        color=(210, 190, 140),
        display_radius=8,
        semi_major_axis=9.537 * AU,
        eccentricity=0.0565,
        orbital_period=10759.2 * 24 * 3600,
        mean_anomaly_epoch=math.radians(317.0),
        arg_periapsis=math.radians(339.4),
        surface_gravity=10.44,
        parent=sun,
    )

    uranus = CelestialBody(
        name="Uranus",
        mass=8.681e25,
        radius=2.556e7,
        soi_radius=5.18e10,
        color=(150, 210, 230),
        display_radius=6,
        semi_major_axis=19.19 * AU,
        eccentricity=0.0457,
        orbital_period=30688.5 * 24 * 3600,
        mean_anomaly_epoch=math.radians(142.3),
        arg_periapsis=math.radians(96.5),
        surface_gravity=8.69,
        parent=sun,
    )

    neptune = CelestialBody(
        name="Neptune",
        mass=1.024e26,
        radius=2.476e7,
        soi_radius=8.67e10,
        color=(60, 80, 200),
        display_radius=6,
        semi_major_axis=30.07 * AU,
        eccentricity=0.0113,
        orbital_period=60182.0 * 24 * 3600,
        mean_anomaly_epoch=math.radians(256.2),
        arg_periapsis=math.radians(273.2),
        surface_gravity=11.15,
        parent=sun,
    )

    bodies = {b.name: b for b in [sun, mercury, venus, earth, mars, jupiter, saturn, uranus, neptune]}
    return bodies
