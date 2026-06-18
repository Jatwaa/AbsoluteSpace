"""Terminal-aesthetic color palette and font helpers."""

import pygame

# ── Palette ───────────────────────────────────────────────────────────────────
BG          = (8,  10,  16)       # near-black space
BG_PANEL    = (12, 16,  24)       # panel background
BG_HEADER   = (18, 24,  36)       # panel header
BORDER      = (40, 60,  90)       # dim panel border
BORDER_HI   = (60, 120, 180)      # highlighted border
GRID        = (15, 20,  30)       # faint grid lines

TEXT        = (170, 210, 255)     # primary text (cool blue-white)
TEXT_DIM    = (80,  110, 150)     # secondary / dim text
TEXT_BRIGHT = (220, 240, 255)     # highlighted text
TEXT_WARN   = (255, 200,  60)     # warning yellow
TEXT_ALERT  = (255,  80,  60)     # alert red
TEXT_GREEN  = (100, 220, 140)     # success / good values
TEXT_ORANGE = (255, 150,  50)     # intermediate / caution

ACCENT      = (60,  160, 255)     # accent blue (selected items)
ACCENT_DIM  = (30,   80, 130)     # dim accent
SELECTED    = (30,   60, 100)     # selected row background

# Trajectory colors
TRAJ_ACTIVE   = (80, 200, 255, 160)
TRAJ_PLANNED  = (100, 255, 100, 120)
TRAJ_COMPLETE = (100, 100, 100, 80)

# Orbit colors (faint)
ORBIT_LINE  = (30, 45, 70)
ORBIT_HI    = (50, 80, 130)

SUN_GLOW    = (255, 200, 50)
STAR_COLOR  = (200, 200, 220)

# ── Layout constants ──────────────────────────────────────────────────────────
PANEL_RIGHT_W  = 320
PANEL_BOTTOM_H = 160
FONT_SIZE_SM   = 11
FONT_SIZE_MD   = 13
FONT_SIZE_LG   = 16
FONT_SIZE_XL   = 20

_fonts: dict[tuple, pygame.font.Font] = {}

def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _fonts:
        try:
            _fonts[key] = pygame.font.SysFont("Consolas", size, bold=bold)
        except Exception:
            _fonts[key] = pygame.font.SysFont("monospace", size, bold=bold)
    return _fonts[key]


def draw_panel(surface: pygame.Surface, rect: pygame.Rect,
               title: str = "", highlighted: bool = False):
    """Draw a terminal-style panel with optional title."""
    pygame.draw.rect(surface, BG_PANEL, rect)
    border_color = BORDER_HI if highlighted else BORDER
    pygame.draw.rect(surface, border_color, rect, 1)

    if title:
        font = get_font(FONT_SIZE_SM, bold=True)
        hdr_rect = pygame.Rect(rect.x, rect.y, rect.width, 18)
        pygame.draw.rect(surface, BG_HEADER, hdr_rect)
        pygame.draw.line(surface, border_color,
                         (rect.x, rect.y + 18), (rect.right, rect.y + 18), 1)
        txt = font.render(f"[ {title} ]", True, ACCENT)
        surface.blit(txt, (rect.x + 6, rect.y + 3))


def draw_text(surface: pygame.Surface, text: str, x: int, y: int,
              color=None, size: int = FONT_SIZE_SM, bold: bool = False) -> int:
    """Draw text, return height used."""
    if color is None:
        color = TEXT
    font = get_font(size, bold=bold)
    rendered = font.render(text, True, color)
    surface.blit(rendered, (x, y))
    return rendered.get_height() + 2


def draw_text_lines(surface: pygame.Surface, lines: list[str],
                    x: int, y: int, color=None, size: int = FONT_SIZE_SM,
                    line_height: int = 15) -> int:
    """Draw multiple lines, return total height."""
    for line in lines:
        draw_text(surface, line, x, y, color=color, size=size)
        y += line_height
    return y


def draw_bar(surface: pygame.Surface, x: int, y: int, w: int, h: int,
             value: float, max_value: float, color=None, bg_color=None):
    """Draw a filled progress bar."""
    if bg_color is None:
        bg_color = BORDER
    if color is None:
        color = TEXT_GREEN
    pygame.draw.rect(surface, bg_color, (x, y, w, h))
    if max_value > 0:
        fill = int(w * min(1.0, value / max_value))
        if fill > 0:
            pygame.draw.rect(surface, color, (x, y, fill, h))
    pygame.draw.rect(surface, BORDER, (x, y, w, h), 1)


def draw_hline(surface: pygame.Surface, x: int, y: int, w: int, color=None):
    if color is None:
        color = BORDER
    pygame.draw.line(surface, color, (x, y), (x + w, y))
