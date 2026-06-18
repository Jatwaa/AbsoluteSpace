"""
AbsoluteSpace — MVP Space Simulator
Controls:
  Scroll         Zoom in/out
  Right-drag     Pan viewport
  Left-click     Select body as origin (Shift+click = destination)
  C              Open Craft Builder window
  W              Calculate transfer windows (origin→destination)
  Space          Pause / Resume
  T              Increase time warp
  Y              Decrease time warp
  G              Toggle orbit display
  H              Toggle phase angle line
  L              Quick-launch demo probe
  1-5            Quick origin→dest pairs
  F1             Help overlay
  Esc            Quit
"""

import sys
import math
import pygame

from sim.bodies import build_solar_system, AU, G
from sim.craft import Spacecraft, ModuleType, CATALOG_BY_NAME
from sim.mission import MissionControl, Mission
from sim.transfer import hohmann_windows, mission_delta_v_budget, seconds_to_date
from ui.renderer import SolarSystemRenderer
from ui.panels import MissionControlPanel, TransferWindowPanel, StatusBar
from ui.craft_builder_window import CraftBuilderWindow
from ui.launch_control_window import LaunchControlWindow
from ui.command_center import CommandCenterScreen
from ui import theme

# ── Constants ─────────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 1400, 900
TARGET_FPS   = 60
WARP_LEVELS  = [1, 10, 100, 1_000, 86_400, 864_000, 8_640_000]
J2000_START  = 8035 * 86400.0   # ~Jan 2022 (reasonable near-future start)
DAY          = 86400.0

# ── Layout ────────────────────────────────────────────────────────────────────
RIGHT_W      = 320
BOTTOM_H     = 60
STATUS_H     = 48

