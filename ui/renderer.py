"""Solar system viewport renderer: zoom, pan, planet orbits, spacecraft."""

import math
import pygame
from typing import Optional, Tuple

from sim.bodies import CelestialBody, AU
from sim.craft import Spacecraft
from sim.mission import Mission, MissionPhase
from sim.transfer import TransferWindow
from . import theme

TWO_PI = 2 * math.pi
ORBIT_POINTS = 180


class Camera:
    def __init__(self, screen_w: int, screen_h: int):
        self.cx = screen_w // 2
        self.cy = screen_h // 2
        self.scale = 180 / AU   # pixels per meter (default: 1 AU = 180px)
        self.dragging = False
        self._drag_start: Tuple[int, int] = (0, 0)
        self._cam_start: Tuple[int, int] = (0, 0)

    def world_to_screen(self, x: float, y: float) -> Tuple[int, int]:
        sx = int(self.cx + x * self.scale)
        sy = int(self.cy - y * self.scale)   # Y flipped (screen Y down)
        return (sx, sy)

    def screen_to_world(self, sx: int, sy: int) -> Tuple[float, float]:
        x = (sx - self.cx) / self.scale
        y = -(sy - self.cy) / self.scale
        return (x, y)

    def zoom(self, factor: float, pivot_sx: int, pivot_sy: int):
        wx, wy = self.screen_to_world(pivot_sx, pivot_sy)
        self.scale *= factor
        self.scale = max(5 / AU, min(5000 / AU, self.scale))
        # Keep pivot fixed on screen
        new_sx = int(self.cx + wx * self.scale)
        new_sy = int(self.cy - wy * self.scale)
        self.cx += pivot_sx - new_sx
        self.cy += pivot_sy - new_sy

    def start_drag(self, sx: int, sy: int):
        self.dragging = True
        self._drag_start = (sx, sy)
        self._cam_start = (self.cx, self.cy)

    def update_drag(self, sx: int, sy: int):
        if self.dragging:
            self.cx = self._cam_start[0] + (sx - self._drag_start[0])
            self.cy = self._cam_start[1] + (sy - self._drag_start[1])

    def stop_drag(self):
        self.dragging = False

    @property
    def au_per_pixel(self) -> float:
        return 1.0 / (self.scale * AU)

    def visible_au(self, viewport_w: int) -> float:
        return viewport_w * self.au_per_pixel


