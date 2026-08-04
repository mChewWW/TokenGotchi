"""Privacy notice screen module.

Draws a first-launch privacy notice overlay and returns the "Got it!" button
rect for click detection. The renderer does NOT track whether the notice has
been seen — that flag lives in state.json. This module is called whenever
show_privacy=True is passed to render_frame().
"""
from __future__ import annotations

import pygame

# ── Colour palette ──────────────────────────────────────────────────────────
BG_DEEP = (18, 16, 28)
BG_PANEL = (34, 30, 52)

BORDER_BRIGHT = (88, 78, 128)

TEXT_PRIMARY = (230, 225, 245)
TEXT_SECONDARY = (160, 150, 190)

ACCENT_PURPLE = (140, 100, 220)

PRIVACY_TEXT_LINES = [
    "TokenGotchi reads only your local",
    "Claude Code session files.",
    "(~/.claude/projects/)",
    "No data is sent anywhere. Ever.",
]


def draw_privacy_notice(
    surface: pygame.Surface,
    font: pygame.font.Font,
    font_large: pygame.font.Font | None = None,
) -> pygame.Rect:
    """Draw the first-launch privacy notice overlay.

    Draws a centred card with privacy text and a "Got it!" button.
    The caller is responsible for tracking whether the notice has been
    accepted (via state.json). This function just renders the UI.

    Args:
        surface:    Pygame surface to draw onto (full window surface).
        font:       Pygame font for body text rendering.
        font_large: Larger font for the title (falls back to font if None).

    Returns:
        pygame.Rect of the "Got it!" button for click detection.
    """
    if font_large is None:
        font_large = font

    win_w = surface.get_width()
    win_h = surface.get_height()

    # Semi-transparent overlay — BG_DEEP at alpha 200
    overlay = pygame.Surface((win_w, win_h), pygame.SRCALPHA)
    overlay.fill((*BG_DEEP, 200))
    surface.blit(overlay, (0, 0))

    # ── Card ──────────────────────────────────────────────────────────────
    card_w = 320
    card_h = 180
    card_x = (win_w - card_w) // 2
    card_y = (win_h - card_h) // 2

    pygame.draw.rect(surface, BG_PANEL, (card_x, card_y, card_w, card_h), border_radius=12)
    pygame.draw.rect(surface, BORDER_BRIGHT, (card_x, card_y, card_w, card_h), 2, border_radius=12)

    # ── Title ─────────────────────────────────────────────────────────────
    title_surf = font_large.render("Privacy Notice", True, TEXT_PRIMARY)
    tx = card_x + (card_w - title_surf.get_width()) // 2
    ty = card_y + 16
    surface.blit(title_surf, (tx, ty))

    # Divider line under title
    div_y = ty + title_surf.get_height() + 6
    pygame.draw.line(surface, BORDER_BRIGHT,
                     (card_x + 20, div_y),
                     (card_x + card_w - 20, div_y), 1)

    # ── Body text ─────────────────────────────────────────────────────────
    line_h = font.get_height() + 4
    text_start_y = div_y + 10
    for i, line in enumerate(PRIVACY_TEXT_LINES):
        if not line:
            continue
        # File path line gets a lighter accent colour
        if line.startswith("(~"):
            color = (110, 190, 255)
        else:
            color = TEXT_SECONDARY
        line_surf = font.render(line, True, color)
        lx = card_x + (card_w - line_surf.get_width()) // 2
        ly = text_start_y + i * line_h
        surface.blit(line_surf, (lx, ly))

    # ── "Got it!" button — full-width within card ──────────────────────────
    btn_margin = 20
    btn_w = card_w - btn_margin * 2
    btn_h = 36
    btn_x = card_x + btn_margin
    btn_y = card_y + card_h - btn_h - 14

    btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
    pygame.draw.rect(surface, ACCENT_PURPLE, btn_rect, border_radius=8)
    # Top highlight line for raised look
    pygame.draw.line(surface, (170, 130, 240),
                     (btn_x + 8, btn_y + 1),
                     (btn_x + btn_w - 8, btn_y + 1), 1)

    btn_label = font.render("Got it!", True, TEXT_PRIMARY)
    blx = btn_x + (btn_w - btn_label.get_width()) // 2
    bly = btn_y + (btn_h - btn_label.get_height()) // 2
    surface.blit(btn_label, (blx, bly))

    return btn_rect
