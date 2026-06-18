"""
Craft Builder — separate OS window with KSP-style stack editor and real-module tree catalog.

Layout:
  Left  (300px) : Collapsible module tree (real-world modules from all space agencies)
  Center(360px) : Rocket stack — modules shown as named blocks per stage (KSP style)
  Right (260px) : Live stats — per-stage ΔV, mass, TWR, mission feasibility checks
  Bottom (44px) : Craft name, action buttons
"""

import math
import pygame
from typing import Optional, Callable

from sim.craft import Spacecraft, SpacecraftStage, Module, ModuleType
from sim.module_db import TreeNode, build_module_tree
from . import theme

# ── Window dimensions ─────────────────────────────────────────────────────────
WIN_W, WIN_H = 980, 740
TREE_W  = 300
STACK_W = 360
STATS_W = WIN_W - TREE_W - STACK_W   # 320
BTM_H   = 44

# ── Stack block appearance ────────────────────────────────────────────────────
BLOCK_W  = 280
BLOCK_H  = 38
BLOCK_GAP = 3
STAGE_HDR = 26

MODULE_COLORS: dict[ModuleType, tuple] = {
    ModuleType.COMMAND:    (45,  130,  75),
    ModuleType.ENGINE:     (180,  72,  40),
    ModuleType.FUEL_TANK:  (45,   88, 150),
    ModuleType.PAYLOAD:    (110,  55, 160),
    ModuleType.SOLAR_PANEL:(155, 135,  35),
    ModuleType.COMMS:      (35,  125, 148),
}

AGENCY_BADGE_COLORS: dict[str, tuple] = {
    "NASA":   (0,   68, 153),
    "SpaceX": (24,  24,  24),
    "ESA":    (0,   73, 135),
    "JAXA":   (65,  35, 135),
    "ISRO":   (255, 153,   0),
    "CNSA":   (198,   0,  32),
    "Roscosmos": (0, 120,  60),
    "Blue Origin": (30, 80, 130),
    "Rocket Lab":  (100, 30, 30),
    "Northrop":    (80,  80,  80),
    "Boeing":      (0,   80, 155),
    "ULA":         (50, 100, 160),
    "ArianeGroup": (0,  100, 150),
    "DOE":         (200, 80,   0),
    "Generic":     (60,  60,  60),
}


def _agency_from_desc(desc: str) -> str:
    """Extract first agency abbreviation from description string like '[NASA/JPL] ...'"""
    if desc.startswith("["):
        bracket = desc[1:desc.find("]")]
        return bracket.split("/")[0].strip()
    return "Generic"


def _badge_color(module: Module) -> tuple:
    agency = _agency_from_desc(module.description)
    for key, col in AGENCY_BADGE_COLORS.items():
        if key.lower() in agency.lower():
            return col
    return AGENCY_BADGE_COLORS["Generic"]


def _darken(color: tuple, factor: float = 0.25) -> tuple:
    return tuple(min(255, int(c * factor)) for c in color[:3])


def _type_icon(t: ModuleType) -> str:
    return {
        ModuleType.ENGINE:     "⚙",
        ModuleType.FUEL_TANK:  "◉",
        ModuleType.COMMAND:    "◈",
        ModuleType.PAYLOAD:    "⬡",
        ModuleType.SOLAR_PANEL:"◇",
        ModuleType.COMMS:      "◎",
    }.get(t, "□")


def _default_craft() -> Spacecraft:
    """
    Demo craft: Artemis-I layout as a flat parts list.
    Top (index 0) = Orion CM.  Bottom = S-IC booster.
    Decouplers between each section define the stage breaks.
    """
    from sim.module_db import build_flat_catalog
    cat = build_flat_catalog()

    def get(name: str) -> Module:
        m = cat.get(name)
        if m is None:
            raise KeyError(f"Module not found in catalog: {name!r}")
        return m

    parts = [
        # ── Payload / crew ──
        get("Orion MPCV"),
        get("Orion Solar Panels"),
        get("MRO HGA (3m)"),
        get("Orion ESM Tank"),
        # ── Stage 3 (S-IVB equivalent) ──
        get("SLS Core/ICPS Interstage"),
        get("S-IVB Tank"),
        get("J-2"),
        # ── Stage 2 (S-II equivalent) ──
        get("Saturn V Interstage (S-II/S-IVB)"),
        get("S-II Stage Tanks"),
        get("RS-25D/E"),
        get("RS-25D/E"),
        # ── Stage 1 (S-IC equivalent) ──
        get("Saturn V Interstage (S-IC/S-II)"),
        get("S-IC Stage Tanks"),
        get("F-1"),
        get("F-1"),
        get("F-1"),
    ]
    sc = Spacecraft(name="Artemis-I", parts=parts)
    return sc