def make_rects(sw: int, sh: int):
    viewport  = pygame.Rect(0, 0, sw - RIGHT_W, sh - STATUS_H)
    mc_panel  = pygame.Rect(sw - RIGHT_W, 0, RIGHT_W, sh // 2 - STATUS_H // 2)
    tw_panel  = pygame.Rect(sw - RIGHT_W, mc_panel.bottom, RIGHT_W, sh - mc_panel.bottom - STATUS_H)
    status    = pygame.Rect(0, sh - STATUS_H, sw, STATUS_H)
    return viewport, mc_panel, tw_panel, status


def make_demo_spacecraft(name: str = "Probe-Alpha") -> Spacecraft:
    """Pre-assembled probe for quick-launch demo."""
    from sim.module_db import build_flat_catalog
    cat = build_flat_catalog()
    parts = [
        cat["Generic 100kg Probe"],
        cat["Dawn Triple-Junction"],
        cat["DSN-compatible Dish"],
        cat["Psyche Xenon Tank"],
        cat["Falcon 9 Stage Sep System"],
        cat["Falcon 9 S2 Tank"],
        cat["Merlin 1D Vac"],
        cat["Falcon 9 Stage Sep System"],
        cat["Falcon 9 S1 Tanks"],
        cat["Merlin 1D SL"],
        cat["Merlin 1D SL"],
        cat["Merlin 1D SL"],
    ]
    sc = Spacecraft(name=name, parts=parts)
    return sc


class App:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("AbsoluteSpace — Mission Simulator")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()

        self.sw, self.sh = SCREEN_W, SCREEN_H
        rects = make_rects(self.sw, self.sh)
        self.viewport_rect, mc_rect, tw_rect, status_rect = rects

        # Simulation state
        self.bodies = build_solar_system()
        self.sim_time = J2000_START
        self.warp_idx = 2        # default x100
        self.paused = False
        self.show_orbits = True
        self.show_phase_line = False
        self.mode = "OBSERVE"    # OBSERVE | PLAN | CRAFT | LAUNCH_CONTROL
        self.screen_mode = "HQ"  # HQ (command center home) | SOLAR (map view)

        self.selected_origin = "Earth"
        self.selected_dest = "Mars"
        self.selected_mission_name: str | None = None
        self.planned_windows: list = []

        # Mission control
        self.mc = MissionControl(self.bodies, self.sim_time)

        # UI components
        self.renderer = SolarSystemRenderer(self.screen, self.viewport_rect)
        self.mc_panel    = MissionControlPanel(mc_rect)
        self.tw_panel    = TransferWindowPanel(tw_rect)
        self.craft_win      = CraftBuilderWindow(on_launch=self._on_craft_ready)
        self.launch_ctrl_win = LaunchControlWindow(
            on_liftoff=self._on_liftoff,
            on_scrub=self._on_scrub,
        )
        self._pending_spacecraft: Spacecraft | None = None
        self.status_bar  = StatusBar(status_rect)

        # Command Center (home screen)
        self.command_center = CommandCenterScreen()

        # Help overlay state
        self.show_help = False

        # Demo: pre-calculate windows
        self._recalc_windows()

    def _recalc_windows(self):
        sun = self.bodies["Sun"]
        origin = self.bodies.get(self.selected_origin)
        dest   = self.bodies.get(self.selected_dest)
        if not origin or not dest or origin is dest:
            return
        self.planned_windows = hohmann_windows(origin, dest, sun,
                                               self.sim_time, n_windows=5)
        budget = mission_delta_v_budget(origin, dest, sun)
        self.tw_panel.set_windows(self.planned_windows, budget)
        self.tw_panel.origin_name = self.selected_origin
        self.tw_panel.dest_name   = self.selected_dest

    def _on_craft_ready(self, spacecraft: Spacecraft):
        """Step 1: Craft Builder closes → open Launch Control for site/date/weather."""
        win = self.tw_panel.selected_window
        if win is None:
            win = self.planned_windows[0] if self.planned_windows else None
        dep_t = win.departure_time if win else self.sim_time + 86400

        self._pending_spacecraft = spacecraft
        self.launch_ctrl_win.open(
            sim_time=self.sim_time,
            spacecraft_name=spacecraft.name,
            target_name=self.selected_dest,
            departure_window_time=dep_t,
        )
        self.mode = "LAUNCH_CONTROL"

    def _on_liftoff(self, site, launch_sim_time: float):
        """Step 2: Countdown reaches T=0 → create mission."""
        sc = self._pending_spacecraft
        if sc is None:
            return
        win = self.tw_panel.selected_window
        if win is None and self.planned_windows:
            win = self.planned_windows[0]
        if win is None:
            return

        import copy
        sc_copy = copy.deepcopy(sc)
        mission = self.mc.create_mission(sc_copy, self.selected_origin,
                                         self.selected_dest, win)
        self.selected_mission_name = mission.name
        self._pending_spacecraft = None
        self.mode = "OBSERVE"
        self.mc.event_log.append(
            f"[{seconds_to_date(self.sim_time)}] "
            f"LIFTOFF: {sc_copy.name} from {site.short} — mission {mission.name} active."
        )

    def _on_scrub(self):
        """Countdown scrubbed — return to observe mode."""
        self._pending_spacecraft = None
        self.mode = "OBSERVE"

    def _handle_hq_action(self, action: str):
        """Dispatch an action string emitted by the Command Center home screen."""
        if action == "OPEN_BUILDER":
            self.craft_win.open()
            self.mode = "CRAFT"
        elif action == "ENTER_SOLAR":
            self.screen_mode = "SOLAR"
        elif action.startswith("FOCUS:"):
            name = action.split(":", 1)[1]
            self.selected_mission_name = name
            mission = self.mc.mission_by_name(name)
            if mission:
                # Frame the map on this mission's destination
                self.selected_origin = mission.origin.name
                self.selected_dest = mission.destination.name
                self._recalc_windows()
            self.screen_mode = "SOLAR"
        elif action.startswith("BUILDING:"):
            fid = action.split(":", 1)[1]
            # Placeholder facilities — log a note in the chat.
            names = {"CONGRESS": "Congress", "ASTRO": "Astronaut Corps",
                     "TECH": "Technologies"}
            self.command_center.chat_log.append(
                ("SYSTEM", f"{names.get(fid, fid)} facility is not yet operational "
                           f"(coming in a future update).", theme.TEXT_DIM))

    def _selected_mission(self) -> Mission | None:
        if self.selected_mission_name:
            return self.mc.mission_by_name(self.selected_mission_name)
        return None

    def run(self):
        running = True
        while running:
            dt_real = self.clock.tick(TARGET_FPS) / 1000.0  # seconds

            # ── Events ───────────────────────────────────────────────
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.VIDEORESIZE:
                    self.sw, self.sh = event.w, event.h
                    rects = make_rects(self.sw, self.sh)
                    self.viewport_rect   = rects[0]
                    self.mc_panel.rect   = rects[1]
                    self.tw_panel.rect   = rects[2]
                    self.status_bar.rect = rects[3]
                    self.renderer.viewport = self.viewport_rect

                elif event.type in (pygame.WINDOWCLOSE, pygame.KEYDOWN,
                                    pygame.MOUSEBUTTONDOWN, pygame.MOUSEWHEEL):
                    # Route to sub-windows first (they own separate OS windows)
                    if self.launch_ctrl_win.handle_event(event):
                        continue
                    if self.craft_win.handle_event(event):
                        continue

                    # Command Center home screen captures all main-window input.
                    if self.screen_mode == "HQ":
                        action = self.command_center.handle_event(event, self.mc)
                        if action:
                            self._handle_hq_action(action)
                        # Global keys still work from HQ
                        if event.type == pygame.KEYDOWN and not self.command_center.chat_active:
                            if event.key == pygame.K_SPACE:
                                self.paused = not self.paused
                            elif event.key == pygame.K_t:
                                self.warp_idx = min(len(WARP_LEVELS)-1, self.warp_idx+1)
                            elif event.key == pygame.K_y:
                                self.warp_idx = max(0, self.warp_idx-1)
                        continue

                    if event.type == pygame.MOUSEBUTTONDOWN:
                        self._handle_mouse_down(event)
                    elif event.type == pygame.MOUSEWHEEL:
                        mx, my = pygame.mouse.get_pos()
                        factor = 1.15 if event.y > 0 else 1/1.15
                        self.renderer.camera.zoom(factor, mx, my)
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            # Return to Command Center home screen
                            self.screen_mode = "HQ"
                        else:
                            self._handle_key(event.key, running)

                elif event.type == pygame.MOUSEBUTTONUP:
                    if self.screen_mode == "SOLAR":
                        self.renderer.camera.stop_drag()

                elif event.type == pygame.MOUSEMOTION:
                    if self.screen_mode == "SOLAR" and self.renderer.camera.dragging:
                        self.renderer.camera.update_drag(event.pos[0], event.pos[1])

            # ── Simulation step ───────────────────────────────────────
            if not self.paused:
                dt_sim = dt_real * WARP_LEVELS[self.warp_idx]
                self.sim_time += dt_sim
                self.mc.sim_time = self.sim_time
                self.mc.step(dt_sim)

            # ── Launch control step ───────────────────────────────────
            self.launch_ctrl_win.step(dt_real, self.sim_time)

            # ── Command center background update ──────────────────────
            if self.screen_mode == "HQ":
                self.command_center.update(dt_real)

            # ── Render ────────────────────────────────────────────────
            if self.screen_mode == "HQ":
                self.command_center.draw(self.screen, self.mc, self.sim_time,
                                         WARP_LEVELS[self.warp_idx], self.paused,
                                         self.sw, self.sh)
                # Sub-windows still draw on top (separate OS windows)
                self.craft_win.draw()
                self.launch_ctrl_win.draw()
                pygame.display.flip()
            else:
                self._render()

        pygame.quit()
        sys.exit(0)

    def _handle_mouse_down(self, event):
        sx, sy = event.pos

        if event.button == 3:  # right click — pan start
            self.renderer.camera.start_drag(sx, sy)
            return

        if event.button == 1:
            # Check mission control panel
            hit = self.mc_panel.handle_click(sx, sy, self.mc)
            if hit:
                self.selected_mission_name = hit
                return

            # Click in viewport — select body
            if self.viewport_rect.collidepoint(sx, sy):
                hit_body = self.renderer.body_at_screen(sx, sy, self.bodies,
                                                         self.sim_time, threshold=16)
                if hit_body:
                    if hit_body == self.selected_origin:
                        # Re-click origin → set as destination
                        if hit_body != self.selected_dest:
                            self.selected_dest = hit_body
                            self._recalc_windows()
                    else:
                        # Set as origin or destination on alternate clicks
                        mods = pygame.key.get_mods()
                        if mods & pygame.KMOD_SHIFT:
                            self.selected_dest = hit_body
                        else:
                            self.selected_origin = hit_body
                        self._recalc_windows()

    def _handle_key(self, key: int, running: bool):
        # Transfer window navigation
        if self.tw_panel.handle_key(key):
            return

        if key == pygame.K_SPACE:
            self.paused = not self.paused

        elif key == pygame.K_t:
            self.warp_idx = min(len(WARP_LEVELS) - 1, self.warp_idx + 1)

        elif key == pygame.K_y:
            self.warp_idx = max(0, self.warp_idx - 1)

        elif key == pygame.K_c:
            if self.craft_win.is_open:
                self.craft_win.close()
                self.mode = "OBSERVE"
            else:
                self.craft_win.open()
                self.mode = "CRAFT"

        elif key == pygame.K_w:
            self._recalc_windows()

        elif key == pygame.K_g:
            self.show_orbits = not self.show_orbits

        elif key == pygame.K_h:
            self.show_phase_line = not self.show_phase_line

        elif key == pygame.K_l:
            # Open launch control for a demo probe
            if not self.planned_windows:
                self._recalc_windows()
            sc = make_demo_spacecraft(f"Probe-{len(self.mc.missions)+1:02d}")
            self._on_craft_ready(sc)

        elif key == pygame.K_F1:
            self.show_help = not self.show_help

        elif key == pygame.K_HOME:
            # Reset camera to inner solar system
            cam = self.renderer.camera
            cam.cx = self.viewport_rect.x + self.viewport_rect.width // 2
            cam.cy = self.viewport_rect.y + self.viewport_rect.height // 2
            cam.scale = 180 / AU

        elif key == pygame.K_1:
            # Quick select origin/dest pairs
            self.selected_origin, self.selected_dest = "Earth", "Mars"
            self._recalc_windows()
        elif key == pygame.K_2:
            self.selected_origin, self.selected_dest = "Earth", "Jupiter"
            self._recalc_windows()
        elif key == pygame.K_3:
            self.selected_origin, self.selected_dest = "Earth", "Venus"
            self._recalc_windows()
        elif key == pygame.K_4:
            self.selected_origin, self.selected_dest = "Earth", "Saturn"
            self._recalc_windows()
        elif key == pygame.K_5:
            self.selected_origin, self.selected_dest = "Mars", "Jupiter"
            self._recalc_windows()

    def _render(self):
        self.screen.fill(theme.BG)
        t = self.sim_time
        cam = self.renderer.camera
        sun = self.bodies["Sun"]

        # ── Solar system viewport ─────────────────────────────────────
        self.renderer.begin_frame()

        # Orbit lines
        if self.show_orbits:
            for body in self.bodies.values():
                hi = body.name in (self.selected_origin, self.selected_dest)
                self.renderer.draw_orbit(body, t, highlighted=hi)

        # Planned transfer arc
        if self.planned_windows:
            win = self.tw_panel.selected_window or self.planned_windows[0]
            org = self.bodies.get(self.selected_origin)
            dst = self.bodies.get(self.selected_dest)
            if org and dst:
                self.renderer.draw_planned_trajectory(win, org, dst, t, G * sun.mass)

        # Phase angle line
        if self.show_phase_line:
            org = self.bodies.get(self.selected_origin)
            dst = self.bodies.get(self.selected_dest)
            if org and dst:
                self.renderer.draw_phase_angle(org, dst, t)

        # Active spacecraft trajectories
        for m in self.mc.missions:
            self.renderer.draw_trajectory(m.spacecraft)

        # Bodies
        for body in self.bodies.values():
            selected = body.name in (self.selected_origin, self.selected_dest)
            self.renderer.draw_body(body, t, selected=selected)

        # Spacecraft dots
        for m in self.mc.missions:
            sel = m.name == self.selected_mission_name
            self.renderer.draw_spacecraft(m.spacecraft, selected=sel)

        # Scale bar
        self.renderer.draw_scale_bar()

        # Viewport border
        pygame.draw.rect(self.screen, theme.BORDER, self.viewport_rect, 1)

        # ── Right panels ──────────────────────────────────────────────
        self.mc_panel.draw(self.screen, self.mc)
        self.tw_panel.draw(self.screen, t)

        # ── Status bar ────────────────────────────────────────────────
        self.status_bar.draw(
            self.screen, t,
            WARP_LEVELS[self.warp_idx],
            f"{self.selected_origin}→{self.selected_dest}",
            self._selected_mission(),
            self.paused,
            self.mode,
        )

        # ── Sub-windows ───────────────────────────────────────────────
        self.craft_win.draw()
        self.launch_ctrl_win.draw()

        # ── Help overlay ──────────────────────────────────────────────
        if self.show_help:
            self._draw_help()

        # ── Corner labels ─────────────────────────────────────────────
        self._draw_origin_dest_labels()

        pygame.display.flip()

    def _draw_origin_dest_labels(self):
        """Draw selected origin/destination labels in viewport corner."""
        x = self.viewport_rect.x + 8
        y = self.viewport_rect.y + 8
        theme.draw_text(self.screen,
                        f"ORIGIN:  {self.selected_origin}", x, y,
                        color=theme.TEXT_GREEN, size=theme.FONT_SIZE_MD, bold=True)
        theme.draw_text(self.screen,
                        f"TARGET:  {self.selected_dest}", x, y + 18,
                        color=theme.TEXT_WARN, size=theme.FONT_SIZE_MD, bold=True)
        theme.draw_text(self.screen,
                        f"[1-5] quick pairs  [Shift+click] set target",
                        x, y + 36, color=theme.TEXT_DIM, size=theme.FONT_SIZE_SM)

    def _draw_help(self):
        ow, oh = 560, 420
        ox = (self.sw - ow) // 2
        oy = (self.sh - oh) // 2
        overlay = pygame.Surface((ow, oh), pygame.SRCALPHA)
        overlay.fill((8, 12, 20, 230))
        self.screen.blit(overlay, (ox, oy))
        pygame.draw.rect(self.screen, theme.BORDER_HI, (ox, oy, ow, oh), 1)

        theme.draw_text(self.screen, "[ ABSOLUTESPACE — CONTROLS ]",
                        ox + 20, oy + 12, color=theme.ACCENT, size=theme.FONT_SIZE_LG, bold=True)

        helps = [
            ("Scroll",        "Zoom in/out"),
            ("Right-drag",    "Pan camera"),
            ("Left-click",    "Select body as origin"),
            ("Shift+click",   "Select body as destination"),
            ("1-5",           "Quick origin→destination pairs"),
            ("Space",         "Pause / Resume simulation"),
            ("T / Y",         "Increase / Decrease time warp"),
            ("G",             "Toggle orbit lines"),
            ("H",             "Toggle phase angle line"),
            ("C",             "Open Craft Builder"),
            ("W",             "Recalculate transfer windows"),
            ("L",             "Quick-launch demo probe"),
            ("HOME",          "Reset camera"),
            ("F1",            "Toggle this help"),
            ("Esc",           "Quit"),
            ("", ""),
            ("In Craft Builder:", ""),
            ("Arrow keys",    "Navigate module list"),
            ("Enter",         "Add module to current stage"),
            ("Delete",        "Remove last module"),
            ("S",             "Add new stage"),
            ("L",             "Launch spacecraft"),
            ("R",             "Reset craft"),
            ("1-5",           "Filter modules by type"),
            ("Tab",           "Cycle builder tabs"),
        ]

        x = ox + 20
        y = oy + 40
        for key, desc in helps:
            if key == "":
                y += 4
                continue
            theme.draw_text(self.screen, key, x, y, color=theme.ACCENT, size=theme.FONT_SIZE_SM)
            theme.draw_text(self.screen, desc, x + 180, y, color=theme.TEXT, size=theme.FONT_SIZE_SM)
            y += 15

        theme.draw_text(self.screen, "Press F1 to close",
                        ox + ow // 2 - 60, oy + oh - 22,
                        color=theme.TEXT_DIM, size=theme.FONT_SIZE_SM)


if __name__ == "__main__":
    app = App()
    app.run()