class SolarSystemRenderer:
    def __init__(self, screen: pygame.Surface, viewport_rect: pygame.Rect):
        self.screen = screen
        self.viewport = viewport_rect
        self.camera = Camera(viewport_rect.centerx, viewport_rect.centery)
        self.camera.cx = viewport_rect.x + viewport_rect.width // 2
        self.camera.cy = viewport_rect.y + viewport_rect.height // 2
        self._star_surf: Optional[pygame.Surface] = None
        self._stars: list[Tuple[int, int, int]] = []  # (x, y, brightness)
        self._generate_stars(350)

    def _generate_stars(self, count: int):
        import random
        rng = random.Random(42)
        for _ in range(count):
            x = rng.randint(0, self.viewport.width)
            y = rng.randint(0, self.viewport.height)
            b = rng.randint(30, 160)
            self._stars.append((x, y, b))

    def _draw_stars(self):
        for (x, y, b) in self._stars:
            c = (b, b, b + 20)
            self.screen.set_at((self.viewport.x + x, self.viewport.y + y), c)

    def _w2s(self, x: float, y: float) -> Tuple[int, int]:
        return self.camera.world_to_screen(x, y)

    def _in_viewport(self, sx: int, sy: int, margin: int = 20) -> bool:
        r = self.viewport
        return (r.x - margin <= sx <= r.right + margin and
                r.y - margin <= sy <= r.bottom + margin)

    def draw_orbit(self, body: CelestialBody, t: float, highlighted: bool = False):
        if body.semi_major_axis == 0 or body.parent is None:
            return
        a = body.semi_major_axis
        e = body.eccentricity
        omega = body.arg_periapsis
        b = a * math.sqrt(1 - e**2)

        pts = []
        for i in range(ORBIT_POINTS + 1):
            nu = i * TWO_PI / ORBIT_POINTS
            r = a * (1 - e**2) / (1 + e * math.cos(nu))
            theta = nu + omega
            wx, wy = r * math.cos(theta), r * math.sin(theta)
            sx, sy = self._w2s(wx, wy)
            pts.append((sx, sy))

        color = theme.ORBIT_HI if highlighted else theme.ORBIT_LINE
        if len(pts) > 1:
            pygame.draw.lines(self.screen, color, False, pts, 1)

    def draw_body(self, body: CelestialBody, t: float,
                  selected: bool = False, label: bool = True):
        if body.parent is None:
            # Sun
            wx, wy = 0.0, 0.0
        else:
            wx, wy = body.position_at(t)

        sx, sy = self._w2s(wx, wy)
        if not self._in_viewport(sx, sy, 60):
            return

        r = body.display_radius
        color = body.color

        if body.parent is None:
            # Sun glow
            for glow_r in range(r + 8, r, -2):
                alpha = max(0, 80 - (glow_r - r) * 12)
                glow_c = (min(255, color[0]), min(200, color[1]), 30)
                pygame.draw.circle(self.screen, glow_c, (sx, sy), glow_r)

        pygame.draw.circle(self.screen, color, (sx, sy), r)

        if selected:
            pygame.draw.circle(self.screen, theme.ACCENT, (sx, sy), r + 3, 1)
            pygame.draw.circle(self.screen, theme.ACCENT_DIM, (sx, sy), r + 6, 1)

        if label:
            font = theme.get_font(theme.FONT_SIZE_SM)
            txt = font.render(body.name, True, theme.TEXT_DIM)
            self.screen.blit(txt, (sx + r + 3, sy - 5))

    def draw_spacecraft(self, sc: Spacecraft, selected: bool = False):
        if sc.status in ("Assembled", "Planning"):
            return
        wx, wy = sc.position
        sx, sy = self._w2s(wx, wy)
        if not self._in_viewport(sx, sy, 20):
            return

        color = theme.TRAJ_ACTIVE[:3]
        pygame.draw.circle(self.screen, color, (sx, sy), 3)
        if selected:
            pygame.draw.circle(self.screen, theme.ACCENT, (sx, sy), 5, 1)

        font = theme.get_font(theme.FONT_SIZE_SM)
        txt = font.render(sc.name[:12], True, theme.TEXT_DIM)
        self.screen.blit(txt, (sx + 5, sy - 4))

    def draw_trajectory(self, sc: Spacecraft):
        if len(sc.trajectory_points) < 2:
            return
        pts = [self._w2s(x, y) for x, y in sc.trajectory_points]
        pts = [(sx, sy) for sx, sy in pts if self._in_viewport(sx, sy, 100)]
        if len(pts) < 2:
            return
        pygame.draw.lines(self.screen, theme.TRAJ_ACTIVE[:3], False, pts, 1)

    def draw_planned_trajectory(self, window: TransferWindow,
                                 origin: CelestialBody, dest: CelestialBody,
                                 t_now: float, sun_mu: float):
        """Draw planned transfer arc from origin to destination."""
        from sim.physics import orbit_from_state
        r1 = origin.semi_major_axis
        r2 = dest.semi_major_axis
        if r1 == 0 or r2 == 0:
            return
        import math
        a = (r1 + r2) / 2
        e_t = (r2 - r1) / (r2 + r1)
        dep_pos = origin.position_at(window.departure_time)
        dep_angle = math.atan2(dep_pos[1], dep_pos[0])

        pts = []
        for i in range(60):
            frac = i / 59.0
            nu = frac * math.pi
            r = a * (1 - e_t**2) / (1 + e_t * math.cos(nu))
            theta = dep_angle + nu
            wx = r * math.cos(theta)
            wy = r * math.sin(theta)
            sx, sy = self._w2s(wx, wy)
            pts.append((sx, sy))

        if len(pts) >= 2:
            pygame.draw.lines(self.screen, theme.TRAJ_PLANNED[:3], False, pts, 1)
            # Arrow at midpoint
            mid = pts[len(pts)//2]
            mid2 = pts[len(pts)//2 + 1]
            dx = mid2[0] - mid[0]
            dy = mid2[1] - mid[1]
            d = math.sqrt(dx**2 + dy**2)
            if d > 0:
                nx, ny = dx/d, dy/d
                p1 = (int(mid[0] + ny*5 - nx*6), int(mid[1] - nx*5 - ny*6))
                p2 = (int(mid[0] - ny*5 - nx*6), int(mid[1] + nx*5 - ny*6))
                pygame.draw.line(self.screen, theme.TRAJ_PLANNED[:3], mid, p1, 1)
                pygame.draw.line(self.screen, theme.TRAJ_PLANNED[:3], mid, p2, 1)

    def draw_phase_angle(self, origin: CelestialBody, dest: CelestialBody, t: float):
        """Draw a line showing current phase angle between two bodies."""
        op = origin.position_at(t)
        dp = dest.position_at(t)
        osx, osy = self._w2s(*op)
        dsx, dsy = self._w2s(*dp)
        pygame.draw.line(self.screen, theme.TEXT_WARN, (osx, osy), (dsx, dsy), 1)

    def begin_frame(self):
        pygame.draw.rect(self.screen, theme.BG, self.viewport)
        self._draw_stars()

    def draw_scale_bar(self):
        # Draw scale bar bottom-left of viewport
        au_per_px = self.camera.au_per_pixel
        target_au = 1.0
        bar_px = int(target_au / au_per_px)
        if bar_px > 200:
            target_au = 0.5
            bar_px = int(target_au / au_per_px)
        if bar_px < 20:
            target_au = 5.0
            bar_px = int(target_au / au_per_px)

        bx = self.viewport.x + 16
        by = self.viewport.bottom - 24
        pygame.draw.line(self.screen, theme.TEXT_DIM, (bx, by), (bx + bar_px, by), 1)
        pygame.draw.line(self.screen, theme.TEXT_DIM, (bx, by - 4), (bx, by + 4), 1)
        pygame.draw.line(self.screen, theme.TEXT_DIM, (bx+bar_px, by - 4), (bx+bar_px, by + 4), 1)
        font = theme.get_font(theme.FONT_SIZE_SM)
        lbl = f"{target_au:.1f} AU"
        txt = font.render(lbl, True, theme.TEXT_DIM)
        self.screen.blit(txt, (bx + bar_px//2 - txt.get_width()//2, by - 14))

    def draw_crosshair(self, sx: int, sy: int):
        size = 6
        pygame.draw.line(self.screen, theme.ACCENT, (sx - size, sy), (sx + size, sy), 1)
        pygame.draw.line(self.screen, theme.ACCENT, (sx, sy - size), (sx, sy + size), 1)

    def body_at_screen(self, sx: int, sy: int, bodies: dict,
                        t: float, threshold: int = 12) -> Optional[str]:
        """Return name of body closest to screen pos within threshold."""
        best_name = None
        best_d = threshold
        for name, body in bodies.items():
            if body.parent is None:
                wx, wy = 0.0, 0.0
            else:
                wx, wy = body.position_at(t)
            bsx, bsy = self._w2s(wx, wy)
            d = math.sqrt((bsx - sx)**2 + (bsy - sy)**2)
            if d < best_d:
                best_d = d
                best_name = name
        return best_name
