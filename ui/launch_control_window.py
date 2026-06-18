"""
Launch Control Window — separate OS window, two modes:

  PLANNING mode : pick launch site, date, see hourly weather forecast
  COUNTDOWN mode: full control centre countdown with holds and event pauses

Integrates with sim/launch_sites, sim/weather, sim/countdown.
"""

from __future__ import annotations
import math
import pygame
from typing import Optional, Callable
from enum import Enum

from sim.launch_sites import LAUNCH_SITES, LaunchSite
from sim.weather import simulator as wx, WeatherConditions, LaunchRuleCheck
from sim.countdown import CountdownController, CountdownPhase, _fmt_t
from sim.transfer import seconds_to_date
from . import theme

# ── Window geometry ───────────────────────────────────────────────────────────
WIN_W, WIN_H = 1100, 720
WARP_LEVELS  = [1, 10, 100, 1_000, 10_000, 100_000]
DAY = 86400.0


class LCMode(Enum):
    PLANNING  = "PLANNING"
    COUNTDOWN = "COUNTDOWN"


# ── colour helpers ────────────────────────────────────────────────────────────
def _go_col(go: bool) -> tuple:
    return theme.TEXT_GREEN if go else theme.TEXT_ALERT

def _phase_col(phase: CountdownPhase) -> tuple:
    if phase in (CountdownPhase.LIFTOFF, CountdownPhase.MAXQ,
                 CountdownPhase.MECO, CountdownPhase.STAGING,
                 CountdownPhase.ORBIT):
        return theme.TEXT_WARN
    if phase == CountdownPhase.SCRUBBED:
        return theme.TEXT_ALERT
    if phase == CountdownPhase.HOLD:
        return (255, 120, 30)
    return theme.TEXT_GREEN


# ── Planning helpers ──────────────────────────────────────────────────────────

def _wx_icon(cond: WeatherConditions) -> str:
    if cond.lightning:   return "⚡"
    if cond.precipitation == "Heavy":   return "⛈"
    if cond.precipitation == "Moderate": return "🌧"
    if cond.precipitation == "Light":   return "🌦"
    if cond.cloud_cover > 0.75:  return "☁"
    if cond.cloud_cover > 0.4:   return "⛅"
    return "☀"


def _go_symbol(go: bool) -> str:
    return "GO " if go else "NO "


# ── Main window ───────────────────────────────────────────────────────────────

