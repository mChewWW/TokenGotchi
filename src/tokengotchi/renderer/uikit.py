"""Drawing primitives that don't look like stock pygame.

The single clearest tell of a hobby pygame UI is `pygame.draw.rect(...,
border_radius=n)`: it is **not anti-aliased**, so every rounded corner is a
visible staircase. No amount of animation polish hides it.

Everything here is drawn at SUPERSAMPLE× and smoothscaled down, which gives
genuinely smooth edges — and then cached, because doing that per frame at
30fps would not be affordable. Call sites get a ready-made Surface to blit.

Caches are keyed on every parameter that affects the pixels, and are bounded
so an animating value (a rolling currency counter, a hover lerp) cannot grow
them without limit.
"""
from __future__ import annotations

from collections import OrderedDict

import pygame

from . import theme

SUPERSAMPLE = 4

_MAX_CACHE = 512
_shape_cache: OrderedDict = OrderedDict()
_shadow_cache: OrderedDict = OrderedDict()
_text_cache: OrderedDict = OrderedDict()
_font_cache: dict[tuple[int, bool], pygame.font.Font] = {}

# Counts every real (uncached) shape build. Lets a test assert that a panel is
# constructed once and not rebuilt every frame.
build_count = 0


def _remember(cache: OrderedDict, key, value):
    cache[key] = value
    cache.move_to_end(key)
    if len(cache) > _MAX_CACHE:
        cache.popitem(last=False)
    return value


def clear_caches() -> None:
    _shape_cache.clear()
    _shadow_cache.clear()
    _text_cache.clear()


# ── Fonts ───────────────────────────────────────────────────────────────────

# The default face: the whole device is lettered in this.
UI_STACK = ("segoeui", "dejavusans", "arial", "helvetica")

# A second stack, for dense numeric read-outs ONLY. Segoe UI is a good
# large-size UI face and a poor small-size one: at 13-14px bold its counters
# close, so an 8 reads as a 6 and a seven-digit figure reads as "2,40X,XXX".
# Measured across every face on the machine at 13 and 14px on that exact
# string; Tahoma and Verdana are the only two that hold their counters, both
# being screen faces built for small sizes.
#
# Applied by opt-in rather than globally, because swapping the whole UI to fix
# one table disturbs every other surface.
READOUT_STACK = ("tahoma", "verdana", "dejavusans", "segoeui", "arial")


def font(size: int = theme.FONT_LABEL, bold: bool = False,
         face: tuple[str, ...] | None = None) -> pygame.font.Font:
    """A cached font. Prefers a clean UI face, falling back gracefully."""
    stack = face or UI_STACK
    key = (size, bold, stack)
    got = _font_cache.get(key)
    if got is not None:
        return got
    f = None
    for name in stack:
        try:
            f = pygame.font.SysFont(name, size, bold=bold)
            if f is not None:
                break
        except Exception:
            continue
    if f is None:
        f = pygame.font.Font(None, size + 6)
    _font_cache[key] = f
    return f


def text(
    s: str,
    color: tuple[int, int, int],
    size: int = theme.FONT_LABEL,
    bold: bool = False,
    track: int = 0,
    face: tuple[str, ...] | None = None,
) -> pygame.Surface:
    """Cached anti-aliased text. Re-rendering every label every frame is a
    real cost at 30fps and this UI has a lot of labels.

    `track` adds letter-spacing, in pixels, by drawing the string one glyph at
    a time. Bold small type on a dark screen is where this matters: the stems
    thicken but the sidebearings do not, so glyphs run together and a dense
    label reads as a smear. Widening the ROWS does not help — the complaint is
    inside the word. A single pixel is usually enough, and it is applied only
    where a run of text is genuinely dense, because tracking a short label
    makes it look like a ransom note.
    """
    key = (s, color, size, bold, track, face)
    got = _text_cache.get(key)
    if got is not None:
        _text_cache.move_to_end(key)
        return got
    f = font(size, bold, face)
    if track <= 0:
        return _remember(_text_cache, key, f.render(s, True, color))

    glyphs = [f.render(ch, True, color) for ch in s]
    w = sum(g.get_width() for g in glyphs) + track * max(0, len(glyphs) - 1)
    surf = pygame.Surface((max(1, w), f.get_height()), pygame.SRCALPHA)
    x = 0
    for g in glyphs:
        surf.blit(g, (x, 0))
        x += g.get_width() + track
    return _remember(_text_cache, key, surf)


def text_w(s: str, size: int = theme.FONT_LABEL, bold: bool = False,
           track: int = 0, face: tuple[str, ...] | None = None) -> int:
    return font(size, bold, face).size(s)[0] + track * max(0, len(s) - 1)


# ── Shapes ──────────────────────────────────────────────────────────────────