# ── Tree renderer helper ──────────────────────────────────────────────────────

class TreeView:
    """Renders and manages interaction for a collapsible module tree."""

    ROW_H = 20

    def __init__(self, root: TreeNode):
        self.root = root
        self.flat: list[tuple[int, TreeNode]] = []   # (depth, node) visible rows
        self.sel_idx = 0
        self.scroll = 0
        self._rebuild_flat()

    def _rebuild_flat(self):
        self.flat = []
        self._walk(self.root, 0)

    def _walk(self, node: TreeNode, depth: int):
        if node is self.root:
            for child in node.children:
                self._walk(child, 0)
            return
        self.flat.append((depth, node))
        if not node.is_leaf and node.expanded:
            for child in node.children:
                self._walk(child, depth + 1)

    def toggle_expand(self, idx: int):
        if 0 <= idx < len(self.flat):
            depth, node = self.flat[idx]
            if not node.is_leaf:
                node.expanded = not node.expanded
                self._rebuild_flat()

    def selected_module(self) -> Optional[Module]:
        if 0 <= self.sel_idx < len(self.flat):
            _, node = self.flat[self.sel_idx]
            return node.module if node.is_leaf else None
        return None

    def draw(self, surf: pygame.Surface, rect: pygame.Rect):
        x, y0 = rect.x + 4, rect.y
        w = rect.width - 8
        row_h = self.ROW_H
        visible_start = self.scroll // row_h
        visible_end = visible_start + rect.height // row_h + 2

        surf.set_clip(rect)
        for i in range(visible_start, min(visible_end, len(self.flat))):
            depth, node = self.flat[i]
            ry = y0 + i * row_h - self.scroll
            if ry + row_h < rect.y or ry > rect.bottom:
                continue

            selected = i == self.sel_idx

            if selected:
                pygame.draw.rect(surf, theme.SELECTED,
                                 (rect.x, ry, rect.width, row_h))

            indent = depth * 12 + 6
            tx = x + indent

            if node.is_leaf:
                mod = node.module
                mod_col = MODULE_COLORS.get(mod.module_type, theme.BORDER)
                badge_col = _badge_color(mod)

                # Type swatch
                pygame.draw.rect(surf, mod_col, (tx, ry + 4, 4, row_h - 8))

                # Agency badge (tiny 2-char pill)
                agency = _agency_from_desc(mod.description)[:6]
                badge_font = theme.get_font(9)
                badge_surf = badge_font.render(agency, True, (200, 200, 200))
                bw = badge_surf.get_width() + 4
                pygame.draw.rect(surf, badge_col, (tx + 7, ry + 4, bw, row_h - 8))
                surf.blit(badge_surf, (tx + 9, ry + 5))

                # Module name
                name_col = theme.TEXT_BRIGHT if selected else theme.TEXT
                name_font = theme.get_font(11)
                name_surf = name_font.render(node.label[:28], True, name_col)
                surf.blit(name_surf, (tx + 9 + bw + 3, ry + 4))

                # Key stat right-aligned
                stat = _key_stat(mod)
                stat_font = theme.get_font(9)
                stat_surf = stat_font.render(stat, True, theme.TEXT_DIM)
                surf.blit(stat_surf, (rect.right - stat_surf.get_width() - 6, ry + 6))

            else:
                # Branch node
                arrow = "▼" if node.expanded else "▶"
                arrow_col = theme.ACCENT if node.expanded else theme.TEXT_DIM
                branch_font = theme.get_font(11, bold=True)
                arrow_surf = theme.get_font(10).render(arrow + " ", True, arrow_col)
                surf.blit(arrow_surf, (tx, ry + 4))
                label_surf = branch_font.render(node.label[:32], True,
                                                theme.ACCENT if selected else theme.TEXT_DIM)
                surf.blit(label_surf, (tx + arrow_surf.get_width(), ry + 4))

        surf.set_clip(None)

    def handle_scroll(self, dy: int, viewport_h: int = 600):
        max_scroll = max(0, len(self.flat) * self.ROW_H - viewport_h)
        self.scroll = max(0, min(max_scroll, self.scroll - dy * 20))

    def click(self, mouse_y: int, tree_content_top: int):
        """
        Map a window-space y coordinate to a flat-list index.
        tree_content_top: the y pixel where row 0 begins (window coords).
        Row i renders at tree_content_top + i*ROW_H - scroll.
        Inverse: i = (mouse_y - tree_content_top + scroll) // ROW_H
        """
        idx = (mouse_y - tree_content_top + self.scroll) // self.ROW_H
        if 0 <= idx < len(self.flat):
            if self.sel_idx == idx:
                self.toggle_expand(idx)
            else:
                self.sel_idx = idx
                _, node = self.flat[idx]
                if not node.is_leaf:
                    self.toggle_expand(idx)

    def navigate(self, direction: int, viewport_h: int = 600):
        self.sel_idx = max(0, min(len(self.flat) - 1, self.sel_idx + direction))
        row_px = self.sel_idx * self.ROW_H
        if row_px < self.scroll:
            self.scroll = row_px
        elif row_px + self.ROW_H > self.scroll + viewport_h:
            self.scroll = row_px + self.ROW_H - viewport_h


def _key_stat(mod: Module) -> str:
    if mod.thrust > 0 and mod.isp > 0:
        if mod.thrust < 1000:
            return f"{mod.thrust:.0f}N {mod.isp}s"
        elif mod.thrust < 1_000_000:
            return f"{mod.thrust/1000:.0f}kN {mod.isp}s"
        else:
            return f"{mod.thrust/1000:.0f}kN"
    if mod.fuel_capacity > 0:
        if mod.fuel_capacity >= 1_000_000:
            return f"{mod.fuel_capacity/1000000:.1f}Mt"
        elif mod.fuel_capacity >= 1_000:
            return f"{mod.fuel_capacity/1000:.0f}t"
        else:
            return f"{mod.fuel_capacity:.0f}kg"
    if mod.power_output > 0:
        return f"{mod.power_output/1000:.1f}kW"
    if mod.crew_capacity > 0:
        return f"{mod.crew_capacity}crew"
    return f"{mod.dry_mass}kg"


# ── Decoupler / separator visual constants ────────────────────────────────────
DECOUPLER_H   = 22    # height of the separator bar row
DECOUPLER_COL = (200, 140, 40)   # amber — stands out from module blocks


# ── Main window class ─────────────────────────────────────────────────────────

class CraftBuilderWindow:
    def __init__(self, on_launch: Callable[[Spacecraft], None]):
        self.on_launch = on_launch
        self._open = False
        self._window: Optional[pygame.Window] = None
        self._surf: Optional[pygame.Surface] = None

        self._module_tree = build_module_tree()
        self._tree_view = TreeView(self._module_tree)

        self.spacecraft = _default_craft()
        self.craft_name = self.spacecraft.name
        self._editing_name = False
        self._name_buf = self.craft_name

        # Index into spacecraft.parts for the selected part (-1 = nothing)
        self.selected_part_idx: int = -1
        self.stack_scroll = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self):
        if self._open:
            if self._window:
                self._window.focus()
            return
        self._window = pygame.Window(
            "AbsoluteSpace — Craft Builder",
            size=(WIN_W, WIN_H),
            resizable=False,
        )
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

    # ── Event dispatch ────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.Event) -> bool:
        if not self._open or self._window is None:
            return False
        ev_win = getattr(event, "window", None)
        if ev_win is not None and ev_win != self._window:
            return False

        if event.type == pygame.WINDOWCLOSE:
            self.close()
            return True
        if event.type == pygame.KEYDOWN:
            return self._handle_key(event)
        if event.type == pygame.MOUSEBUTTONDOWN:
            return self._handle_click(event.pos, event.button)
        if event.type == pygame.MOUSEWHEEL:
            return self._handle_scroll(event)
        return False

    def _handle_key(self, event: pygame.Event) -> bool:
        key = event.key

        if self._editing_name:
            if key in (pygame.K_RETURN, pygame.K_ESCAPE):
                self.craft_name = self._name_buf.strip() or "Spacecraft"
                self.spacecraft.name = self.craft_name
                self._editing_name = False
            elif key == pygame.K_BACKSPACE:
                self._name_buf = self._name_buf[:-1]
            elif event.unicode and event.unicode.isprintable():
                self._name_buf += event.unicode
            return True

        if key == pygame.K_ESCAPE:
            self.close()
        elif key == pygame.K_UP:
            self._tree_view.navigate(-1, WIN_H - BTM_H - 32)
        elif key == pygame.K_DOWN:
            self._tree_view.navigate(1, WIN_H - BTM_H - 32)
        elif key == pygame.K_LEFT:
            idx = self._tree_view.sel_idx
            depth, node = self._tree_view.flat[idx]
            if not node.is_leaf and node.expanded:
                self._tree_view.toggle_expand(idx)
        elif key == pygame.K_RIGHT:
            idx = self._tree_view.sel_idx
            depth, node = self._tree_view.flat[idx]
            if not node.is_leaf and not node.expanded:
                self._tree_view.toggle_expand(idx)
        elif key == pygame.K_RETURN:
            self._add_selected_module()
        elif key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            self._remove_selected_part()
        elif key == pygame.K_r:
            self.spacecraft = _default_craft()
            self.craft_name = self.spacecraft.name
            self.selected_part_idx = -1
        elif key == pygame.K_l:
            self._do_launch()
        elif key == pygame.K_n:
            self._editing_name = True
            self._name_buf = self.craft_name
        # Move selected part up/down in the list
        elif key == pygame.K_PAGEUP:
            self._move_selected_part(-1)
        elif key == pygame.K_PAGEDOWN:
            self._move_selected_part(1)
        return True

    def _handle_click(self, pos: tuple[int, int], button: int) -> bool:
        x, y = pos
        body_h = WIN_H - BTM_H

        if y >= body_h:
            self._handle_bottom_click(x, y)
            return True

        if x < TREE_W:
            TREE_CONTENT_TOP = 32
            self._tree_view.click(y, TREE_CONTENT_TOP)
            if button == 1:
                mod = self._tree_view.selected_module()
                if mod:
                    self._add_module(mod)
            return True

        if TREE_W <= x < TREE_W + STACK_W:
            self._handle_stack_click(x - TREE_W, y)
            return True

        return True

    def _handle_scroll(self, event: pygame.Event) -> bool:
        mx, my = pygame.mouse.get_pos()
        tree_viewport_h = WIN_H - BTM_H - 32   # content area below panel header
        if mx < TREE_W:
            self._tree_view.handle_scroll(event.y, tree_viewport_h)
        else:
            self.stack_scroll = max(0, self.stack_scroll - event.y * 28)
        return True

    def _handle_stack_click(self, lx: int, y: int):
        """
        Hit-test against the flat parts list.  Each part renders at a known y;
        decouplers use DECOUPLER_H, regular modules use BLOCK_H + BLOCK_GAP.
        Content starts at STACK_CONTENT_TOP = 32 (after the panel header).
        """
        STACK_CONTENT_TOP = 32
        cy = STACK_CONTENT_TOP - self.stack_scroll
        sc = self.spacecraft

        for idx, part in enumerate(sc.parts):
            if part.module_type == ModuleType.DECOUPLER:
                row_h = DECOUPLER_H
            else:
                row_h = BLOCK_H + BLOCK_GAP

            if cy <= y <= cy + row_h:
                if self.selected_part_idx == idx:
                    # Second click → remove
                    sc.parts.pop(idx)
                    self.selected_part_idx = -1
                else:
                    self.selected_part_idx = idx
                return
            cy += row_h

    def _handle_bottom_click(self, x: int, y: int):
        bh = WIN_H - BTM_H
        btn_h = 28
        btn_y = bh + (BTM_H - btn_h) // 2
        buttons = [
            ("LAUNCH", WIN_W - 100),
            ("RESET",  WIN_W - 200),
            ("CLOSE",  WIN_W - 300),
        ]
        for label, bx in buttons:
            if bx <= x <= bx + 90 and btn_y <= y <= btn_y + btn_h:
                if label == "LAUNCH":
                    self._do_launch()
                elif label == "RESET":
                    self.spacecraft = _default_craft()
                    self.craft_name = self.spacecraft.name
                    self.selected_part_idx = -1
                elif label == "CLOSE":
                    self.close()
                return
        if 8 <= x <= 220 and btn_y <= y <= btn_y + btn_h:
            self._editing_name = True
            self._name_buf = self.craft_name

    # ── Craft actions ─────────────────────────────────────────────────────────

    def _add_selected_module(self):
        mod = self._tree_view.selected_module()
        if mod:
            self._add_module(mod)

    def _add_module(self, mod: Module):
        """Append the module to the parts list (below the selected part if any)."""
        sc = self.spacecraft
        if self.selected_part_idx >= 0:
            sc.parts.insert(self.selected_part_idx + 1, mod)
            self.selected_part_idx += 1
        else:
            sc.parts.append(mod)
            self.selected_part_idx = len(sc.parts) - 1

    def _remove_selected_part(self):
        sc = self.spacecraft
        if 0 <= self.selected_part_idx < len(sc.parts):
            sc.parts.pop(self.selected_part_idx)
            self.selected_part_idx = min(self.selected_part_idx, len(sc.parts) - 1)

    def _move_selected_part(self, direction: int):
        """Swap selected part up (-1) or down (+1) in the list."""
        sc = self.spacecraft
        idx = self.selected_part_idx
        new_idx = idx + direction
        if 0 <= idx < len(sc.parts) and 0 <= new_idx < len(sc.parts):
            sc.parts[idx], sc.parts[new_idx] = sc.parts[new_idx], sc.parts[idx]
            self.selected_part_idx = new_idx

    def _do_launch(self):
        import copy
        self.spacecraft.name = self.craft_name
        self.on_launch(copy.deepcopy(self.spacecraft))
        self.close()

    # ── Drawing ───────────────────────────────────────────────────────────────

    def draw(self):
        if not self._open or self._surf is None or self._window is None:
            return
        surf = self._surf
        surf.fill(theme.BG)

        h = WIN_H - BTM_H
        pygame.draw.line(surf, theme.BORDER, (TREE_W, 0),      (TREE_W, h))
        pygame.draw.line(surf, theme.BORDER, (TREE_W + STACK_W, 0), (TREE_W + STACK_W, h))
        pygame.draw.line(surf, theme.BORDER, (0, h), (WIN_W, h))

        self._draw_tree_panel(surf, pygame.Rect(0, 0, TREE_W, h))
        self._draw_stack_panel(surf, pygame.Rect(TREE_W, 0, STACK_W, h))
        self._draw_stats_panel(surf, pygame.Rect(TREE_W + STACK_W, 0, STATS_W, h))
        self._draw_bottom_bar(surf, pygame.Rect(0, h, WIN_W, BTM_H))

        # Detail tooltip for hovered module
        mod = self._tree_view.selected_module()
        if mod:
            self._draw_module_detail(surf, mod)

        self._window.flip()

    def _draw_tree_panel(self, surf: pygame.Surface, rect: pygame.Rect):
        # Title
        theme.draw_text(surf, "MODULE CATALOG", rect.x + 6, rect.y + 4,
                        color=theme.ACCENT, bold=True, size=12)
        theme.draw_text(surf, "Click to select  ▶/▼ expand  Enter adds",
                        rect.x + 6, rect.y + 18, color=theme.TEXT_DIM, size=9)
        theme.draw_hline(surf, rect.x, rect.y + 30, rect.width)

        tree_rect = pygame.Rect(rect.x, rect.y + 32, rect.width, rect.height - 32)
        self._tree_view.draw(surf, tree_rect)

    def _draw_stack_panel(self, surf: pygame.Surface, rect: pygame.Rect):
        """
        Render the flat parts list top-to-bottom.
        Regular modules → colored blocks.
        Decouplers → full-width amber separator bars with stage ΔV annotation.
        Stages are numbered from the bottom (firing order), so we pre-compute
        them once for the ΔV labels on each separator.
        """
        x0, y0, w = rect.x, rect.y, rect.width
        sc = self.spacecraft

        # Header
        theme.draw_text(surf, "ROCKET STACK", x0 + 8, y0 + 4,
                        color=theme.ACCENT, bold=True, size=12)
        theme.draw_text(surf,
                        "top = payload  |  add parts from catalog  |  click to select  |  PgUp/Dn reorder",
                        x0 + 8, y0 + 18, color=theme.TEXT_DIM, size=9)
        theme.draw_hline(surf, x0, y0 + 30, w)

        # Pre-compute stage dV labels keyed by decoupler position
        # Stages in firing order: stage 0 fires first (bottom of rocket)
        computed_stages = sc.compute_stages()
        n_stages = len(computed_stages)

        # Map each decoupler's parts-list position to the stage ΔV *above* it
        # (the section between this decoupler and the next one up fires as that stage)
        stage_dv_at: dict[int, tuple[int, float]] = {}   # parts_idx -> (stage_firing_idx, dv)
        dec_count = 0
        for idx, part in enumerate(sc.parts):
            if part.module_type == ModuleType.DECOUPLER:
                # This decoupler separates "above group" (higher stage index) from below
                # The section below it fires first → stage index = n_decouplers - dec_count - 1
                firing_idx = n_stages - dec_count - 1
                if 0 <= firing_idx < n_stages:
                    dv = sc.stage_delta_v(firing_idx)
                    stage_dv_at[idx] = (firing_idx, dv)
                dec_count += 1

        # Also annotate the topmost section (above all decouplers) as the last stage
        # That's handled in the stats panel; no bar for the top section.

        clip = pygame.Rect(x0, y0 + 31, w, rect.height - 31)
        surf.set_clip(clip)

        cy = y0 + 32 - self.stack_scroll
        connector_x = x0 + w // 2

        for idx, part in enumerate(sc.parts):
            is_sel = idx == self.selected_part_idx

            if part.module_type == ModuleType.DECOUPLER:
                # ── Separator bar ──────────────────────────────────────────
                bar_rect = pygame.Rect(x0 + 8, cy, w - 16, DECOUPLER_H)
                pygame.draw.rect(surf, _darken(DECOUPLER_COL, 0.25), bar_rect)
                pygame.draw.rect(surf,
                                 theme.ACCENT if is_sel else DECOUPLER_COL,
                                 bar_rect, 2 if is_sel else 1)

                # Separation lines each side
                pygame.draw.line(surf, DECOUPLER_COL,
                                 (x0 + 8, cy + DECOUPLER_H // 2),
                                 (x0 + w - 8, cy + DECOUPLER_H // 2), 1)

                # Label: part name + ΔV for the stage above this decoupler
                if idx in stage_dv_at:
                    fire_idx, dv = stage_dv_at[idx]
                    stage_num = n_stages - fire_idx   # display number (1 = upper)
                    label = f"  {part.name}   [Stage {stage_num} above: {dv:.0f} m/s]"
                else:
                    label = f"  {part.name}"

                theme.draw_text(surf, label, x0 + 12, cy + 4,
                                color=theme.TEXT_BRIGHT if is_sel else DECOUPLER_COL,
                                size=10, bold=True)

                if is_sel:
                    theme.draw_text(surf, "click again to remove",
                                    x0 + w - 135, cy + 5,
                                    color=theme.TEXT_ALERT, size=9)
                cy += DECOUPLER_H

            else:
                # ── Module block ───────────────────────────────────────────
                bx = x0 + (w - BLOCK_W) // 2
                self._draw_module_block(surf, part, bx, cy, idx)

                # Thin connector line to next part (skip after last)
                if idx < len(sc.parts) - 1 and sc.parts[idx + 1].module_type != ModuleType.DECOUPLER:
                    pygame.draw.line(surf, theme.BORDER,
                                     (connector_x, cy + BLOCK_H),
                                     (connector_x, cy + BLOCK_H + BLOCK_GAP))
                cy += BLOCK_H + BLOCK_GAP

        if not sc.parts:
            theme.draw_text(surf,
                            "[ empty — click modules in the catalog to build your rocket ]",
                            x0 + 14, cy + 20, color=theme.TEXT_DIM, size=10)

        surf.set_clip(None)

    def _draw_module_block(self, surf: pygame.Surface, mod: Module,
                           bx: int, by: int, parts_idx: int):
        mod_col = MODULE_COLORS.get(mod.module_type, theme.BORDER)
        badge_col = _badge_color(mod)
        is_sel = parts_idx == self.selected_part_idx

        block_rect = pygame.Rect(bx, by, BLOCK_W, BLOCK_H)
        bg = _darken(mod_col, 0.22)
        pygame.draw.rect(surf, bg, block_rect)

        # Left color bar
        pygame.draw.rect(surf, mod_col, (bx, by, 6, BLOCK_H))

        # Agency badge
        agency = _agency_from_desc(mod.description)[:8]
        badge_font = theme.get_font(9)
        badge_surf = badge_font.render(agency, True, (210, 210, 210))
        bw = badge_surf.get_width() + 6
        pygame.draw.rect(surf, badge_col, (bx + 9, by + 7, bw, BLOCK_H - 14))
        surf.blit(badge_surf, (bx + 12, by + 8))

        # Module name
        icon = _type_icon(mod.module_type)
        name_col = theme.TEXT_BRIGHT if is_sel else theme.TEXT
        theme.draw_text(surf, f"{icon} {mod.name}",
                        bx + 12 + bw + 3, by + 5, color=name_col, size=12)

        # Key stat sub-line
        stat = _key_stat(mod)
        theme.draw_text(surf, stat, bx + 12 + bw + 3, by + 21,
                        color=theme.TEXT_DIM, size=10)

        # Border
        border_col = theme.ACCENT if is_sel else mod_col
        pygame.draw.rect(surf, border_col, block_rect, 2 if is_sel else 1)

        if is_sel:
            theme.draw_text(surf, "click again to remove",
                            bx + BLOCK_W - 138, by + 14,
                            color=theme.TEXT_ALERT, size=9)

    def _draw_stats_panel(self, surf: pygame.Surface, rect: pygame.Rect):
        x, y = rect.x + 8, rect.y + 4
        w = rect.width - 16
        sc = self.spacecraft

        theme.draw_text(surf, "CRAFT STATS", x, y, color=theme.ACCENT, bold=True, size=12)
        y += 18
        theme.draw_hline(surf, x, y, w)
        y += 6

        def row(label: str, value: str, col=None, size: int = 11):
            nonlocal y
            theme.draw_text(surf, label, x, y, color=theme.TEXT_DIM, size=size)
            theme.draw_text(surf, value, x + 130, y, color=col or theme.TEXT_BRIGHT, size=size)
            y += 14

        total_dv = sc.total_delta_v
        dv_col = (theme.TEXT_GREEN if total_dv > 8000
                  else theme.TEXT_WARN if total_dv > 3000
                  else theme.TEXT_ALERT)
        twr_col = (theme.TEXT_GREEN if sc.twr > 0.5
                   else theme.TEXT_WARN if sc.twr > 0.05
                   else theme.TEXT_ALERT)

        stages = sc.compute_stages()
        row("Total mass:",    f"{sc.total_mass/1000:.2f} t")
        row("Dry mass:",      f"{sum(s.dry_mass for s in stages)/1000:.2f} t")
        row("Propellant:",    f"{sum(s.propellant_mass for s in stages)/1000:.1f} t")
        row("Stages:",        str(len(stages)))
        row("Total ΔV:",      f"{total_dv:.0f} m/s", col=dv_col)
        row("Thrust:",        f"{sc.thrust/1000:.0f} kN")
        row("TWR (launch):",  f"{sc.twr:.3f}", col=twr_col)
        row("Crew:",          str(sc.crew))

        y += 4
        theme.draw_hline(surf, x, y, w)
        y += 6
        theme.draw_text(surf, "PER STAGE  (firing order, 1=first)", x, y,
                        color=theme.TEXT_DIM, bold=True, size=11)
        y += 14

        for i, stage in enumerate(stages):
            col = theme.TEXT_DIM
            theme.draw_text(surf, f"Stage {i+1}", x, y, color=col, bold=True, size=11)
            y += 13
            dv_s = sc.stage_delta_v(i)
            theme.draw_text(surf, f"  ΔV: {dv_s:.0f} m/s", x, y,
                            color=theme.TEXT_GREEN if dv_s > 500 else theme.TEXT_DIM, size=11)
            y += 13
            theme.draw_text(surf, f"  Thr: {stage.total_thrust/1000:.0f} kN  "
                            f"Isp: {stage.effective_isp:.0f} s", x, y,
                            color=theme.TEXT_DIM, size=11)
            y += 13
            theme.draw_text(surf, f"  Wet: {stage.wet_mass/1000:.1f} t  "
                            f"Dry: {stage.dry_mass/1000:.1f} t", x, y,
                            color=theme.TEXT_DIM, size=11)
            y += 16
            if y > rect.bottom - 160:
                break

        y += 4
        theme.draw_hline(surf, x, y, w)
        y += 6
        theme.draw_text(surf, "MISSION FEASIBILITY", x, y, color=theme.TEXT_DIM, bold=True, size=11)
        y += 14

        checks = [
            ("LEO orbit",       9_300,   "Surface → Low Earth Orbit"),
            ("→ Mars xfer",     5_717,   "Earth departure + capture"),
            ("→ Venus xfer",    5_400,   "Earth departure + capture"),
            ("→ Jupiter xfer",  8_900,   "Earth departure + capture"),
            ("→ Saturn xfer",  10_500,   "Earth departure + capture"),
            ("→ Neptune",      15_800,   "Earth departure + capture"),
        ]
        for name, req, _ in checks:
            ok = total_dv >= req
            col = theme.TEXT_GREEN if ok else theme.TEXT_ALERT
            mark = "✓" if ok else "✗"
            theme.draw_text(surf, f"{mark} {name}", x, y, color=col, size=11)
            theme.draw_text(surf, f"{req:,}", x + 135, y, color=theme.TEXT_DIM, size=10)
            y += 14
            if y > rect.bottom - 10:
                break

    def _draw_module_detail(self, surf: pygame.Surface, mod: Module):
        """Small detail box at bottom of stats panel."""
        rx = TREE_W + STACK_W + 4
        ry = WIN_H - BTM_H - 120
        rw = STATS_W - 8
        rh = 116
        pygame.draw.rect(surf, theme.BG_PANEL, (rx, ry, rw, rh))
        pygame.draw.rect(surf, theme.BORDER_HI, (rx, ry, rw, rh), 1)
        x, y = rx + 6, ry + 4
        theme.draw_text(surf, mod.name, x, y, color=theme.TEXT_BRIGHT, bold=True, size=11)
        y += 15
        # Description (word-wrap crude)
        desc = mod.description
        chars_per_line = (rw - 12) // 6
        lines = []
        while len(desc) > chars_per_line:
            cut = desc[:chars_per_line].rfind(" ")
            if cut < 0: cut = chars_per_line
            lines.append(desc[:cut])
            desc = desc[cut+1:]
        lines.append(desc)
        for line in lines[:4]:
            theme.draw_text(surf, line, x, y, color=theme.TEXT_DIM, size=10)
            y += 12
        y += 2
        stats = []
        if mod.thrust > 0:
            t = mod.thrust
            ts = f"{t:.0f}N" if t < 1000 else (f"{t/1000:.1f}kN" if t < 1_000_000 else f"{t/1000:.0f}kN")
            stats.append(f"Thrust: {ts}  Isp: {mod.isp}s")
        if mod.fuel_capacity > 0:
            fc = mod.fuel_capacity
            stats.append(f"Propellant: {fc/1000:.1f}t" if fc >= 1000 else f"Propellant: {fc:.0f}kg")
        if mod.power_output > 0:
            stats.append(f"Power out: {mod.power_output/1000:.1f}kW")
        if mod.power_draw > 0 and mod.module_type != ModuleType.ENGINE:
            stats.append(f"Power draw: {mod.power_draw}W")
        stats.append(f"Dry mass: {mod.dry_mass}kg")
        for s in stats[:2]:
            theme.draw_text(surf, s, x, y, color=theme.TEXT, size=10)
            y += 12

    def _draw_bottom_bar(self, surf: pygame.Surface, rect: pygame.Rect):
        pygame.draw.rect(surf, theme.BG_HEADER, rect)
        pygame.draw.line(surf, theme.BORDER, rect.topleft, rect.topright)
        bh = rect.y
        btn_h, btn_w = 28, 90
        btn_y = bh + (BTM_H - btn_h) // 2

        # Name field
        name_col = theme.ACCENT if self._editing_name else theme.BORDER
        pygame.draw.rect(surf, theme.BG_PANEL, (8, btn_y, 230, btn_h))
        pygame.draw.rect(surf, name_col, (8, btn_y, 230, btn_h), 1)
        display = (self._name_buf if self._editing_name else self.craft_name) + \
                  ("▎" if self._editing_name else "")
        theme.draw_text(surf, f"  {display}", 8, btn_y + 7,
                        color=theme.TEXT_BRIGHT if self._editing_name else theme.TEXT, size=12)
        theme.draw_text(surf, "[N] rename", 244, btn_y + 8, color=theme.TEXT_DIM, size=10)

        theme.draw_text(surf,
                        "↑↓ nav tree  Enter/click adds module  Del removes selected  PgUp/Dn reorders",
                        260, btn_y + 8, color=theme.TEXT_DIM, size=9)

        buttons = [
            ("LAUNCH", theme.TEXT_GREEN),
            ("RESET",  theme.TEXT_DIM),
            ("CLOSE",  theme.TEXT_DIM),
        ]
        for i, (label, col) in enumerate(buttons):
            bx = WIN_W - 100 - i * 105
            pygame.draw.rect(surf, theme.BG_PANEL, (bx, btn_y, btn_w, btn_h))
            pygame.draw.rect(surf, col, (bx, btn_y, btn_w, btn_h), 1)
            fw = theme.get_font(12).size(label)[0]
            theme.draw_text(surf, label, bx + (btn_w - fw) // 2, btn_y + 7, color=col, size=12)
