"""Physics and orbital mechanics: patched conics, vis-viva, maneuver planning."""

import math
from typing import Tuple, Optional
from .bodies import CelestialBody, G, AU

TWO_PI = 2 * math.pi


# ── Keplerian orbit representation ───────────────────────────────────────────

class Orbit:
    """Sun-centered Keplerian orbit (2D ecliptic plane)."""

    def __init__(self, semi_major_axis: float, eccentricity: float,
                 arg_periapsis: float, true_anomaly_epoch: float,
                 epoch: float, mu: float):
        self.a = semi_major_axis      # m
        self.e = eccentricity
        self.omega = arg_periapsis    # rad
        self.nu0 = true_anomaly_epoch # rad at epoch
        self.t0 = epoch               # s
        self.mu = mu                  # gravitational parameter of central body

    @property
    def period(self) -> float:
        if self.a <= 0:
            return float("inf")
        return TWO_PI * math.sqrt(self.a ** 3 / self.mu)

    @property
    def semi_latus_rectum(self) -> float:
        return self.a * (1 - self.e ** 2)

    def radius_at_nu(self, nu: float) -> float:
        return self.semi_latus_rectum / (1 + self.e * math.cos(nu))

    def periapsis(self) -> float:
        return self.a * (1 - self.e)

    def apoapsis(self) -> float:
        return self.a * (1 + self.e)

    def mean_motion(self) -> float:
        if self.a <= 0:
            return 0.0
        return math.sqrt(self.mu / self.a ** 3)

    def true_anomaly_at(self, t: float) -> float:
        dt = t - self.t0
        n = self.mean_motion()
        M0 = true_to_mean(self.nu0, self.e)
        M = (M0 + n * dt) % TWO_PI
        E = solve_kepler(M, self.e)
        return eccentric_to_true(E, self.e)

    def position_at(self, t: float) -> Tuple[float, float]:
        nu = self.true_anomaly_at(t)
        r = self.radius_at_nu(nu)
        theta = nu + self.omega
        return (r * math.cos(theta), r * math.sin(theta))

    def velocity_at(self, t: float) -> Tuple[float, float]:
        nu = self.true_anomaly_at(t)
        r = self.radius_at_nu(nu)
        p = self.semi_latus_rectum
        h = math.sqrt(self.mu * p)
        vr = (self.mu / h) * self.e * math.sin(nu)
        vt = (self.mu / h) * (1 + self.e * math.cos(nu))
        theta = nu + self.omega
        vx = vr * math.cos(theta) - vt * math.sin(theta)
        vy = vr * math.sin(theta) + vt * math.cos(theta)
        return (vx, vy)

    @property
    def speed_at_periapsis(self) -> float:
        return math.sqrt(self.mu * (2 / self.periapsis() - 1 / self.a))

    @property
    def speed_at_apoapsis(self) -> float:
        return math.sqrt(self.mu * (2 / self.apoapsis() - 1 / self.a))

    @property
    def vis_viva_at(self):
        def _f(r: float) -> float:
            return math.sqrt(self.mu * (2 / r - 1 / self.a))
        return _f


# ── Kepler helpers ────────────────────────────────────────────────────────────

def solve_kepler(M: float, e: float, tol: float = 1e-12) -> float:
    """Newton-Raphson: M = E - e*sin(E)."""
    E = M
    for _ in range(100):
        dE = (M - E + e * math.sin(E)) / (1 - e * math.cos(E))
        E += dE
        if abs(dE) < tol:
            break
    return E % TWO_PI


def eccentric_to_true(E: float, e: float) -> float:
    return 2 * math.atan2(math.sqrt(1 + e) * math.sin(E / 2),
                          math.sqrt(1 - e) * math.cos(E / 2)) % TWO_PI


def true_to_eccentric(nu: float, e: float) -> float:
    return 2 * math.atan2(math.sqrt(1 - e) * math.sin(nu / 2),
                          math.sqrt(1 + e) * math.cos(nu / 2)) % TWO_PI


def true_to_mean(nu: float, e: float) -> float:
    E = true_to_eccentric(nu, e)
    return (E - e * math.sin(E)) % TWO_PI


# ── Orbit construction from state vectors ────────────────────────────────────

def orbit_from_state(pos: Tuple[float, float], vel: Tuple[float, float],
                     mu: float, t: float) -> Orbit:
    """Construct an Orbit from position/velocity and gravitational parameter."""
    x, y = pos
    vx, vy = vel
    r = math.sqrt(x**2 + y**2)
    v = math.sqrt(vx**2 + vy**2)
    if r == 0 or v == 0:
        return Orbit(0, 0, 0, 0, t, mu)

    # Specific angular momentum (z-component)
    h = x * vy - y * vx

    # Semi-latus rectum
    p = h**2 / mu

    # Eccentricity vector
    ex = (v**2 / mu - 1/r) * x - (x*vx + y*vy) / mu * vx
    ey = (v**2 / mu - 1/r) * y - (x*vx + y*vy) / mu * vy
    e = math.sqrt(ex**2 + ey**2)

    # Semi-major axis via energy
    energy = v**2/2 - mu/r
    if abs(energy) < 1e-10:
        a = float("inf")
    else:
        a = -mu / (2 * energy)

    # Argument of periapsis (angle of eccentricity vector)
    omega = math.atan2(ey, ex) % TWO_PI

    # True anomaly at current position
    nu = (math.atan2(y, x) - omega) % TWO_PI

    return Orbit(a, min(e, 0.9999), omega, nu, t, mu)


