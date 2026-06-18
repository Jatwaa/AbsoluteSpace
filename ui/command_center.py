"""
Command Center — the game's home screen (NASA-style mission operations hub).

Layout (full main window):
  ┌─────────────────────────────────────────────────────────────────┐
  │  HEADER: title · date · time-warp                                 │
  ├────────────┬──────────────────────────────────┬──────────────────┤
  │ GLOBAL     │  ACTIVE MISSIONS                  │  FACILITIES      │
  │ COMMS      │  (craft listing: status, dest,    │  - Craft Builder │
  │ (chat,     │   next attention / issue flags)   │  - Congress      │
  │  multiplay)│                                    │  - Astronauts    │
  │            │                                    │  - Technologies  │
  │            │                                    │  - Enter Map     │
  ├────────────┴──────────────────────────────────┴──────────────────┤
  │  FOOTER: hints                                                     │
  └─────────────────────────────────────────────────────────────────┘

handle_event(event) returns an action string for main.py to act on:
  "OPEN_BUILDER"     — open craft builder window
  "ENTER_SOLAR"      — switch to the solar-system map view
  "FOCUS:<name>"     — enter map focused on a mission
  "BUILDING:<id>"    — a (placeholder) facility was opened
"""

from __future__ import annotations
import pygame
from typing import Optional

from sim.mission import MissionControl, Mission, Urgency, MissionPhase
from sim.transfer import seconds_to_date
from . import theme

HEADER_H = 46
FOOTER_H = 28
LEFT_W   = 300      # chat column
RIGHT_W  = 264      # facilities column

URGENCY_COLOR = {
    Urgency.CRITICAL: theme.TEXT_ALERT,
    Urgency.SOON:     theme.TEXT_ORANGE,
    Urgency.UPCOMING: theme.TEXT_WARN,
    Urgency.NOMINAL:  theme.TEXT_GREEN,
    Urgency.NONE:     theme.TEXT_DIM,
}

PHASE_COLOR = {
    MissionPhase.PLANNING: theme.TEXT_DIM,
    MissionPhase.LAUNCH:   theme.TEXT_WARN,
    MissionPhase.PARKING:  theme.TEXT,
    MissionPhase.TRANSFER: theme.TEXT_GREEN,
    MissionPhase.ARRIVAL:  theme.ACCENT,
    MissionPhase.ORBIT:    theme.TEXT_GREEN,
    MissionPhase.LANDED:   theme.TEXT_GREEN,
    MissionPhase.ABORTED:  theme.TEXT_ALERT,
    MissionPhase.COMPLETE: theme.TEXT_DIM,
}


# ── Facility buttons ──────────────────────────────────────────────────────────

class _Facility:
    def __init__(self, fid: str, label: str, sub: str, enabled: bool,
                 accent: tuple):
        self.fid = fid
        self.label = label
        self.sub = sub
        self.enabled = enabled
        self.accent = accent
        self.rect = pygame.Rect(0, 0, 0, 0)