class LaunchControlWindow:
    def __init__(self,
                 on_liftoff: Callable,          # (site, sim_time) -> None
                 on_scrub:   Callable):
        self.on_liftoff = on_liftoff
        self.on_scrub   = on_scrub

        self._open = False
        self._window: Optional[pygame.Window] = None
        self._surf:   Optional[pygame.Surface] = None

        self.mode = LCMode.PLANNING

        # Planning state
        self.sim_time: float = 0.0           # current master sim time
        self.spacecraft_name: str = "Spacecraft"
        self.target_name: str = "Mars"
        self.departure_window_time: float = 0.0  # selected transfer window t

        self.sites = LAUNCH_SITES
        self.sel_site_idx = 0                # selected site index
        self.plan_date_offset = 0            # days offset from sim_time
        self.forecast: list[WeatherConditions] = []
        self.sel_hour = 9                    # selected launch hour

        # Countdown state
        self.ctrl: Optional[CountdownController] = None
        self.warp_idx = 3                    # default ×1000
        self._fired_liftoff = False

        # Layout cached rects
        self._plan_site_rect  = pygame.Rect(0, 0, 0, 0)
        self._plan_fcst_rect  = pygame.Rect(0, 0, 0, 0)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self, sim_time: float, spacecraft_name: str, target_name: str,
             departure_window_time: float):
        if self._open:
            if self._window: self._window.focus()
            return
        self.sim_time = sim_time
        self.spacecraft_name = spacecraft_name
        self.target_name = target_name
        self.departure_window_time = departure_window_time
        self.mode = LCMode.PLANNING
        self._refresh_forecast()
        self._fired_liftoff = False

        self._window = pygame.Window(
            "AbsoluteSpace — Launch Control",
            size=(WIN_W, WIN_H), resizable=False)
        self._surf = self._window.get_surface()
        self._open = True

    def close(self):
        if self._window:
            self._window.destroy()
            self._window = None
            self._surf = None
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    # ── Per-frame update ──────────────────────────────────────────────────────

    def step(self, dt_real: float, master_sim_time: float):
        """Called every frame. dt_real = wall-clock seconds."""
        if not self._open:
            return
        self.sim_time = master_sim_time

        if self.mode == LCMode.COUNTDOWN and self.ctrl:
            dt_sim = dt_real * WARP_LEVELS[self.warp_idx]
            site = self.sites[self.sel_site_idx]

            events = self.ctrl.step(dt_sim)

            # Liftoff callback
            if (self.ctrl.phase == CountdownPhase.LIFTOFF
                    and self.ctrl.t >= 0 and not self._fired_liftoff):
                self._fired_liftoff = True
                self.on_liftoff(site, self._launch_sim_time())

    # ── Event handling ────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.Event) -> bool:
        if not self._open or self._window is None:
            return False
        ev_win = getattr(event, "window", None)
        if ev_win is not None and ev_win != self._window:
            return False

        if event.type == pygame.WINDOWCLOSE:
            self.close(); return True
        if event.type == pygame.KEYDOWN:
            return self._handle_key(event.key)
        if event.type == pygame.MOUSEBUTTONDOWN:
            return self._handle_click(event.pos, event.button)
        if event.type == pygame.MOUSEWHEEL:
            return self._handle_scroll(event.y)
        return False

    def _handle_key(self, key: int) -> bool:
        if self.mode == LCMode.PLANNING:
            if key == pygame.K_UP:
                self.sel_site_idx = max(0, self.sel_site_idx - 1)
                self._refresh_forecast()
            elif key == pygame.K_DOWN:
                self.sel_site_idx = min(len(self.sites)-1, self.sel_site_idx+1)
                self._refresh_forecast()
            elif key == pygame.K_LEFT:
                self.sel_hour = max(0, self.sel_hour - 1)
            elif key == pygame.K_RIGHT:
                self.sel_hour = min(23, self.sel_hour + 1)
            elif key == pygame.K_PAGEUP:
                self.plan_date_offset = max(0, self.plan_date_offset - 1)
                self._refresh_forecast()
            elif key == pygame.K_PAGEDOWN:
                self.plan_date_offset = min(30, self.plan_date_offset + 1)
                self._refresh_forecast()
            elif key == pygame.K_RETURN:
                self._begin_countdown()
            elif key == pygame.K_ESCAPE:
                self.close()
        else:  # COUNTDOWN
            if key == pygame.K_SPACE:
                if self.ctrl:
                    if self.ctrl.is_held: self.ctrl.resume()
                    else: self.ctrl.hold("MANUAL HOLD")
            elif key == pygame.K_h:
                if self.ctrl: self.ctrl.hold("MANUAL HOLD")
            elif key == pygame.K_r:
                if self.ctrl: self.ctrl.resume()
            elif key == pygame.K_s:
                if self.ctrl:
                    self.ctrl.scrub()
                    self.on_scrub()
            elif key == pygame.K_t:
                self.warp_idx = min(len(WARP_LEVELS)-1, self.warp_idx+1)
            elif key == pygame.K_y:
                self.warp_idx = max(0, self.warp_idx-1)
            elif key == pygame.K_ESCAPE:
                self.close()
        return True

    def _handle_click(self, pos: tuple[int, int], button: int) -> bool:
        x, y = pos
        if self.mode == LCMode.PLANNING:
            self._planning_click(x, y)
        else:
            self._countdown_click(x, y)
        return True

    def _handle_scroll(self, dy: int) -> bool:
        if self.mode == LCMode.PLANNING:
            self.sel_site_idx = max(0, min(len(self.sites)-1, self.sel_site_idx - dy))
            self._refresh_forecast()
        return True

    def _planning_click(self, x: int, y: int):
        # Site list
        r = self._plan_site_rect
        if r.collidepoint(x, y):
            row = (y - r.y - 30) // 20
            idx = row + 0
            if 0 <= idx < len(self.sites):
                self.sel_site_idx = idx
                self._refresh_forecast()
            return

        # Forecast table — click hour row
        r = self._plan_fcst_rect
        if r.collidepoint(x, y):
            row = (y - r.y - 50) // 18
            if 0 <= row < 24:
                self.sel_hour = row
            return

        # Buttons at bottom
        bh = WIN_H - 44
        if y >= bh:
            btn_y = bh + 8
            btn_h = 28
            # PROCEED button
            if WIN_W - 180 <= x <= WIN_W - 20 and btn_y <= y <= btn_y + btn_h:
                self._begin_countdown()
            # Date nav
            elif 220 <= x <= 310 and btn_y <= y <= btn_y + btn_h:
                self.plan_date_offset = max(0, self.plan_date_offset - 1)
                self._refresh_forecast()
            elif 315 <= x <= 405 and btn_y <= y <= btn_y + btn_h:
                self.plan_date_offset = min(30, self.plan_date_offset + 1)
                self._refresh_forecast()

    def _countdown_click(self, x: int, y: int):
        bh = WIN_H - 44
        if y < bh:
            return
        btn_y = bh + 8
        btn_h = 28
        # RESUME
        if 10 <= x <= 120 and btn_y <= y <= btn_y+btn_h:
            if self.ctrl: self.ctrl.resume()
        # HOLD
        elif 130 <= x <= 240 and btn_y <= y <= btn_y+btn_h:
            if self.ctrl: self.ctrl.hold("MANUAL HOLD")
        # SCRUB
        elif 250 <= x <= 360 and btn_y <= y <= btn_y+btn_h:
            if self.ctrl: self.ctrl.scrub(); self.on_scrub()
        # WARP -
        elif WIN_W - 280 <= x <= WIN_W - 200 and btn_y <= y <= btn_y+btn_h:
            self.warp_idx = max(0, self.warp_idx-1)
        # WARP +
        elif WIN_W - 190 <= x <= WIN_W - 110 and btn_y <= y <= btn_y+btn_h:
            self.warp_idx = min(len(WARP_LEVELS)-1, self.warp_idx+1)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _launch_sim_time(self) -> float:
        return self.sim_time + self.plan_date_offset * DAY

    def _refresh_forecast(self):
        site = self.sites[self.sel_site_idx]
        self.forecast = wx.daily_forecast(site, self._launch_sim_time())

    def _begin_countdown(self):
        self.mode = LCMode.COUNTDOWN
        self.ctrl = CountdownController(mission_name=self.spacecraft_name)
        self.ctrl.log.append(
            f"[T-01:00:00] LAUNCH DIRECTOR: {self.spacecraft_name} launch attempt "
            f"from {self.sites[self.sel_site_idx].short}. Target: {self.target_name}.")
        self.ctrl.hold("AWAITING LAUNCH DIRECTOR GO")

    def _selected_forecast(self) -> Optional[WeatherConditions]:
        if self.forecast and 0 <= self.sel_hour < len(self.forecast):
            return self.forecast[self.sel_hour]
        return None

    # ── Drawing ───────────────────────────────────────────────────────────────

    def draw(self):
        if not self._open or self._surf is None or self._window is None:
            return
        self._surf.fill(theme.BG)
        if self.mode == LCMode.PLANNING:
            self._draw_planning(self._surf)
        else:
            self._draw_countdown(self._surf)
        self._window.flip()

    # ── PLANNING VIEW ─────────────────────────────────────────────────────────

    def _draw_planning(self, surf: pygame.Surface):
        # Header
        _header(surf, f"LAUNCH PLANNING  —  {self.spacecraft_name}  →  {self.target_name}",
                seconds_to_date(self.sim_time))

        site_rect   = pygame.Rect(0,  44, 240, WIN_H - 88)
        detail_rect = pygame.Rect(240, 44, 280, WIN_H - 88)
        fcst_rect   = pygame.Rect(520, 44, WIN_W-520, WIN_H - 88)

        self._plan_site_rect  = site_rect
        self._plan_fcst_rect  = fcst_rect

        self._draw_plan_sites(surf, site_rect)
        self._draw_plan_detail(surf, detail_rect)
        self._draw_plan_forecast(surf, fcst_rect)
        self._draw_plan_bottom(surf)

    def _draw_plan_sites(self, surf: pygame.Surface, rect: pygame.Rect):
        pygame.draw.rect(surf, theme.BG_PANEL, rect)
        pygame.draw.rect(surf, theme.BORDER, rect, 1)
        x, y = rect.x + 6, rect.y + 6
        theme.draw_text(surf, "LAUNCH SITES", x, y, color=theme.ACCENT, bold=True)
        theme.draw_hline(surf, x, y+14, rect.width-12)
        y += 20

        for i, site in enumerate(self.sites):
            is_sel = i == self.sel_site_idx
            ry = y + i * 20
            if ry > rect.bottom - 20:
                break
            if is_sel:
                pygame.draw.rect(surf, theme.SELECTED,
                                 (rect.x+2, ry-1, rect.width-4, 19))
            col = theme.TEXT_BRIGHT if is_sel else theme.TEXT
            theme.draw_text(surf, f"{'>' if is_sel else ' '} {site.short}", x, ry, color=col, size=11)
            theme.draw_text(surf, site.country[:3], rect.right-30, ry, color=theme.TEXT_DIM, size=10)

    def _draw_plan_detail(self, surf: pygame.Surface, rect: pygame.Rect):
        pygame.draw.rect(surf, theme.BG_PANEL, rect)
        pygame.draw.rect(surf, theme.BORDER, rect, 1)
        x, y = rect.x + 8, rect.y + 6
        w = rect.width - 16
        site = self.sites[self.sel_site_idx]

        theme.draw_text(surf, "SITE DETAILS", x, y, color=theme.ACCENT, bold=True)
        y += 16
        theme.draw_hline(surf, x, y, w); y += 6

        def row(lbl, val, col=None):
            nonlocal y
            theme.draw_text(surf, lbl, x, y, color=theme.TEXT_DIM, size=11)
            theme.draw_text(surf, val, x+100, y, color=col or theme.TEXT_BRIGHT, size=11)
            y += 14

        row("Site:",       site.name[:22])
        y += 2
        row("Agency:",     site.agency[:22])
        row("Country:",    site.country)
        row("Latitude:",   site.lat_str)
        row("Longitude:",  site.lon_str)
        row("Altitude:",   f"{site.altitude:.0f} m ASL")
        row("Climate:",    site.climate.title())
        y += 4
        theme.draw_hline(surf, x, y, w); y += 6
        row("Rot. Speed:", f"{site.surface_speed():.0f} m/s",
            col=theme.TEXT_GREEN)
        row("Wind limit:", f"{site.max_wind_surface:.0f} m/s")
        y += 4
        theme.draw_hline(surf, x, y, w); y += 6

        theme.draw_text(surf, "PADS:", x, y, color=theme.TEXT_DIM, size=11); y += 13
        for pad in site.pads[:4]:
            theme.draw_text(surf, f"  {pad}", x, y, color=theme.TEXT, size=11); y += 13

        y += 6
        theme.draw_hline(surf, x, y, w); y += 6

        # Selected window info
        cond = self._selected_forecast()
        if cond:
            go, reasons = wx.is_go(site, cond)
            col = theme.TEXT_GREEN if go else theme.TEXT_ALERT
            theme.draw_text(surf, f"H+{self.sel_hour:02d}:00 STATUS:", x, y,
                            color=theme.TEXT_DIM, size=11); y += 14
            theme.draw_text(surf, "GO FOR LAUNCH" if go else "NO-GO",
                            x, y, color=col, bold=True, size=13); y += 16
            if not go:
                for r in reasons[:3]:
                    theme.draw_text(surf, f"  {r[:28]}", x, y,
                                    color=theme.TEXT_ALERT, size=10); y += 12

    def _draw_plan_forecast(self, surf: pygame.Surface, rect: pygame.Rect):
        pygame.draw.rect(surf, theme.BG_PANEL, rect)
        pygame.draw.rect(surf, theme.BORDER, rect, 1)
        x0, y0 = rect.x + 6, rect.y + 6
        w = rect.width - 12

        site = self.sites[self.sel_site_idx]
        launch_t = self._launch_sim_time()
        date_str = seconds_to_date(launch_t)

        theme.draw_text(surf, f"24-HR WEATHER FORECAST — {date_str}", x0, y0,
                        color=theme.ACCENT, bold=True)
        theme.draw_text(surf, "PgUp/PgDn change date   ←/→ select hour   Enter = begin countdown",
                        x0, y0+14, color=theme.TEXT_DIM, size=9)
        theme.draw_hline(surf, x0, y0+26, w)
        y = y0 + 30

        # Column headers
        cols = [(0,"HR"),(30,"SKY"),(100,"WIND"),(170,"VIS"),(220,"LTNG"),(265,"PRECIP"),(315,"STATUS")]
        for cx, lbl in cols:
            theme.draw_text(surf, lbl, x0+cx, y, color=theme.TEXT_DIM, size=10)
        y += 16
        theme.draw_hline(surf, x0, y, w); y += 2

        for h, cond in enumerate(self.forecast):
            is_sel = h == self.sel_hour
            go, _ = wx.is_go(site, cond)
            ry = y + h * 18

            if ry + 18 > rect.bottom - 6:
                break

            if is_sel:
                pygame.draw.rect(surf, theme.SELECTED,
                                 (rect.x+2, ry-1, rect.width-4, 17))

            col = theme.TEXT_BRIGHT if is_sel else (theme.TEXT if go else theme.TEXT_ALERT)

            sky = cond.sky_text[:10]
            wind = f"{cond.wind_kt:.0f}kt {cond.wind_cardinal}"
            vis  = f"{cond.visibility_km:.0f}km"
            ltng = "YES" if cond.lightning else "No"
            ltng_col = theme.TEXT_ALERT if cond.lightning else theme.TEXT_DIM
            prcp = cond.precipitation[:4]
            stat = _go_symbol(go)
            stat_col = theme.TEXT_GREEN if go else theme.TEXT_ALERT

            theme.draw_text(surf, f"{h:02d}:00", x0+0,  ry, color=col, size=11)
            theme.draw_text(surf, sky,            x0+30, ry, color=col, size=11)
            theme.draw_text(surf, wind,           x0+100,ry, color=col, size=11)
            theme.draw_text(surf, vis,            x0+170,ry, color=theme.TEXT_DIM, size=10)
            theme.draw_text(surf, ltng,           x0+220,ry, color=ltng_col, size=10)
            theme.draw_text(surf, prcp,           x0+265,ry, color=col, size=11)
            theme.draw_text(surf, stat,           x0+315,ry, color=stat_col, size=11,
                            bold=is_sel)

        # Selected hour detail
        cond = self._selected_forecast()
        if cond:
            dy = rect.bottom - 70
            theme.draw_hline(surf, x0, dy, w); dy += 4
            theme.draw_text(surf,
                            f"H+{self.sel_hour:02d}:00  "
                            f"Temp: {cond.temp_c:.0f}°C  "
                            f"Wind: {cond.wind_kt:.0f}kt {cond.wind_cardinal}  "
                            f"Upper: {cond.wind_upper:.0f} m/s  "
                            f"Sky: {cond.sky_text}  "
                            f"Hum: {cond.humidity*100:.0f}%",
                            x0, dy, color=theme.TEXT, size=11)

    def _draw_plan_bottom(self, surf: pygame.Surface):
        bh = WIN_H - 44
        pygame.draw.rect(surf, theme.BG_HEADER, (0, bh, WIN_W, 44))
        pygame.draw.line(surf, theme.BORDER, (0, bh), (WIN_W, bh))
        btn_y = bh + 8
        btn_h = 28

        site = self.sites[self.sel_site_idx]
        d_str = seconds_to_date(self._launch_sim_time())
        theme.draw_text(surf, f"SITE: {site.short}   DATE: {d_str}   HOUR: {self.sel_hour:02d}:00 UTC",
                        10, btn_y+5, color=theme.TEXT, size=12)

        # Prev/Next date buttons
        for lbl, bx in [("◄ PREV DAY", 220), ("NEXT DAY ►", 315)]:
            pygame.draw.rect(surf, theme.BG_PANEL, (bx, btn_y, 90, btn_h))
            pygame.draw.rect(surf, theme.BORDER, (bx, btn_y, 90, btn_h), 1)
            theme.draw_text(surf, lbl, bx+5, btn_y+7, color=theme.TEXT_DIM, size=11)

        # PROCEED button
        cond = self._selected_forecast()
        go = wx.is_go(site, cond)[0] if cond else False
        bcol = theme.TEXT_GREEN if go else theme.TEXT_WARN
        bx = WIN_W - 180
        pygame.draw.rect(surf, theme.BG_PANEL, (bx, btn_y, 160, btn_h))
        pygame.draw.rect(surf, bcol, (bx, btn_y, 160, btn_h), 1)
        lbl = "BEGIN COUNTDOWN ►" if go else "PROCEED ANYWAY ►"
        theme.draw_text(surf, lbl, bx+8, btn_y+7, color=bcol, size=11, bold=True)

    # ── COUNTDOWN VIEW ────────────────────────────────────────────────────────

    def _draw_countdown(self, surf: pygame.Surface):
        if not self.ctrl:
            return

        ctrl = self.ctrl
        site = self.sites[self.sel_site_idx]
        launch_t = self._launch_sim_time()
        cond = wx.conditions_at(site, launch_t + ctrl.t)
        rules = wx.launch_rules(site, cond)

        # ── Header ──
        _header(surf,
                f"LAUNCH CONTROL  —  {self.spacecraft_name}  →  {self.target_name}  "
                f"[{site.short}]",
                seconds_to_date(self.sim_time))

        # Layout: 3 columns
        TIMER_W = 240
        WX_W    = 280
        SYS_W   = WIN_W - TIMER_W - WX_W

        timer_rect = pygame.Rect(0,   44, TIMER_W,       WIN_H - 88)
        wx_rect    = pygame.Rect(TIMER_W, 44, WX_W,      WIN_H - 88)
        sys_rect   = pygame.Rect(TIMER_W+WX_W, 44, SYS_W, WIN_H//2 - 44)
        log_rect   = pygame.Rect(TIMER_W+WX_W, 44+WIN_H//2-44, SYS_W, WIN_H//2 - 44)

        for r in (timer_rect, wx_rect, sys_rect, log_rect):
            pygame.draw.rect(surf, theme.BG_PANEL, r)
            pygame.draw.rect(surf, theme.BORDER, r, 1)

        self._draw_cd_timer(surf, timer_rect, ctrl)
        self._draw_cd_weather(surf, wx_rect, site, cond, rules)
        self._draw_cd_systems(surf, sys_rect, ctrl, rules)
        self._draw_cd_log(surf, log_rect, ctrl)
        self._draw_cd_bottom(surf, ctrl)

    def _draw_cd_timer(self, surf: pygame.Surface, rect: pygame.Rect,
                       ctrl: CountdownController):
        x, y = rect.x + 10, rect.y + 10
        w = rect.width - 20

        theme.draw_text(surf, "COUNTDOWN", x, y, color=theme.ACCENT, bold=True, size=12)
        y += 20

        # Big T-minus display
        t_col = theme.TEXT_ALERT if ctrl.is_held else (
            theme.TEXT_WARN if ctrl.post_liftoff else theme.TEXT_GREEN)
        t_str = ctrl.t_display
        big_font = theme.get_font(28, bold=True)
        t_surf = big_font.render(t_str, True, t_col)
        surf.blit(t_surf, (rect.centerx - t_surf.get_width()//2, y))
        y += t_surf.get_height() + 6

        # HOLD banner
        if ctrl.is_held:
            hold_col = theme.TEXT_ALERT if ctrl.is_scrubbed else (255, 120, 30)
            label = "SCRUBBED" if ctrl.is_scrubbed else "   HOLD  "
            h_font = theme.get_font(18, bold=True)
            h_surf = h_font.render(label, True, hold_col)
            surf.blit(h_surf, (rect.centerx - h_surf.get_width()//2, y))
            y += h_surf.get_height() + 4

            reason = ctrl.hold_reason[:28]
            theme.draw_text(surf, reason, x, y, color=hold_col, size=10)
            y += 14

        elif ctrl.phase == CountdownPhase.LIFTOFF:
            lf_surf = theme.get_font(16, bold=True).render("LIFTOFF", True, theme.TEXT_WARN)
            surf.blit(lf_surf, (rect.centerx - lf_surf.get_width()//2, y))
            y += lf_surf.get_height() + 4
        else:
            y += 4

        theme.draw_hline(surf, x, y, w); y += 6

        # Phase
        phase_col = _phase_col(ctrl.phase)
        theme.draw_text(surf, "PHASE:", x, y, color=theme.TEXT_DIM, size=11); y += 14
        theme.draw_text(surf, ctrl.phase.value, x, y, color=phase_col,
                        bold=True, size=12); y += 18

        theme.draw_hline(surf, x, y, w); y += 6

        # Propellant loading bars
        theme.draw_text(surf, "PROPELLANT", x, y, color=theme.TEXT_DIM, size=11); y += 14
        for label, level in [("LOX  ", ctrl.lox_level), ("RP-1 ", ctrl.fuel_level)]:
            theme.draw_text(surf, label, x, y, color=theme.TEXT_DIM, size=11)
            bar_x = x + 40
            bar_w = w - 40
            theme.draw_bar(surf, bar_x, y+2, bar_w, 10, level, 1.0,
                           color=theme.TEXT_GREEN if level >= 1.0 else theme.TEXT_WARN)
            pct = f"{level*100:.0f}%"
            theme.draw_text(surf, pct, bar_x + bar_w - 28, y, color=theme.TEXT_DIM, size=10)
            y += 16

        y += 4
        theme.draw_hline(surf, x, y, w); y += 6

        # Warp display
        warp = WARP_LEVELS[self.warp_idx]
        warp_str = f"×{warp:,}"
        theme.draw_text(surf, f"TIME WARP  {warp_str}", x, y,
                        color=theme.TEXT_DIM, size=11); y += 14

    def _draw_cd_weather(self, surf: pygame.Surface, rect: pygame.Rect,
                         site: LaunchSite, cond: WeatherConditions,
                         rules: list[LaunchRuleCheck]):
        x, y = rect.x + 8, rect.y + 8
        w = rect.width - 16

        theme.draw_text(surf, "WEATHER  —  LIVE", x, y, color=theme.ACCENT, bold=True)
        theme.draw_text(surf, site.name[:30], x, y+14, color=theme.TEXT_DIM, size=10)
        y += 30
        theme.draw_hline(surf, x, y, w); y += 6

        def wx_row(label, val, unit="", col=None):
            nonlocal y
            theme.draw_text(surf, label, x, y, color=theme.TEXT_DIM, size=11)
            vc = col or theme.TEXT_BRIGHT
            theme.draw_text(surf, f"{val}{unit}", x+120, y, color=vc, size=11)
            y += 15

        wx_row("Temperature", f"{cond.temp_c:.1f}", "°C")
        wx_row("Wind (sfc)",  f"{cond.wind_kt:.0f}kt {cond.wind_cardinal}",
               col=theme.TEXT_ALERT if cond.wind_speed > site.max_wind_surface else theme.TEXT_GREEN)
        wx_row("Wind (upper)", f"{cond.wind_upper:.0f}", " m/s",
               col=theme.TEXT_ALERT if cond.wind_upper > site.max_wind_upper else theme.TEXT_GREEN)
        wx_row("Sky",         cond.sky_text)
        wx_row("Visibility",  f"{cond.visibility_km:.1f}", " km",
               col=theme.TEXT_ALERT if cond.visibility_km < site.min_visibility/1000 else theme.TEXT_GREEN)
        wx_row("Humidity",    f"{cond.humidity*100:.0f}", "%")
        wx_row("Precip",      cond.precipitation,
               col=theme.TEXT_ALERT if cond.precipitation in ("Moderate","Heavy") else theme.TEXT_GREEN)
        wx_row("Lightning",   "DETECTED" if cond.lightning else "NONE",
               col=theme.TEXT_ALERT if cond.lightning else theme.TEXT_GREEN)

        y += 4
        theme.draw_hline(surf, x, y, w); y += 6

        theme.draw_text(surf, "LAUNCH RULES", x, y, color=theme.TEXT_DIM, bold=True, size=11)
        y += 14

        all_go = all(r.go for r in rules)
        for rule in rules:
            col = theme.TEXT_GREEN if rule.go else theme.TEXT_ALERT
            mark = "GO " if rule.go else "NO "
            theme.draw_text(surf, f"{mark} {rule.name}", x, y, color=col, size=11)
            y += 13
            if not rule.go:
                theme.draw_text(surf, f"     {rule.value} / {rule.limit}",
                                x, y, color=theme.TEXT_DIM, size=10); y += 12

        y += 4
        theme.draw_hline(surf, x, y, w); y += 6
        all_col = theme.TEXT_GREEN if all_go else theme.TEXT_ALERT
        label = "ALL SYSTEMS GO" if all_go else "WEATHER NO-GO"
        theme.draw_text(surf, label, x, y, color=all_col, bold=True, size=13)

    def _draw_cd_systems(self, surf: pygame.Surface, rect: pygame.Rect,
                         ctrl: CountdownController, rules: list[LaunchRuleCheck]):
        x, y = rect.x + 8, rect.y + 8
        w = rect.width - 16

        theme.draw_text(surf, "SYSTEMS STATUS — GO/NO-GO POLL", x, y,
                        color=theme.ACCENT, bold=True)
        y += 18
        theme.draw_hline(surf, x, y, w); y += 6

        wx_go = all(r.go for r in rules)
        systems = [
            ("RANGE SAFETY",  True),
            ("VEHICLE",       ctrl.lox_level >= 0.99 and ctrl.fuel_level >= 0.99),
            ("PROPULSION",    ctrl.t <= -60),
            ("GUIDANCE",      True),
            ("FLIGHT CONTROL",True),
            ("WEATHER",       wx_go),
            ("DOWNRANGE",     True),
            ("NETWORK",       True),
        ]

        cols = w // 2
        for i, (name, go) in enumerate(systems):
            col_x = x + (i % 2) * cols
            row_y = y + (i // 2) * 16
            col = theme.TEXT_GREEN if go else theme.TEXT_ALERT
            theme.draw_text(surf, f"{'GO' if go else 'NO':3s}  {name}",
                            col_x, row_y, color=col, size=11)

        y += (len(systems) // 2 + 1) * 16 + 4
        theme.draw_hline(surf, x, y, w); y += 4

        overall_go = all(go for _, go in systems)
        oc = theme.TEXT_GREEN if overall_go else theme.TEXT_ALERT
        theme.draw_text(surf, "OVERALL: GO FOR LAUNCH" if overall_go else "OVERALL: NO-GO",
                        x, y, color=oc, bold=True, size=12)

    def _draw_cd_log(self, surf: pygame.Surface, rect: pygame.Rect,
                     ctrl: CountdownController):
        x, y = rect.x + 8, rect.y + 8
        w = rect.width - 16

        theme.draw_text(surf, "COMM LOG", x, y, color=theme.ACCENT, bold=True)
        y += 16
        theme.draw_hline(surf, x, y, w); y += 4

        lines_h = (rect.bottom - y - 4) // 13
        recent = ctrl.log[-lines_h:] if ctrl.log else []
        for line in recent:
            # Highlight milestones
            col = theme.TEXT_WARN if "LIFTOFF" in line or "HOLD" in line or "SCRUB" in line \
                  else theme.TEXT_DIM
            truncated = line[:w // 7 + 2]
            theme.draw_text(surf, truncated, x, y, color=col, size=10)
            y += 13

    def _draw_cd_bottom(self, surf: pygame.Surface, ctrl: CountdownController):
        bh = WIN_H - 44
        pygame.draw.rect(surf, theme.BG_HEADER, (0, bh, WIN_W, 44))
        pygame.draw.line(surf, theme.BORDER, (0, bh), (WIN_W, bh))
        btn_y = bh + 8
        btn_h = 28

        buttons = [
            ("RESUME",    10,  theme.TEXT_GREEN  if ctrl.is_held and not ctrl.is_scrubbed else theme.TEXT_DIM),
            ("HOLD",      130, theme.TEXT_WARN   if not ctrl.is_held else theme.TEXT_DIM),
            ("SCRUB",     250, theme.TEXT_ALERT),
        ]
        for lbl, bx, col in buttons:
            pygame.draw.rect(surf, theme.BG_PANEL, (bx, btn_y, 110, btn_h))
            pygame.draw.rect(surf, col, (bx, btn_y, 110, btn_h), 1)
            fw = theme.get_font(12).size(lbl)[0]
            theme.draw_text(surf, lbl, bx + (110-fw)//2, btn_y+7, color=col,
                            size=12, bold=True)

        # Warp controls
        warp_lbl = f"WARP  ×{WARP_LEVELS[self.warp_idx]:,}"
        theme.draw_text(surf, warp_lbl, WIN_W-380, btn_y+7, color=theme.TEXT, size=12)
        for lbl, bx2, tip in [("◄ SLOWER", WIN_W-280, "Y"), ("FASTER ►", WIN_W-170, "T")]:
            pygame.draw.rect(surf, theme.BG_PANEL, (bx2, btn_y, 100, btn_h))
            pygame.draw.rect(surf, theme.BORDER, (bx2, btn_y, 100, btn_h), 1)
            theme.draw_text(surf, lbl, bx2+8, btn_y+7, color=theme.TEXT_DIM, size=11)
            theme.draw_text(surf, f"[{tip}]", bx2+74, btn_y+18, color=theme.TEXT_DIM, size=9)

        # Keys hint
        theme.draw_text(surf, "Space=Hold/Resume  H=Hold  R=Resume  S=Scrub  T/Y=Warp",
                        370, btn_y+7, color=theme.TEXT_DIM, size=9)


# ── Shared header ─────────────────────────────────────────────────────────────

def _header(surf: pygame.Surface, title: str, date_str: str):
    pygame.draw.rect(surf, theme.BG_HEADER, (0, 0, WIN_W, 44))
    pygame.draw.line(surf, theme.BORDER, (0, 43), (WIN_W, 43))
    theme.draw_text(surf, title, 10, 6, color=theme.ACCENT, bold=True, size=13)
    theme.draw_text(surf, "ABSOLUTESPACE MISSION CONTROL", 10, 22,
                    color=theme.TEXT_DIM, size=10)
    theme.draw_text(surf, date_str, WIN_W-130, 14, color=theme.TEXT, size=12)