# ── Maneuver calculations ─────────────────────────────────────────────────────

def hohmann_delta_v(r1: float, r2: float, mu: float) -> Tuple[float, float]:
    """Heliocentric delta-v for Hohmann transfer: departure and arrival burns."""
    a_transfer = (r1 + r2) / 2
    v1_circ = math.sqrt(mu / r1)
    v2_circ = math.sqrt(mu / r2)
    v_transfer_peri = math.sqrt(mu * (2/r1 - 1/a_transfer))
    v_transfer_apo  = math.sqrt(mu * (2/r2 - 1/a_transfer))
    dv1 = abs(v_transfer_peri - v1_circ)   # m/s excess at departure planet's orbit
    dv2 = abs(v2_circ - v_transfer_apo)    # m/s excess at arrival planet's orbit
    return (dv1, dv2)


def hohmann_transfer_time(r1: float, r2: float, mu: float) -> float:
    """Time of flight for Hohmann transfer (half period of transfer ellipse)."""
    a = (r1 + r2) / 2
    return math.pi * math.sqrt(a**3 / mu)


def phase_angle_required(r1: float, r2: float, mu: float) -> float:
    """Required phase angle of target ahead of spacecraft at departure for Hohmann."""
    tof = hohmann_transfer_time(r1, r2, mu)
    n2 = math.sqrt(mu / r2**3)
    phi = math.pi - n2 * tof
    return phi % TWO_PI


def parking_to_transfer_dv(v_inf: float, body_mu: float,
                            parking_alt: float = 200_000,
                            body_radius: float = 6.371e6) -> float:
    """
    Delta-v from circular parking orbit to hyperbolic escape with excess speed v_inf.
    Single Oberth-effect burn: dv = sqrt(v_inf^2 + v_esc^2) - v_park
    """
    r_park = body_radius + parking_alt
    v_park = math.sqrt(body_mu / r_park)
    v_hyp  = math.sqrt(v_inf**2 + 2 * body_mu / r_park)
    return v_hyp - v_park


def escape_delta_v(surface_r: float, body_mu: float, parking_alt: float = 200_000) -> float:
    """Delta-v to escape a body's SOI from low parking orbit (v_infinity = 0)."""
    r_park = surface_r + parking_alt
    v_park = math.sqrt(body_mu / r_park)
    v_esc  = math.sqrt(2 * body_mu / r_park)
    return v_esc - v_park


def launch_delta_v(body: CelestialBody, parking_alt: float = 200_000) -> float:
    """Total delta-v from surface to low parking orbit (simplified with gravity+drag loss)."""
    r_park = body.radius + parking_alt
    v_orbit = math.sqrt(body.mu / r_park)
    drag_gravity_loss = 1500 * (body.surface_gravity / 9.81)
    return v_orbit + drag_gravity_loss


# ── Trajectory propagation (simple 2-body, patched conic) ────────────────────

def propagate_orbit(orbit: Orbit, dt: float, steps: int) -> list[Tuple[float, float]]:
    """Generate trajectory sample points for rendering."""
    t0 = orbit.t0
    points = []
    for i in range(steps):
        t = t0 + i * (dt / steps)
        points.append(orbit.position_at(t))
    return points


def angle_between(v1: Tuple[float, float], v2: Tuple[float, float]) -> float:
    """Angle in radians between two 2D vectors."""
    d = math.sqrt(v1[0]**2 + v1[1]**2) * math.sqrt(v2[0]**2 + v2[1]**2)
    if d == 0:
        return 0.0
    cos_a = (v1[0]*v2[0] + v1[1]*v2[1]) / d
    return math.acos(max(-1.0, min(1.0, cos_a)))


def vec_add(a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float]:
    return (a[0] + b[0], a[1] + b[1])


def vec_sub(a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float]:
    return (a[0] - b[0], a[1] - b[1])


def vec_scale(a: Tuple[float, float], s: float) -> Tuple[float, float]:
    return (a[0] * s, a[1] * s)


def vec_mag(a: Tuple[float, float]) -> float:
    return math.sqrt(a[0]**2 + a[1]**2)


def vec_norm(a: Tuple[float, float]) -> Tuple[float, float]:
    m = vec_mag(a)
    if m == 0:
        return (0.0, 0.0)
    return (a[0]/m, a[1]/m)