class CommandCenterScreen:
    def __init__(self):
        # Chat state (multiplayer placeholder — locally simulated)
        self.chat_log: list[tuple[str, str, tuple]] = [
            ("SYSTEM",  "Global comms channel online.", theme.TEXT_DIM),
            ("FLIGHT",  "Welcome to Mission Control, Director.", theme.ACCENT),
            ("CAPCOM",  "All stations reporting nominal.", theme.TEXT),
            ("RANGE",   "Eastern range clear for operations.", theme.TEXT_GREEN),
        ]
        self.chat_input = ""
        self.chat_active = False
        self.chat_scroll = 0

        # Mission list
        self.selected_idx = 0
        self._mission_rows: list[tuple[pygame.Rect, str]] = []

        # Facilities
        self.facilities = [
            _Facility("BUILDER",   "VEHICLE ASSEMBLY",   "Design & build craft",  True,  theme.ACCENT),
            _Facility("MAP",       "MISSION MAP",        "Solar-system view",     True,  theme.TEXT_GREEN),
            _Facility("CONGRESS",  "CONGRESS",           "Budget & funding",      False, theme.TEXT_WARN),
            _Facility("ASTRO",     "ASTRONAUT CORPS",    "Crew roster & training",False, theme.TEXT_ORANGE),
            _Facility("TECH",      "TECHNOLOGIES",       "R&D tech tree",         False, (150, 110, 200)),
        ]
        self._fac_rects: list[_Facility] = self.facilities

        # Layout rects (filled in draw)
        self._chat_rect   = pygame.Rect(0, 0, 0, 0)
        self._chat_input_rect = pygame.Rect(0, 0, 0, 0)
        self._list_rect   = pygame.Rect(0, 0, 0, 0)

        # Simulated incoming chatter
        self._chatter_timer = 0.0
        self._chatter_pool = [
            ("CAPCOM",  "Telemetry lock confirmed on all active vehicles."),
            ("FLIGHT",  "Trajectory team, stand by for window update."),
            ("GUIDANCE","Nav solution converged. Residuals nominal."),
            ("PROP",    "Tank pressures holding steady fleet-wide."),
            ("NETWORK", "Deep Space Network handover complete."),
            ("PUBLIC",  "Press briefing scheduled for next milestone."),
        ]
        self._chatter_idx = 0

    # ── Update (background chatter) ───────────────────────────────────────────

    def update(self, dt_real: float):
        self._chatter_timer += dt_real
        if self._chatter_timer > 18.0:
            self._chatter_timer = 0.0
            who, msg = self._chatter_pool[self._chatter_idx % len(self._chatter_pool)]
            self._chatter_idx += 1
            self.chat_log.append((who, msg, theme.TEXT_DIM))
            if len(self.chat_log) > 100:
                self.chat_log = self.chat_log[-100:]

    # ── Event handling ────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.Event, mc: MissionControl) -> Optional[str]:
        if event.type == pygame.MOUSEBUTTONDOWN:
            return self._handle_click(event.pos, event.button, mc)
        if event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if self._chat_rect.collidepoint(mx, my):
                self.chat_scroll = max(0, self.chat_scroll - event.y * 2)
            return None
        if event.type == pygame.KEYDOWN:
            return self._handle_key(event, mc)
        return None

    def _handle_key(self, event: pygame.Event, mc: MissionControl) -> Optional[str]:
        if self.chat_active:
            if event.key == pygame.K_RETURN:
                if self.chat_input.strip():
                    self.chat_log.append(("DIRECTOR", self.chat_input.strip(),
                                          theme.TEXT_BRIGHT))
                    self.chat_input = ""
            elif event.key == pygame.K_ESCAPE:
                self.chat_active = False
                self.chat_input = ""
            elif event.key == pygame.K_BACKSPACE:
                self.chat_input = self.chat_input[:-1]
            elif event.unicode and event.unicode.isprintable():
                if len(self.chat_input) < 120:
                    self.chat_input += event.unicode
            return None

        # Navigation when chat not focused
        active = mc.missions
        if event.key == pygame.K_UP:
            self.selected_idx = max(0, self.selected_idx - 1)
        elif event.key == pygame.K_DOWN:
            self.selected_idx = min(max(0, len(active) - 1), self.selected_idx + 1)
        elif event.key == pygame.K_RETURN:
            if active:
                return f"FOCUS:{self._sorted_missions(mc)[self.selected_idx].name}"
        elif event.key == pygame.K_b:
            return "OPEN_BUILDER"
        elif event.key == pygame.K_m:
            return "ENTER_SOLAR"
        return None

    def _handle_click(self, pos: tuple[int, int], button: int,
                      mc: MissionControl) -> Optional[str]:
        x, y = pos

        # Chat input box focus
        if self._chat_input_rect.collidepoint(x, y):
            self.chat_active = True
            return None
        else:
            if self.chat_active and not self._chat_rect.collidepoint(x, y):
                self.chat_active = False

        # Facility buttons
        for fac in self.facilities:
            if fac.rect.collidepoint(x, y):
                if fac.fid == "BUILDER":
                    return "OPEN_BUILDER"
                if fac.fid == "MAP":
                    return "ENTER_SOLAR"
                return f"BUILDING:{fac.fid}"

        # Mission rows
        for rect, name in self._mission_rows:
            if rect.collidepoint(x, y):
                # set selection
                for i, m in enumerate(self._sorted_missions(mc)):
                    if m.name == name:
                        self.selected_idx = i
                        break
                if button == 1:
                    return f"FOCUS:{name}"
        return None

    # ── Mission sorting (critical first, then by next attention) ─────────────

    def _sorted_missions(self, mc: MissionControl) -> list[Mission]:
        now = mc.sim_time
        def key(m: Mission):
            info = m.next_attention(now)
            urg_order = {Urgency.CRITICAL: 0, Urgency.SOON: 1, Urgency.UPCOMING: 2,
                         Urgency.NOMINAL: 3, Urgency.NONE: 4}
            return (urg_order[info.urgency], info.time)
        return sorted(mc.missions, key=key)

    # ── Drawing ───────────────────────────────────────────────────────────────

    def draw(self, surf: pygame.Surface, mc: MissionControl,
             sim_time: float, warp: float, paused: bool, sw: int, sh: int):
        surf.fill(theme.BG)
        self._draw_header(surf, sim_time, warp, paused, sw)

        body_top = HEADER_H
        body_h = sh - HEADER_H - FOOTER_H
        self._chat_rect = pygame.Rect(0, body_top, LEFT_W, body_h)
        self._list_rect = pygame.Rect(LEFT_W, body_top, sw - LEFT_W - RIGHT_W, body_h)
        right_rect = pygame.Rect(sw - RIGHT_W, body_top, RIGHT_W, body_h)

        self._draw_chat(surf, self._chat_rect)
        self._draw_missions(surf, self._list_rect, mc, sim_time)
        self._draw_facilities(surf, right_rect)
        self._draw_footer(surf, sw, sh)

    def _draw_header(self, surf, sim_time, warp, paused, sw):
        pygame.draw.rect(surf, theme.BG_HEADER, (0, 0, sw, HEADER_H))
        pygame.draw.line(surf, theme.BORDER_HI, (0, HEADER_H), (sw, HEADER_H))
        theme.draw_text(surf, "ABSOLUTESPACE  ·  MISSION OPERATIONS CENTER",
                        14, 8, color=theme.ACCENT, bold=True, size=theme.FONT_SIZE_LG)
        theme.draw_text(surf, "Flight Director Console", 14, 28,
                        color=theme.TEXT_DIM, size=theme.FONT_SIZE_SM)

        date_str = seconds_to_date(sim_time)
        warp_str = f"×{warp:,.0f}" if warp >= 1 else f"×{warp:.2f}"
        pause = "  [PAUSED]" if paused else ""
        info = f"MET DATE: {date_str}   WARP: {warp_str}{pause}"
        w = theme.get_font(theme.FONT_SIZE_MD).size(info)[0]
        theme.draw_text(surf, info, sw - w - 16, 14,
                        color=theme.TEXT_WARN if paused else theme.TEXT_BRIGHT,
                        size=theme.FONT_SIZE_MD)

    # ── Chat panel ────────────────────────────────────────────────────────────

    def _draw_chat(self, surf: pygame.Surface, rect: pygame.Rect):
        theme.draw_panel(surf, rect, "GLOBAL COMMS  ·  ALL STATIONS")
        x = rect.x + 8
        w = rect.width - 16
        input_h = 26
        log_top = rect.y + 22
        log_bottom = rect.bottom - input_h - 8

        # online indicator
        theme.draw_text(surf, "● 4 controllers online", rect.right - 130, rect.y + 4,
                        color=theme.TEXT_GREEN, size=theme.FONT_SIZE_SM)

        # Messages (newest at bottom)
        line_h = 26
        max_lines = (log_bottom - log_top) // line_h
        visible = self.chat_log[-(max_lines + self.chat_scroll): len(self.chat_log) - self.chat_scroll] \
            if self.chat_scroll else self.chat_log[-max_lines:]
        y = log_top + 4
        font = theme.get_font(theme.FONT_SIZE_SM)
        for who, msg, col in visible:
            theme.draw_text(surf, who, x, y, color=col, bold=True, size=theme.FONT_SIZE_SM)
            # wrap message
            y += 13
            wrapped = _wrap(msg, font, w - 8)
            for wl in wrapped[:2]:
                theme.draw_text(surf, wl, x + 4, y, color=theme.TEXT, size=theme.FONT_SIZE_SM)
                y += 12
            y += 2
            if y > log_bottom - 12:
                break

        # Input box
        self._chat_input_rect = pygame.Rect(rect.x + 6, rect.bottom - input_h - 4,
                                            rect.width - 12, input_h)
        ic = theme.ACCENT if self.chat_active else theme.BORDER
        pygame.draw.rect(surf, theme.BG_PANEL, self._chat_input_rect)
        pygame.draw.rect(surf, ic, self._chat_input_rect, 1)
        prompt = self.chat_input + ("▎" if self.chat_active else "")
        placeholder = prompt if (self.chat_active or self.chat_input) else "Click to broadcast…"
        pcol = theme.TEXT_BRIGHT if self.chat_active else theme.TEXT_DIM
        theme.draw_text(surf, f" {placeholder}", self._chat_input_rect.x + 2,
                        self._chat_input_rect.y + 6, color=pcol, size=theme.FONT_SIZE_SM)

    # ── Mission listing ───────────────────────────────────────────────────────

    def _draw_missions(self, surf: pygame.Surface, rect: pygame.Rect,
                       mc: MissionControl, now: float):
        theme.draw_panel(surf, rect, "ACTIVE MISSIONS  ·  FLEET STATUS")
        x = rect.x + 10
        w = rect.width - 20

        missions = self._sorted_missions(mc)
        crit = sum(1 for m in missions
                   if m.next_attention(now).urgency == Urgency.CRITICAL)

        # Summary strip
        y = rect.y + 24
        theme.draw_text(surf, f"Fleet: {len(missions)} craft", x, y, color=theme.TEXT_DIM)
        if crit:
            theme.draw_text(surf, f"⚠ {crit} REQUIRE ATTENTION", x + 140, y,
                            color=theme.TEXT_ALERT, bold=True)
        else:
            theme.draw_text(surf, "✓ All nominal", x + 140, y, color=theme.TEXT_GREEN)
        y += 18
        theme.draw_hline(surf, x, y, w)
        y += 4

        # Column headers
        cols = self._cols(x, w)
        for cx, label in cols:
            theme.draw_text(surf, label, cx, y, color=theme.TEXT_DIM, size=theme.FONT_SIZE_SM)
        y += 15
        theme.draw_hline(surf, x, y, w)
        y += 4

        self._mission_rows = []

        if not missions:
            theme.draw_text(surf, "No active missions.", x, y + 20, color=theme.TEXT_DIM)
            theme.draw_text(surf, "Open VEHICLE ASSEMBLY to design and launch a craft.",
                            x, y + 38, color=theme.TEXT_DIM)
            return

        row_h = 40
        for i, m in enumerate(missions):
            if y + row_h > rect.bottom - 6:
                break
            info = m.next_attention(now)
            urg_col = URGENCY_COLOR[info.urgency]
            selected = i == self.selected_idx
            row_rect = pygame.Rect(rect.x + 4, y - 2, rect.width - 8, row_h)

            if selected:
                pygame.draw.rect(surf, theme.SELECTED, row_rect)
            # urgency stripe
            pygame.draw.rect(surf, urg_col, (rect.x + 4, y - 2, 3, row_h))

            self._mission_rows.append((row_rect, m.name))

            sc = m.spacecraft
            phase_col = PHASE_COLOR.get(m.phase, theme.TEXT)

            # Row line 1
            theme.draw_text(surf, m.name, cols[0][0], y,
                            color=theme.TEXT_BRIGHT if selected else theme.TEXT, bold=True)
            theme.draw_text(surf, f"{m.origin.name[:5]}→{m.destination.name[:6]}",
                            cols[1][0], y, color=theme.TEXT)
            theme.draw_text(surf, m.phase.value[:14], cols[2][0], y, color=phase_col)
            theme.draw_text(surf, info.countdown_str(now), cols[3][0], y,
                            color=urg_col, bold=info.urgency in (Urgency.CRITICAL, Urgency.SOON))

            # Row line 2 (detail)
            y2 = y + 16
            crew = f"{sc.crew} crew" if sc.crew else "uncrewed"
            detail = f"   {crew} · ΔV {sc.remaining_delta_v:,.0f} m/s · fuel {sc.fuel_remaining/1000:.1f} t"
            theme.draw_text(surf, detail, cols[0][0], y2, color=theme.TEXT_DIM,
                            size=theme.FONT_SIZE_SM)
            # Next attention label / issue
            attn = info.label
            attn_col = urg_col if info.urgency in (Urgency.CRITICAL, Urgency.SOON) else theme.TEXT_DIM
            label = ("⚠ " if info.urgency == Urgency.CRITICAL else "→ ") + attn
            theme.draw_text(surf, label[:34], cols[2][0], y2, color=attn_col,
                            size=theme.FONT_SIZE_SM)

            y += row_h
            theme.draw_hline(surf, x, y - 4, w, color=theme.GRID)

    def _cols(self, x: int, w: int):
        return [
            (x,            "MISSION"),
            (x + 130,      "ROUTE"),
            (x + 250,      "PHASE"),
            (x + w - 70,   "NEXT"),
        ]

    # ── Facilities column ─────────────────────────────────────────────────────

    def _draw_facilities(self, surf: pygame.Surface, rect: pygame.Rect):
        theme.draw_panel(surf, rect, "FACILITIES")
        x = rect.x + 10
        w = rect.width - 20
        y = rect.y + 28

        btn_h = 56
        for fac in self.facilities:
            fac.rect = pygame.Rect(x, y, w, btn_h)
            bg = theme.BG_HEADER if fac.enabled else theme.BG_PANEL
            pygame.draw.rect(surf, bg, fac.rect)
            border = fac.accent if fac.enabled else theme.BORDER
            pygame.draw.rect(surf, border, fac.rect, 1)
            # accent stripe
            pygame.draw.rect(surf, fac.accent if fac.enabled else theme.BORDER,
                             (x, y, 4, btn_h))

            lbl_col = theme.TEXT_BRIGHT if fac.enabled else theme.TEXT_DIM
            theme.draw_text(surf, fac.label, x + 12, y + 8, color=lbl_col,
                            bold=True, size=theme.FONT_SIZE_MD)
            theme.draw_text(surf, fac.sub, x + 12, y + 26, color=theme.TEXT_DIM,
                            size=theme.FONT_SIZE_SM)
            if not fac.enabled:
                theme.draw_text(surf, "LOCKED", x + w - 56, y + 8,
                                color=theme.TEXT_DIM, size=theme.FONT_SIZE_SM)
            y += btn_h + 8

        # Hint footer in column
        y += 4
        theme.draw_hline(surf, x, y, w)
        y += 8
        theme.draw_text(surf, "Locked facilities are", x, y, color=theme.TEXT_DIM,
                        size=theme.FONT_SIZE_SM); y += 13
        theme.draw_text(surf, "placeholders for future", x, y, color=theme.TEXT_DIM,
                        size=theme.FONT_SIZE_SM); y += 13
        theme.draw_text(surf, "expansion.", x, y, color=theme.TEXT_DIM,
                        size=theme.FONT_SIZE_SM)

    def _draw_footer(self, surf: pygame.Surface, sw: int, sh: int):
        y = sh - FOOTER_H
        pygame.draw.rect(surf, theme.BG_HEADER, (0, y, sw, FOOTER_H))
        pygame.draw.line(surf, theme.BORDER, (0, y), (sw, y))
        hint = ("[↑↓] select mission   [Enter] focus on map   [B] vehicle assembly   "
                "[M] mission map   [Space] pause   click chat to broadcast")
        theme.draw_text(surf, hint, 12, y + 7, color=theme.TEXT_DIM, size=theme.FONT_SIZE_SM)


def _wrap(text: str, font: pygame.font.Font, max_w: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for word in words:
        test = (cur + " " + word).strip()
        if font.size(test)[0] <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines
