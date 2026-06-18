"""All UI panels: Mission Control, Craft Builder, Transfer Windows, Status Bar."""

import math
import pygame
from typing import Optional, Callable

from sim.bodies import CelestialBody, AU
from sim.craft import Spacecraft, Module, ModuleType, MODULE_CATALOG, CATALOG_BY_NAME, SpacecraftStage
from sim.mission import Mission, MissionControl, MissionPhase
from sim.transfer import TransferWindow, mission_delta_v_budget, porkchop_sample, seconds_to_date
from . import theme

DAY = 86400.0
LINE = 15
PAD = 6


# ── Mission Control Panel ──────────────────────────────────────────────────────

class MissionControlPanel:
    def __init__(self, rect: pygame.Rect):
        self.rect = rect
        self.scroll = 0
        self.selected_mission: Optional[str] = None

    def draw(self, surface: pygame.Surface, mc: MissionControl):
        theme.draw_panel(surface, self.rect, "MISSION CONTROL")
        x = self.rect.x + PAD
        y = self.rect.y + 22
        w = self.rect.width - PAD * 2

        # Stats row
        active = len(mc.active_missions)
        total = len(mc.missions)
        theme.draw_text(surface, f"Active: {active}  Total: {total}",
                        x, y, color=theme.TEXT_DIM)
        y += LINE + 2
        theme.draw_hline(surface, x, y, w)
        y += 4

        # Mission list
        missions = mc.missions[-8:]  # show last 8
        for m in missions:
            selected = m.name == self.selected_mission
            bg = theme.SELECTED if selected else None
            if bg:
                pygame.draw.rect(surface, bg, (x - 2, y - 1, w + 4, LINE + 2))

            phase_color = _phase_color(m.phase)
            name_txt = m.name[:16]
            theme.draw_text(surface, name_txt, x, y, color=theme.TEXT_BRIGHT if selected else theme.TEXT)
            status_txt = m.phase.value[:12]
            theme.draw_text(surface, status_txt, x + 110, y, color=phase_color)
            y += LINE

            if selected:
                for line in m.status_lines()[1:]:
                    theme.draw_text(surface, line, x + 4, y, color=theme.TEXT_DIM)
                    y += LINE

        y += 4
        theme.draw_hline(surface, x, y, w)
        y += 4

        # Event log (last few entries)
        log_entries = mc.event_log[-5:]
        for entry in log_entries:
            txt = entry[:w // 7]  # rough char limit
            theme.draw_text(surface, txt, x, y, color=theme.TEXT_DIM)
            y += LINE

    def handle_click(self, sx: int, sy: int, mc: MissionControl) -> Optional[str]:
        if not self.rect.collidepoint(sx, sy):
            return None
        rel_y = sy - self.rect.y - 22
        idx = rel_y // LINE
        missions = mc.missions[-8:]
        if 0 <= idx < len(missions):
            name = missions[idx].name
            self.selected_mission = name if self.selected_mission != name else None
            return name
        return None


# ── Craft Builder Panel ────────────────────────────────────────────────────────

class CraftBuilderPanel:
    def __init__(self, rect: pygame.Rect):
        self.rect = rect
        self.visible = False
        self.selected_module_idx = 0
        self.stage_idx = 0          # which stage we're editing
        self.filter_type: Optional[ModuleType] = None
        self.craft_name = "Spacecraft-1"
        self._editing_name = False

        # Working spacecraft
        self.spacecraft: Optional[Spacecraft] = None
        self.reset_craft()

        # Tab state
        self.tab = 0  # 0=modules, 1=stages, 2=summary
        self._tabs = ["MODULES", "STAGES", "SUMMARY"]

    def reset_craft(self):
        stage = SpacecraftStage()
        from sim.craft import CATALOG_BY_NAME
        # Default starter: Probe Core + Medium Tank + RL-10
        stage.modules = [
            CATALOG_BY_NAME["Probe Core"],
            CATALOG_BY_NAME["Tank M-5"],
            CATALOG_BY_NAME["RL-10B"],
        ]
        self.spacecraft = Spacecraft(
            name=self.craft_name,
            stages=[stage],
            extra_modules=[],
        )

    @property
    def filtered_catalog(self) -> list[Module]:
        if self.filter_type is None:
            return MODULE_CATALOG
        return [m for m in MODULE_CATALOG if m.module_type == self.filter_type]

    def draw(self, surface: pygame.Surface):
        if not self.visible:
            return
        theme.draw_panel(surface, self.rect, "CRAFT BUILDER", highlighted=True)
        x = self.rect.x + PAD
        y = self.rect.y + 22
        w = self.rect.width - PAD * 2

        # Tab bar
        tab_w = w // len(self._tabs)
        for i, tab_name in enumerate(self._tabs):
            tx = x + i * tab_w
            col = theme.ACCENT if i == self.tab else theme.TEXT_DIM
            bg = theme.SELECTED if i == self.tab else None
            if bg:
                pygame.draw.rect(surface, bg, (tx, y, tab_w, LINE + 2))
            theme.draw_text(surface, tab_name, tx + 2, y, color=col)
        y += LINE + 4
        theme.draw_hline(surface, x, y, w)
        y += 4

        if self.tab == 0:
            self._draw_module_list(surface, x, y, w)
        elif self.tab == 1:
            self._draw_stages(surface, x, y, w)
        elif self.tab == 2:
            self._draw_summary(surface, x, y, w)

        # Craft name + action at bottom
        by = self.rect.bottom - 40
        theme.draw_hline(surface, x, by, w)
        theme.draw_text(surface, f"Craft: {self.spacecraft.name}", x, by + 4,
                        color=theme.TEXT_BRIGHT)
        theme.draw_text(surface, f"[L]aunch  [R]eset  [N]ame  [Esc]Close",
                        x, by + 18, color=theme.TEXT_DIM)

    def _draw_module_list(self, surface: pygame.Surface, x: int, y: int, w: int):
        # Filter buttons
        types = [None] + list(ModuleType)
        labels = ["ALL"] + [t.value[:4] for t in ModuleType]
        bw = (w - 4) // len(labels)
        for i, (t, lbl) in enumerate(zip(types, labels)):
            col = theme.ACCENT if t == self.filter_type else theme.TEXT_DIM
            theme.draw_text(surface, lbl, x + i * bw, y, color=col)
        y += LINE + 2
        theme.draw_hline(surface, x, y, w)
        y += 2

        catalog = self.filtered_catalog
        max_rows = (self.rect.bottom - 60 - y) // LINE
        start = max(0, self.selected_module_idx - max_rows // 2)
        end = min(len(catalog), start + max_rows)

        for i in range(start, end):
            m = catalog[i]
            selected = i == self.selected_module_idx
            if selected:
                pygame.draw.rect(surface, theme.SELECTED, (x - 2, y - 1, w + 4, LINE + 1))
            name_col = theme.TEXT_BRIGHT if selected else theme.TEXT
            theme.draw_text(surface, m.name[:22], x, y, color=name_col)
            # Right-align key stat
            if m.thrust > 0:
                stat = f"{m.thrust/1000:.0f}kN"
            elif m.fuel_capacity > 0:
                stat = f"{m.fuel_capacity/1000:.0f}t"
            elif m.power_output > 0:
                stat = f"{m.power_output/1000:.1f}kW"
            else:
                stat = f"{m.dry_mass}kg"
            theme.draw_text(surface, stat, x + w - 55, y, color=theme.TEXT_DIM)
            y += LINE

        # Module details for selected
        if 0 <= self.selected_module_idx < len(catalog):
            m = catalog[self.selected_module_idx]
            dy = self.rect.bottom - 80
            theme.draw_hline(surface, x, dy, w)
            dy += 3
            theme.draw_text(surface, m.description[:w//7], x, dy, color=theme.TEXT_DIM)
            dy += LINE
            details = []
            if m.thrust > 0:
                details.append(f"Thrust:{m.thrust/1000:.0f}kN  Isp:{m.isp}s")
            if m.fuel_capacity > 0:
                details.append(f"Propellant: {m.fuel_capacity/1000:.1f} t")
            if m.crew_capacity > 0:
                details.append(f"Crew: {m.crew_capacity}")
            details.append(f"Dry mass: {m.dry_mass} kg")
            for d in details[:2]:
                theme.draw_text(surface, d, x, dy, color=theme.TEXT_DIM)
                dy += LINE

    def _draw_stages(self, surface: pygame.Surface, x: int, y: int, w: int):
        sc = self.spacecraft
        if not sc:
            return
        for i, stage in enumerate(sc.stages):
            selected = i == self.stage_idx
            header_col = theme.ACCENT if selected else theme.TEXT_DIM
            theme.draw_text(surface, f"Stage {i+1} {'◄' if selected else ''}",
                            x, y, color=header_col, bold=True)
            y += LINE
            theme.draw_text(surface, f"  Thrust: {stage.total_thrust/1000:.0f} kN", x, y, color=theme.TEXT_DIM)
            y += LINE
            theme.draw_text(surface, f"  Isp: {stage.effective_isp:.0f} s", x, y, color=theme.TEXT_DIM)
            y += LINE
            theme.draw_text(surface, f"  ΔV: {sc.stage_delta_v(i):.0f} m/s", x, y, color=theme.TEXT_GREEN)
            y += LINE
            theme.draw_text(surface, f"  Prop: {stage.propellant_mass/1000:.1f} t  Dry: {stage.dry_mass/1000:.1f} t",
                            x, y, color=theme.TEXT_DIM)
            y += LINE
            theme.draw_text(surface, "  Modules:", x, y, color=theme.TEXT_DIM)
            y += LINE
            for m in stage.modules:
                theme.draw_text(surface, f"    {m.name}", x, y, color=theme.TEXT_DIM)
                y += LINE
            theme.draw_hline(surface, x, y, w)
            y += 4

    def _draw_summary(self, surface: pygame.Surface, x: int, y: int, w: int):
        sc = self.spacecraft
        if not sc:
            return

        def row(label: str, value: str, col=None):
            nonlocal y
            theme.draw_text(surface, label, x, y, color=theme.TEXT_DIM)
            theme.draw_text(surface, value, x + 130, y, color=col or theme.TEXT_BRIGHT)
            y += LINE

        row("Total mass:", f"{sc.total_mass/1000:.2f} t")
        row("Stages:", str(len(sc.stages)))
        row("Total ΔV:", f"{sc.total_delta_v:.0f} m/s",
            col=_dv_color(sc.total_delta_v))
        row("Thrust:", f"{sc.thrust/1000:.0f} kN")
        row("TWR:", f"{sc.twr:.2f}", col=theme.TEXT_GREEN if sc.twr > 0.1 else theme.TEXT_ALERT)
        row("Crew:", str(sc.crew))

        y += 4
        theme.draw_hline(surface, x, y, w)
        y += 4
        theme.draw_text(surface, "ΔV requirements (typical):", x, y, color=theme.TEXT_DIM)
        y += LINE
        targets = [
            ("LEO (Earth)", 9300),
            ("Earth→Mars", 5600),
            ("Earth→Jupiter", 8900),
            ("Mars landing", 4100),
        ]
        for dest, dv_req in targets:
            avail = sc.total_delta_v
            ok = avail >= dv_req
            col = theme.TEXT_GREEN if ok else theme.TEXT_ALERT
            check = "✓" if ok else "✗"
            theme.draw_text(surface, f"  {check} {dest}: {dv_req} m/s", x, y, color=col)
            y += LINE

    def handle_key(self, key: int, on_launch: Callable) -> bool:
        if not self.visible:
            return False
        catalog = self.filtered_catalog
        if key == pygame.K_UP:
            self.selected_module_idx = max(0, self.selected_module_idx - 1)
        elif key == pygame.K_DOWN:
            self.selected_module_idx = min(len(catalog) - 1, self.selected_module_idx + 1)
        elif key == pygame.K_RETURN:
            self._add_selected_module()
        elif key == pygame.K_DELETE or key == pygame.K_BACKSPACE:
            self._remove_last_module()
        elif key == pygame.K_TAB:
            self.tab = (self.tab + 1) % len(self._tabs)
        elif key == pygame.K_ESCAPE:
            self.visible = False
        elif key == pygame.K_r:
            self.reset_craft()
        elif key == pygame.K_l:
            on_launch(self.spacecraft)
        elif key == pygame.K_s:
            self._add_stage()
        elif key == pygame.K_1:
            self.filter_type = None
        elif key == pygame.K_2:
            self.filter_type = ModuleType.ENGINE
        elif key == pygame.K_3:
            self.filter_type = ModuleType.FUEL_TANK
        elif key == pygame.K_4:
            self.filter_type = ModuleType.COMMAND
        elif key == pygame.K_5:
            self.filter_type = ModuleType.PAYLOAD
        return True

    def _add_selected_module(self):
        if not self.spacecraft:
            return
        catalog = self.filtered_catalog
        if 0 <= self.selected_module_idx < len(catalog):
            mod = catalog[self.selected_module_idx]
            if self.stage_idx < len(self.spacecraft.stages):
                self.spacecraft.stages[self.stage_idx].modules.append(mod)
            else:
                # Add to extra modules
                self.spacecraft.extra_modules.append(mod)

    def _remove_last_module(self):
        if not self.spacecraft:
            return
        if self.stage_idx < len(self.spacecraft.stages):
            stage = self.spacecraft.stages[self.stage_idx]
            if stage.modules:
                stage.modules.pop()

    def _add_stage(self):
        if self.spacecraft:
            self.spacecraft.stages.append(SpacecraftStage())
            self.stage_idx = len(self.spacecraft.stages) - 1


# ── Transfer Window Panel ──────────────────────────────────────────────────────

class TransferWindowPanel:
    def __init__(self, rect: pygame.Rect):
        self.rect = rect
        self.windows: list[TransferWindow] = []
        self.selected_idx = 0
        self.origin_name = "Earth"
        self.dest_name = "Mars"
        self.budget: dict = {}

    def set_windows(self, windows: list[TransferWindow], budget: dict):
        self.windows = windows
        self.selected_idx = 0
        self.budget = budget

    @property
    def selected_window(self) -> Optional[TransferWindow]:
        if self.windows and 0 <= self.selected_idx < len(self.windows):
            return self.windows[self.selected_idx]
        return None

    def draw(self, surface: pygame.Surface, sim_time: float):
        theme.draw_panel(surface, self.rect, f"TRANSFER WINDOWS  {self.origin_name}→{self.dest_name}")
        x = self.rect.x + PAD
        y = self.rect.y + 22
        w = self.rect.width - PAD * 2

        if not self.windows:
            theme.draw_text(surface, "No windows calculated.", x, y, color=theme.TEXT_DIM)
            theme.draw_text(surface, "Select origin + destination", x, y + LINE, color=theme.TEXT_DIM)
            theme.draw_text(surface, "then press [W] to calculate.", x, y + LINE*2, color=theme.TEXT_DIM)
            return

        # Column headers
        theme.draw_text(surface, "  Departure        ΔV      Dur    Quality", x, y, color=theme.TEXT_DIM)
        y += LINE
        theme.draw_hline(surface, x, y, w)
        y += 3

        for i, win in enumerate(self.windows):
            selected = i == self.selected_idx
            days_until = (win.departure_time - sim_time) / DAY
            past = days_until < 0

            if selected:
                pygame.draw.rect(surface, theme.SELECTED, (x - 2, y - 1, w + 4, LINE + 1))

            col = theme.TEXT_DIM if past else (theme.TEXT_BRIGHT if selected else theme.TEXT)
            mark = "►" if selected else " "
            past_str = "(past)" if past else f"{abs(days_until):.0f}d"
            q_col = _quality_color(win.quality)

            line = f"{mark} {win.departure_date_str}  {win.dv_total:.0f}m/s  {win.duration_days:.0f}d"
            theme.draw_text(surface, line, x, y, color=col)
            theme.draw_text(surface, win.quality, x + w - 56, y, color=q_col)
            y += LINE

        y += 4
        theme.draw_hline(surface, x, y, w)
        y += 4

        # Selected window detail
        win = self.selected_window
        if win:
            theme.draw_text(surface, "Selected window:", x, y, color=theme.TEXT_DIM)
            y += LINE
            theme.draw_text(surface, f"  Dep burn:  {win.dv_departure:.0f} m/s", x, y, color=theme.TEXT)
            y += LINE
            theme.draw_text(surface, f"  Arr burn:  {win.dv_arrival:.0f} m/s", x, y, color=theme.TEXT)
            y += LINE
            theme.draw_text(surface, f"  Total ΔV:  {win.dv_total:.0f} m/s", x, y,
                            color=_dv_color(win.dv_total))
            y += LINE

        # Budget breakdown
        if self.budget:
            y += 4
            theme.draw_hline(surface, x, y, w)
            y += 4
            theme.draw_text(surface, "Mission ΔV budget:", x, y, color=theme.TEXT_DIM)
            y += LINE
            for k, v in self.budget.items():
                if k == "transfer_days":
                    theme.draw_text(surface, f"  {k}: {v:.0f} d", x, y, color=theme.TEXT_DIM)
                elif isinstance(v, float) and v > 0:
                    theme.draw_text(surface, f"  {k}: {v:.0f} m/s", x, y, color=theme.TEXT_DIM)
                y += LINE

    def handle_key(self, key: int) -> bool:
        if key == pygame.K_UP:
            self.selected_idx = max(0, self.selected_idx - 1)
            return True
        if key == pygame.K_DOWN:
            self.selected_idx = min(len(self.windows) - 1, self.selected_idx + 1)
            return True
        return False


# ── Status Bar ────────────────────────────────────────────────────────────────

class StatusBar:
    def __init__(self, rect: pygame.Rect):
        self.rect = rect

    def draw(self, surface: pygame.Surface, sim_time: float, time_warp: float,
             selected_body: Optional[str], selected_mission: Optional[Mission],
             paused: bool, mode: str):
        theme.draw_panel(surface, self.rect, "")
        x = self.rect.x + PAD
        y = self.rect.y + PAD

        # Time display
        date_str = seconds_to_date(sim_time)
        warp_str = f"x{time_warp:.0f}" if time_warp >= 1 else f"x{time_warp:.2f}"
        pause_str = "[PAUSED]" if paused else ""
        time_col = theme.TEXT_WARN if paused else theme.TEXT_BRIGHT
        theme.draw_text(surface, f"DATE: {date_str}  WARP: {warp_str}  {pause_str}",
                        x, y, color=time_col, size=theme.FONT_SIZE_MD)

        # Selected body info
        col2 = x + 340
        if selected_body:
            theme.draw_text(surface, f"SELECTED: {selected_body}", col2, y,
                            color=theme.ACCENT, size=theme.FONT_SIZE_MD)

        # Mode indicator
        col3 = x + 580
        theme.draw_text(surface, f"MODE: {mode}", col3, y,
                        color=theme.TEXT_DIM, size=theme.FONT_SIZE_MD)

        # Controls hint
        col4 = x + 760
        hints = "[C]raft  [W]indows  [Space]Pause  [T/Y]Warp  Scroll:Zoom"
        theme.draw_text(surface, hints, col4, y, color=theme.TEXT_DIM, size=theme.FONT_SIZE_SM)

        # Mission status (selected)
        if selected_mission:
            y2 = y + LINE + 2
            sc = selected_mission.spacecraft
            theme.draw_text(surface, f"{selected_mission.name}  {selected_mission.phase.value}",
                            x, y2, color=theme.TEXT)
            theme.draw_text(surface, f"ΔV rem: {sc.remaining_delta_v:.0f}m/s",
                            x + 280, y2, color=theme.TEXT_DIM)
            theme.draw_text(surface, f"Fuel: {sc.fuel_remaining/1000:.1f}t",
                            x + 400, y2, color=theme.TEXT_DIM)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _phase_color(phase: MissionPhase) -> tuple:
    colors = {
        MissionPhase.PLANNING:  theme.TEXT_DIM,
        MissionPhase.LAUNCH:    theme.TEXT_WARN,
        MissionPhase.PARKING:   theme.TEXT,
        MissionPhase.TRANSFER:  theme.TEXT_GREEN,
        MissionPhase.ARRIVAL:   theme.ACCENT,
        MissionPhase.ORBIT:     theme.TEXT_GREEN,
        MissionPhase.COMPLETE:  theme.TEXT_DIM,
        MissionPhase.ABORTED:   theme.TEXT_ALERT,
        MissionPhase.LANDED:    theme.TEXT_GREEN,
    }
    return colors.get(phase, theme.TEXT)


def _dv_color(dv: float) -> tuple:
    if dv > 10000:
        return theme.TEXT_GREEN
    elif dv > 6000:
        return theme.TEXT_WARN
    else:
        return theme.TEXT_ALERT


def _quality_color(quality: str) -> tuple:
    return {
        "OPTIMAL": theme.TEXT_GREEN,
        "GOOD":    theme.TEXT_GREEN,
        "FAIR":    theme.TEXT_WARN,
        "COSTLY":  theme.TEXT_ALERT,
    }.get(quality, theme.TEXT)