def _lerp(a, b, t: float):
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def round_rect(
    size: tuple[int, int],
    radius: int,
    fill: tuple[int, int, int] | None,
    *,
    border: tuple[int, int, int] | None = None,
    border_w: int = 1,
    gradient_to: tuple[int, int, int] | None = None,
    top_highlight: int = 0,
    alpha: int = 255,
) -> pygame.Surface:
    """An anti-aliased rounded rectangle.

    gradient_to    — vertical gradient from `fill` at the top to this at the
                     bottom. Flat fills read as unfinished; real UI surfaces
                     almost always carry a slight vertical ramp.
    top_highlight  — alpha of a 1px light line inset along the top edge, the
                     cheap trick that makes a surface look like it has
                     thickness rather than being a painted rectangle.
    """
    global build_count
    w, h = int(size[0]), int(size[1])
    if w <= 0 or h <= 0:
        return pygame.Surface((max(w, 1), max(h, 1)), pygame.SRCALPHA)

    key = (w, h, radius, fill, border, border_w, gradient_to, top_highlight, alpha)
    got = _shape_cache.get(key)
    if got is not None:
        _shape_cache.move_to_end(key)
        return got

    build_count += 1
    S = SUPERSAMPLE
    W, H, R = w * S, h * S, radius * S
    big = pygame.Surface((W, H), pygame.SRCALPHA)

    if fill is not None:
        if gradient_to is None:
            pygame.draw.rect(big, fill, (0, 0, W, H), border_radius=R)
        else:
            # Paint a full-bleed gradient, then punch it to the rounded shape
            # by multiplying in the alpha of a rounded mask.
            grad = pygame.Surface((W, H), pygame.SRCALPHA)
            for y in range(H):
                pygame.draw.line(
                    grad, _lerp(fill, gradient_to, y / max(1, H - 1)), (0, y), (W, y)
                )
            mask = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, W, H), border_radius=R)
            grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            big.blit(grad, (0, 0))

    if top_highlight > 0:
        hl = pygame.Surface((W, H), pygame.SRCALPHA)
        inset = R // 2
        pygame.draw.line(
            hl, (255, 255, 255, top_highlight),
            (inset, S), (W - inset, S), max(1, S),
        )
        mask = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, W, H), border_radius=R)
        hl.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        big.blit(hl, (0, 0))

    if border is not None and border_w > 0:
        pygame.draw.rect(
            big, border, (0, 0, W, H), width=border_w * S, border_radius=R
        )

    out = pygame.transform.smoothscale(big, (w, h))
    if alpha < 255:
        out.set_alpha(alpha)
    return _remember(_shape_cache, key, out)


def _blur(surf: pygame.Surface, factor: float = 0.22) -> pygame.Surface:
    """Cheap box blur by downscale-then-upscale. pygame has no gaussian."""
    w, h = surf.get_size()
    small = pygame.transform.smoothscale(
        surf, (max(1, int(w * factor)), max(1, int(h * factor)))
    )
    return pygame.transform.smoothscale(small, (w, h))


def shadow(
    size: tuple[int, int], radius: int, blur: int, alpha: int
) -> pygame.Surface:
    """A soft drop shadow for a rounded rect of `size`.

    Returned surface is larger than `size` by `blur` on every side; blit it at
    (x - blur, y - blur + offset).
    """
    w, h = int(size[0]), int(size[1])
    key = (w, h, radius, blur, alpha)
    got = _shadow_cache.get(key)
    if got is not None:
        _shadow_cache.move_to_end(key)
        return got

    pad = blur
    surf = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
    pygame.draw.rect(
        surf, (0, 0, 0, alpha), (pad, pad, w, h), border_radius=radius
    )
    return _remember(_shadow_cache, key, _blur(surf))


def draw_panel(
    dest: pygame.Surface,
    rect: pygame.Rect,
    *,
    fill=theme.SURFACE,
    gradient_to=None,
    border=theme.BORDER_SUBTLE,
    radius: int = theme.RADIUS_MD,
    elevation=theme.SHADOW_CARD,
    top_highlight: int = 26,
) -> None:
    """Blit a shadowed, gradient, anti-aliased panel. The workhorse."""
    if elevation is not None:
        dy, blur, a = elevation
        sh = shadow((rect.w, rect.h), radius, blur, a)
        dest.blit(sh, (rect.x - blur, rect.y - blur + dy))
    body = round_rect(
        (rect.w, rect.h), radius, fill,
        border=border, gradient_to=gradient_to, top_highlight=top_highlight,
    )
    dest.blit(body, rect.topleft)


def blit_centered(dest: pygame.Surface, surf: pygame.Surface, rect: pygame.Rect,
                  dx: int = 0, dy: int = 0) -> None:
    dest.blit(
        surf,
        (rect.centerx - surf.get_width() // 2 + dx,
         rect.centery - surf.get_height() // 2 + dy),
    )


def scaled_about_center(surf: pygame.Surface, scale: float,
                        center: tuple[int, int]) -> tuple[pygame.Surface, tuple[int, int]]:
    """Scale a surface about its centre. Returns (surface, topleft)."""
    if abs(scale - 1.0) < 0.001:
        return surf, (center[0] - surf.get_width() // 2,
                      center[1] - surf.get_height() // 2)
    w = max(1, int(surf.get_width() * scale))
    h = max(1, int(surf.get_height() * scale))
    out = pygame.transform.smoothscale(surf, (w, h))
    return out, (center[0] - w // 2, center[1] - h // 2)
