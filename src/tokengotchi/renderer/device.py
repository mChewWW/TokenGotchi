"""The device — a moulded shell with a recessed CRT screen.

Not a recoloured dashboard, not a recomposed dashboard, but an *object*.
Virtual pets were physical things before they were apps, and the frame should
be the thing.

Everything here is chrome. The creature is drawn by `sprites.py`, which must
not be modified — magnification happens on the blit, never in the sprite code.

**Nothing in here animates ambiently**, with the single rationed exception of
`draw_sparkle` on metal shells. This window sits on top of the user's real
work all day; boring chrome is ignorable, breathing chrome is not. The
starfield is the amplitude ceiling.
"""
from __future__ import annotations

import math

import pygame

import numpy as np

from . import skins as skinmod
from . import ink, metal as metalmod, theme, uikit

# Shell geometry
BEZEL = 8            # case margin from the window edge
SCREEN_X = 26
SCREEN_Y = 40
SCREEN_W = 348
SCREEN_H = 250

_overlay_cache: dict = {}


def screen_rect() -> pygame.Rect:
    return pygame.Rect(SCREEN_X, SCREEN_Y, SCREEN_W, SCREEN_H)


def draw_shell(surf: pygame.Surface, shell=None) -> None:
    """The moulded case: dark base, lit body, soft top bevel."""
    sh = shell or skinmod.SHELL_DEFAULT
    w, h = surf.get_size()
    surf.blit(uikit.round_rect((w, h), 0, sh.lo, border=None), (0, 0))
    body = uikit.round_rect(
        (w - BEZEL * 2, h - BEZEL * 2), 22, sh.body,
        gradient_to=sh.hi, border=sh.hi, top_highlight=60,
    )
    if sh.body_right:
        # Asymmetric case (Joy-Con). Averaging the two halves into one purple
        # would lose the entire reference — the asymmetry IS the design.
        right = uikit.round_rect(
            (w - BEZEL * 2, h - BEZEL * 2), 22, sh.body_right,
            gradient_to=sh.hi_right or sh.body_right, border=sh.hi_right,
            top_highlight=60,
        )
        body = body.copy()
        half = (w - BEZEL * 2) // 2
        body.blit(right, (half, 0), pygame.Rect(half, 0, half, h))
    if sh.metal:
        # A plated face replaces the plastic gradient entirely. It is one
        # cached surface: the ramp and its grain are baked at build time, so a
        # metal case costs the same per frame as a plain one.
        m = metalmod.face(sh.metal, body.get_size())
        body = body.copy()
        body.blit(m, (0, 0), special_flags=0)
        mask = uikit.round_rect(body.get_size(), 22, (255, 255, 255),
                                border=None)
        body.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surf.blit(body, (BEZEL, BEZEL))
    if sh.translucent:
        # Order matters: the machine goes on FIRST, then the plastic's own
        # thickness over it. Blit the internals on top of a body that already
        # has its highlight baked in and nothing ever sits *behind* glass.
        surf.blit(_internals((w, h), sh), (0, 0))
        surf.blit(_thickness((w, h), sh), (0, 0))


# Real component colours, BEFORE the shell tints them. Drawing everything in
# `sh.lo` -- the case's own darkest tone -- makes the "internals" a monochrome
# shadow of the case, which reads as dirt. Internals are foreign objects: a
# green board, an amber ribbon, a black chip, a can.
PCB = (28, 92, 58)
PCB_TRACE = (46, 122, 74)
SILK = (206, 206, 190)
RIBBON = (214, 132, 46)
RIBBON_LINE = (168, 96, 30)
CHIP = (24, 24, 28)
CHIP_LEG = (178, 180, 186)
SPEAKER_C = (120, 122, 128)
SPEAKER_MESH = (70, 72, 78)
CAP = (40, 48, 90)
CAP_STRIPE = (190, 190, 196)
GOLD = (198, 162, 62)
VIA = (196, 198, 204)


def _lerp(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def _board(size):
    """The machine, drawn at FULL contrast in real colours.

    Tinting and blurring happen afterwards in `_internals`. Drawing faint and
    then blurring destroys the image. Drawing solid and then compressing
    contrast is what reads as "behind plastic".

    Components are placed where they actually live and deliberately NOT spread
    evenly: real boards are dense in patches and empty elsewhere, and an even
    scatter reads as wallpaper.
    """
    w, h = size
    s = pygame.Surface(size, pygame.SRCALPHA)

    board = pygame.Rect(22, 300, w - 44, h - 322)
    pygame.draw.rect(s, PCB, board, border_radius=4)
    for y in range(board.top + 8, board.bottom - 4, 7):
        pygame.draw.line(s, PCB_TRACE, (board.left + 6, y), (board.right - 6, y))
    for x in range(board.left + 14, board.right - 10, 21):
        pygame.draw.line(s, PCB_TRACE, (x, board.top + 6), (x, board.bottom - 6))
        for y in range(board.top + 8, board.bottom - 4, 21):
            pygame.draw.circle(s, VIA, (x, y), 1)

    # CPU: a black QFP with a comb of silver legs reads as "chip" universally.
    cpu = pygame.Rect(w // 2 - 30, 368, 60, 34)
    for i in range(0, cpu.w, 6):
        pygame.draw.line(s, CHIP_LEG, (cpu.x + i, cpu.top - 4), (cpu.x + i, cpu.top))
        pygame.draw.line(s, CHIP_LEG, (cpu.x + i, cpu.bottom), (cpu.x + i, cpu.bottom + 4))
    for i in range(0, cpu.h, 6):
        pygame.draw.line(s, CHIP_LEG, (cpu.left - 4, cpu.y + i), (cpu.left, cpu.y + i))
        pygame.draw.line(s, CHIP_LEG, (cpu.right, cpu.y + i), (cpu.right + 4, cpu.y + i))
    pygame.draw.rect(s, CHIP, cpu, border_radius=2)
    pygame.draw.circle(s, (58, 58, 64), (cpu.left + 8, cpu.top + 8), 3)

    # Speaker, behind the real grille.
    scx, scy = w - 74, 396
    pygame.draw.circle(s, SPEAKER_C, (scx, scy), 24)
    for r in range(6, 24, 5):
        pygame.draw.circle(s, SPEAKER_MESH, (scx, scy), r, 1)
    pygame.draw.circle(s, SPEAKER_MESH, (scx, scy), 6)

    # Electrolytics: circle plus a keyed stripe, seen top-down.
    for cx, cy, r in ((58, 388, 11), (92, 408, 8)):
        pygame.draw.circle(s, CAP, (cx, cy), r)
        pygame.draw.circle(s, (18, 22, 44), (cx, cy), r, 1)
        pygame.draw.arc(s, CAP_STRIPE, (cx - r, cy - r, r * 2, r * 2), 2.2, 4.1, 3)

    for lx, ly, lw in ((board.left + 10, 306, 22), (cpu.right + 8, 372, 16)):
        pygame.draw.rect(s, SILK, (lx, ly, lw, 3))

    # The 26px ring around the screen is the largest run of case plastic, and
    # empty it reads as unfinished. Ribbon and cart fingers live here.
    rib = pygame.Rect(w // 2 - 78, 8, 156, 16)
    pygame.draw.rect(s, RIBBON, rib, border_radius=2)
    for i in range(rib.left + 4, rib.right - 2, 4):
        pygame.draw.line(s, RIBBON_LINE, (i, rib.top + 2), (i, rib.bottom - 2))
    for tab in (rib.left - 6, rib.right):
        pygame.draw.rect(s, (72, 44, 22), (tab, rib.top, 6, 16), border_radius=1)

    for side in (10, w - 26):
        pygame.draw.rect(s, RIBBON, (side, 44, 14, 120), border_radius=2)
        for y in range(48, 162, 4):
            pygame.draw.line(s, RIBBON_LINE, (side + 2, y), (side + 11, y))

    for i in range(13):
        pygame.draw.rect(s, GOLD, (44 + i * 24, 28, 13, 8))
    return s


def _internals(size, sh):
    """The machine as seen THROUGH the shell.

    Four things happen behind translucent plastic. Do only one and the result
    reads as flat colour:

      1. blur -- the plastic is not optically smooth
      2. tint toward the shell colour, and desaturate
      3. CRUSH CONTRAST, not presence. Compress the luminance range and keep
         alpha high. Low contrast at high alpha reads as "through plastic";
         high contrast at low alpha reads as "faint dirt".
      4. depth falloff -- a frosted case blurs harder than a clear one
    """
    key = ("guts", size, sh.id, sh.body, sh.guts)
    got = _overlay_cache.get(key)
    if got is not None:
        return got

    board = _board(size)
    arr = pygame.surfarray.pixels3d(board).astype("float32")
    alpha = pygame.surfarray.pixels_alpha(board).copy()

    tint = np.array(sh.body, dtype="float32")
    mix = 0.46 if sh.tinted_guts else 0.14
    arr = arr * (1.0 - mix) + tint * mix

    base = float(np.mean(sh.body))
    # A narrow band (+/-66) around a light case mean squeezes the black chip up
    # into grey. Wider: still 'through plastic', but components keep identity.
    spread = 96.0
    lo, hi = max(0.0, base - spread), min(255.0, base + spread)
    arr = lo + (arr / 255.0) * (hi - lo)

    out = pygame.Surface(size, pygame.SRCALPHA)
    pygame.surfarray.pixels3d(out)[:] = arr.astype("uint8")
    pygame.surfarray.pixels_alpha(out)[:] = (
        alpha.astype("float32") * min(1.0, 0.82 * sh.guts)).astype("uint8")
    del arr, alpha

    out = uikit._blur(out, 0.72 if sh.frosted else 0.88)
    _overlay_cache[key] = out
    return out


def _thickness(size, sh):
    """Edge darkening and screw bosses -- proof the case has volume.

    Thicker plastic means more material, so darker and more saturated. This is
    the strongest translucency cue available and costs almost nothing.
    """
    import math
    key = ("thick", size, sh.id)
    got = _overlay_cache.get(key)
    if got is not None:
        return got
    w, h = size
    s = pygame.Surface(size, pygame.SRCALPHA)
    dark = _lerp(sh.body, (0, 0, 0), 0.45)

    for i in range(8):
        a = int(96 * (1 - i / 8))
        pygame.draw.rect(s, (*dark, a),
                         (BEZEL + i, BEZEL + i,
                          w - (BEZEL + i) * 2, h - (BEZEL + i) * 2),
                         width=1, border_radius=max(2, 22 - i))
    r = screen_rect()
    for i in range(5):
        a = int(84 * (1 - i / 5))
        pygame.draw.rect(s, (*dark, a),
                         (r.x - 7 + i, r.y - 7 + i,
                          r.w + 14 - i * 2, r.h + 14 - i * 2),
                         width=1, border_radius=14)

    for bx, by in ((28, 28), (w - 28, 28), (28, h - 28), (w - 28, h - 28),
                   (28, h // 2 + 60), (w - 28, h // 2 + 60)):
        pygame.draw.circle(s, (*dark, 100), (bx, by), 9)
        pygame.draw.circle(s, (*dark, 140), (bx, by), 5)
        for ang in (0.0, 2.094, 4.189):
            pygame.draw.line(s, (*dark, 175), (bx, by),
                             (bx + int(4 * math.cos(ang)),
                              by + int(4 * math.sin(ang))), 2)
    _overlay_cache[key] = s
    return s


def _pattern(size: tuple[int, int], kind: str, period: int, alpha: int,
             tint: tuple[int, int, int] = (0, 0, 0)) -> pygame.Surface:
    """Cached display pattern. Period is gated in skins.py, not chosen here."""
    key = ("pat", size, kind, period, alpha, tint)
    got = _overlay_cache.get(key)
    if got is not None:
        return got
    w, h = size
    s = pygame.Surface(size, pygame.SRCALPHA)
    if kind == "scan":
        for y in range(0, h, period):
            pygame.draw.line(s, (0, 0, 0, alpha), (0, y), (w, y))
    elif kind == "grid":
        for y in range(0, h, period):
            pygame.draw.line(s, (0, 0, 0, alpha), (0, y), (w, y))
        for x in range(0, w, period):
            pygame.draw.line(s, (0, 0, 0, alpha // 2), (x, 0), (x, h))
    elif kind == "graticule":
        # A scope's grid is LIT, not shadowed — bright divisions on the tube
        # face, brighter still on the centre axes. Drawing it as a dark mask
        # yields something indistinguishable from plain scanlines.
        cx, cy = w // 2, h // 2
        major = period * 5
        for x in range(cx % major, w, major):
            pygame.draw.line(s, (*tint, alpha), (x, 0), (x, h))
        for y in range(cy % major, h, major):
            pygame.draw.line(s, (*tint, alpha), (0, y), (w, y))
        for x in range(cx % period, w, period):        # minor ticks, centre row
            pygame.draw.line(s, (*tint, alpha), (x, cy - 3), (x, cy + 3))
        for y in range(cy % period, h, period):
            pygame.draw.line(s, (*tint, alpha), (cx - 3, y), (cx + 3, y))
        pygame.draw.line(s, (*tint, alpha * 2), (0, cy), (w, cy))
        pygame.draw.line(s, (*tint, alpha * 2), (cx, 0), (cx, h))
    elif kind == "aperture":
        # RGB PHOSPHOR STRIPES, not dark lines.
        #
        # Faint vertical black lines would be indistinguishable from the plain
        # scanline skin — measured: the two base colours are 12.1 apart, both
        # near-black, so only line orientation would differ and at alpha 24
        # that is invisible.
        #
        # A real aperture grille is a colour filter: vertical red, green and
        # blue phosphor columns with a black guard band. It MULTIPLIES rather
        # than darkens uniformly, which is what makes whites fringe and the
        # whole screen read as a Trinitron.
        #
        # The triad is R,G,B,guard = 4 columns, which also keeps the period off
        # the sprite's 3x grid. A natural 3-column triad would trip the moire
        # gate in skins.py, and correctly so.
        k = 255 - alpha * 4
        cols = ((255, k, k), (k, 255, k), (k, k, 255), (k, k, k))
        s.fill((255, 255, 255, 255))
        for x in range(0, w, 4):
            for i, col in enumerate(cols):
                if x + i < w:
                    pygame.draw.line(s, (*col, 255), (x + i, 0), (x + i, h))
    _overlay_cache[key] = s
    return s


def _glare(size: tuple[int, int], strength: int) -> pygame.Surface:
    """Cached glass glare — one soft highlight across the upper screen."""
    key = ("gl", size, strength)
    got = _overlay_cache.get(key)
    if got is not None:
        return got
    w, h = size
    s = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.ellipse(s, (255, 255, 255, strength),
                        (-40, -int(h * 0.48), w + 80, int(h * 0.76)))
    out = uikit._blur(s, 0.2)
    _overlay_cache[key] = out
    return out


def begin_screen(skin=None) -> pygame.Surface:
    """Return an offscreen surface representing the CRT's inside.

    Callers draw the starfield, creature and readout onto this, then pass it to
    `end_screen`, which applies the CRT treatment and blits it into the recess.
    Doing it offscreen is what lets the scanlines and glare sit *over*
    everything on the screen and nothing outside it.
    """
    sk = skin or skinmod.DEFAULT
    s = pygame.Surface((SCREEN_W, SCREEN_H))
    s.fill(sk.base)
    return s


def end_screen(dest: pygame.Surface, inner: pygame.Surface, skin=None,
               skin_shell=None) -> None:
    """Apply the display treatment and seat the screen in its recess."""
    sk = skin or skinmod.DEFAULT
    r = screen_rect()
    if sk.grain:
        inner.blit(skinmod.grain(inner.get_size(), sk.grain), (0, 0))
    if sk.tint:
        t = pygame.Surface(inner.get_size(), pygame.SRCALPHA)
        t.fill(sk.tint)
        inner.blit(t, (0, 0))
    if sk.pattern != "none":
        pat = _pattern(inner.get_size(), sk.pattern, sk.period, sk.alpha,
                       sk.phosphor if sk.pattern == "graticule" else (0, 0, 0))
        # The grille FILTERS light; the line masks subtract it.
        flags = pygame.BLEND_RGBA_MULT if sk.pattern == "aperture" else 0
        inner.blit(pat, (0, 0), special_flags=flags)
    if sk.glare:
        inner.blit(_glare(inner.get_size(), sk.glare), (0, 0))

    # Round the corners by intersecting alpha with a rounded mask, so the CRT
    # is a hole in the shell rather than a square pasted on it.
    shaped = pygame.Surface(inner.get_size(), pygame.SRCALPHA)
    shaped.blit(inner, (0, 0))
    mask = uikit.round_rect(inner.get_size(), 12, (255, 255, 255), border=None)
    shaped.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

    dest.blit(uikit.shadow((r.w, r.h), 12, 9, 190), (r.x - 9, r.y - 5))
    dest.blit(shaped, r.topleft)
    # inner lip — the glass sitting below the case surface
    pygame.draw.rect(dest, (skin_shell or skinmod.SHELL_DEFAULT).lo, r,
                     width=2, border_radius=12)


def draw_rate(inner: pygame.Surface, tokens_per_bit: int, skin=None) -> pygame.Rect:
    """The earn rate, drawn INSIDE the screen.

    Deliberately not on the case. Two reasons, one practical and one about what
    the object is:

      * Inside the screen it takes the skin's own phosphor directly, so it
        needs no background sampling, no OkLCh ink solve and no glint
        exclusion — structurally immune to the entire class of contrast
        problems that case lettering has.
      * The silkscreen is lettering pressed into plastic. A number that changes
        four times a day printed on the case is a category error; a number on
        the display is what a display is for.

    Pace (today's tokens vs. the trailing 7-day average) deliberately does not
    appear here; the detail panel's TODAY row surfaces that number for anyone
    who opens it.
    """
    sk = skin or skinmod.DEFAULT
    w = inner.get_width()

    # TOP-right, not bottom-right. On the hunger row its click target competes
    # with any control sharing that row — keeping it off that row stops future
    # controls there from stealing its clicks.
    rate = uikit.text(f"{tokens_per_bit}T=1b >", sk.phosphor,
                      theme.FONT_CAPTION, bold=True)
    rx = w - 12 - rate.get_width()
    ry = 6
    inner.blit(rate, (rx, ry))
    return pygame.Rect(rx - 4, ry - 3, rate.get_width() + 8,
                       rate.get_height() + 6)


OVERHEAL_MAX = 125.0          # matches food.food_golden_apple's cap
# A brighter yellow such as (255, 214, 0) sits close enough to the default
# skin's meter[1] warning amber (255, 206, 92) that a starving pet and an
# overhealed one read the same colour at a glance. This is a deeper, more
# saturated bronze-gold so it can't be mistaken for a warning state on any
# skin, paired with glint marks (see draw_readout) so "gold" reads as treasure
# rather than as another meter tier.
OVERHEAL_COLOR = (255, 176, 0)
OVERHEAL_SHADE = (120, 74, 0)
OVERHEAL_BORDER = (255, 236, 150)
OVERHEAL_SPARKLE = (255, 255, 235)


def _round_half_up(x: float) -> int:
    """int(x) truncates 99.6 -> 99; the meter needs 100 to actually show 100."""
    return math.floor(x + 0.5)


def draw_readout(inner: pygame.Surface, hunger: float, skin=None,
                 t: float = 0.0) -> None:
    """Phosphor hunger meter, drawn INSIDE the screen.

    Not a separate 80px chrome strip stacked under the stage: putting it on the
    screen is most of what makes the frame an object instead of a form.

    OVERHEAL REPLACES, IT DOES NOT EXTEND. The bar has no room past 100 — it
    is already full there — so a Golden Apple's overheal (100-125) does not
    grow the bar rightward. It repaints the LEADING edge yellow instead, using
    the SAME 0-100 scale as the rest of the bar: 25 points of overheal is 25
    points of width, i.e. one quarter of the bar, not the whole thing. At 125
    the first quarter is yellow and the remaining three quarters are the
    normal "well fed" colour; back down at 100 the yellow is gone.

    `t` is `time.monotonic()` from the caller, used only to twinkle the
    overheal glints (see `_draw_overheal_sparkle`) — the starfield already
    established that a rationed twinkle is the amplitude ceiling for
    animation inside the screen, and a set of glints frozen in place read as
    dirt on the glass rather than as sparkle.
    """
    sk = skin or skinmod.DEFAULT
    pct = max(0.0, min(OVERHEAL_MAX, hunger))
    w = inner.get_width()
    y = inner.get_height() - 34

    # round-half-up, not int()'s truncation: a pet sitting at exactly 100 or
    # 125 hunger must be able to actually show "100%"/"125%" rather than
    # perpetually reading one point short.
    inner.blit(uikit.text(f"HUNGER  {_round_half_up(pct)}%", sk.phosphor,
                          theme.FONT_CAPTION, bold=True), (12, y))

    bw = w - 24
    by = y + 16
    inner.blit(uikit.round_rect((bw, 7), 3, sk.edge,
                                border=sk.phosphor), (12, by))

    if pct <= 100.0:
        fill = _round_half_up(bw * pct / 100.0)
        if fill >= 3:
            # Low hunger shifts the phosphor toward amber then red. A CRT
            # would not have a second phosphor, but legibility of a critical
            # state outranks the conceit — the player must be able to see the
            # pet is starving. Per-skin, not fixed theme constants: on an
            # amber phosphor a fixed amber warning sits 39.7 RGB from normal,
            # and a starving pet looks fed.
            col = (sk.meter[0] if pct >= 50 else
                   sk.meter[1] if pct >= 20 else sk.meter[2])
            inner.blit(uikit.round_rect((fill, 7), 3, col, border=None),
                      (12, by))
    else:
        # Full bar. The amount overhealed eats into it from the left as
        # gold, on the same 0-100 scale as everything else — NOT normalised
        # against the 100-125 overheal range, which would paint the whole bar
        # gold at 125 instead of just the last 25 points' worth of it.
        gold_w = max(0, min(bw, _round_half_up(bw * (pct - 100.0) / 100.0)))
        if gold_w < 3:
            inner.blit(uikit.round_rect((bw, 7), 3, sk.meter[0], border=None),
                      (12, by))
        else:
            # Green is the BACKDROP, drawn full width first — same rounded
            # rect a fully-fed bar would show, right end capped to match the
            # track's true right edge. Gold is drawn on top of it, its OWN
            # 4 corners rounded and no border. Where gold's rounded corners
            # curve away, the green backdrop shows through the dog-ear —
            # exactly how the normal 0-100% fill's leading edge shows the
            # empty track through ITS dog-ears. That backdrop is what makes
            # the join read as a rounded cap instead of either a flat cut
            # (gold's own corner with nothing behind it) or a seam (a border
            # drawn around gold to fake the same effect).
            #
            # Gold's radius is a point bigger than the track's (4 vs 3):
            # against black, the track's radius-3 dog-ear reads clearly, but
            # green is nowhere near as dark, so the same radius against a
            # green backdrop nearly disappears. The extra point of curve
            # keeps the cap legible without the two radii looking mismatched.
            inner.blit(uikit.round_rect((bw, 7), 3, sk.meter[0], border=None),
                      (12, by))
            inner.blit(uikit.round_rect(
                (gold_w, 7), 4, OVERHEAL_COLOR, gradient_to=OVERHEAL_SHADE,
                top_highlight=180), (12, by))
            inset = 2
            if gold_w > inset * 2 + 3:
                pygame.draw.line(inner, OVERHEAL_BORDER,
                                 (12 + inset, by), (12 + gold_w - inset, by))
                pygame.draw.line(inner, OVERHEAL_BORDER,
                                 (12 + inset, by + 6),
                                 (12 + gold_w - inset, by + 6))
            _draw_overheal_sparkle(inner, 12, by, gold_w, 7, t)


def draw_hatch_readout(inner: pygame.Surface, bits_earned: int,
                       bits_needed: int, skin=None) -> None:
    """Progress meter shown in place of the hunger bar while the pet is an EGG.

    An egg can't be fed (see window._draw_creature's `can_feed` gate) and
    doesn't starve in any way the player can act on, so showing "HUNGER 100%"
    here — a bar that visibly does nothing no matter what the player does —
    read as broken. This swaps in the number that actually moves: BITS earned
    toward hatching, same bar geometry as the hunger meter it replaces so the
    swap at hatch time doesn't jump the layout.
    """
    sk = skin or skinmod.DEFAULT
    w = inner.get_width()
    y = inner.get_height() - 34

    bits_needed = max(1, bits_needed)
    shown = max(0, min(bits_earned, bits_needed))
    pct = shown / bits_needed

    inner.blit(uikit.text(f"HATCHING  {shown}/{bits_needed}", sk.phosphor,
                          theme.FONT_CAPTION, bold=True), (12, y))

    bw = w - 24
    by = y + 16
    inner.blit(uikit.round_rect((bw, 7), 3, sk.edge,
                                border=sk.phosphor), (12, by))

    fill = _round_half_up(bw * pct)
    if fill >= 3:
        inner.blit(uikit.round_rect((fill, 7), 3, sk.meter[0], border=None),
                  (12, by))


_SPARKLE_SLOTS = 6   # candidate glint positions; only some are lit any instant


def _draw_overheal_sparkle(inner: pygame.Surface, x: int, y: int,
                           seg_w: int, seg_h: int, t: float) -> None:
    """Glints that drift and twinkle across the overheal segment.

    A couple of glints frozen at fixed x/y read as printed decoration, not
    treasure — the reference is the starfield, where glints scatter across the
    whole field and fade in and out rather than sitting in one spot.
    This borrows that shape: each of a handful of candidate slots
    gets a deterministic pseudo-random position covering the FULL segment
    (both x across its width and y across the bar's height, not just the
    centre line) and a twinkle phase from `t`, so slots light up and die
    across the bar rather than blinking in place.

    Deterministic from `t` alone (no per-frame RNG, same reasoning as
    draw_sparkle): a paused window and a resumed one agree, and nothing
    accumulates.
    """
    if seg_w < 8:
        return
    for i in range(_SPARKLE_SLOTS):
        seed = (i * 2654435761 + 0x9E3779B1) & 0xFFFFFFFF
        rx = ((seed >> 4) % 1009) / 1009.0
        ry = ((seed >> 14) % 503) / 503.0
        # One full light/dark cycle every 7-18s, not once or twice a second.
        # The starfield's twinkle_speed range reads fine for a continuous sine
        # pulse but reads as frantic flickering once it is gated by the
        # b < 0.55 cutoff below, so this range is much slower.
        speed = 0.055 + ((seed >> 22) % 100) / 100.0 * 0.09
        phase = ((seed >> 6) % 1000) / 1000.0 * math.tau

        b = math.sin(phase + t * speed * math.tau)
        if b < 0.55:                     # dark most of the time, like a star
            continue
        k = (b - 0.55) / 0.45            # 0..1 brightness within the flash

        cx = x + 2 + int(rx * max(1, seg_w - 4))
        cy = y + 2 + int(ry * max(1, seg_h - 4))
        arm = 1 if k < 0.6 else 2
        col = tuple(int(c * k) for c in OVERHEAL_SPARKLE)
        pygame.draw.line(inner, col, (cx - arm, cy), (cx + arm, cy))
        pygame.draw.line(inner, col, (cx, cy - arm), (cx, cy + arm))


def draw_button(
    surf: pygame.Surface,
    rect: pygame.Rect,
    label: str,
    tint: tuple[int, int, int],
    *,
    enabled: bool = True,
    hovered: bool = False,
    pressed: bool = False,
    cost: str | None = None,
    shell_id: str | None = None,
) -> None:
    """A pressable moulding, tinted by the currency it spends.

    Colour carries meaning here rather than decorating: FEED is amber because
    feeding costs BITS, SHOP is phosphor because the shop costs ECHOES.
    """
    r = rect.move(0, 1) if (pressed and enabled) else rect
    sh = skinmod.get_shell(shell_id)
    if not enabled:
        # A disabled button's face is sh.lo, so the label has to be measured
        # against sh.lo and not sh.body: raw sh.text on sh.lo measures 1.05 Lc
        # on Seafoam and 1.17 on Bone, i.e. invisible.
        body, edge, fg = sh.lo, sh.body, ink.adapt(sh.text, sh.lo)
        hi = 0
    else:
        k = 0.46 if hovered else 0.34
        body = tuple(int(c * k) for c in tint)
        # The border is drawn onto the CASE, not onto the button, so it needs
        # the same treatment as any other ink: 9.6 Lc on silver as raw tint.
        edge = tint
        fg = tint
        hi = 120 if hovered else 96

    if enabled and not pressed:
        surf.blit(uikit.shadow((r.w, r.h), 12, 8, 150), (r.x - 8, r.y - 3))
    surf.blit(
        uikit.round_rect((r.w, r.h), 12, body,
                         gradient_to=tuple(int(c * 0.45) for c in body),
                         border=edge, top_highlight=hi),
        r.topleft,
    )
    lab = uikit.text(label, fg, theme.FONT_LABEL, bold=True)
    if cost is None:
        uikit.blit_centered(surf, lab, r)
    else:
        uikit.blit_centered(surf, lab, r, dx=-12)
        c = uikit.text(cost, fg, theme.FONT_CAPTION, bold=True)
        surf.blit(c, (r.centerx + 16, r.centery - c.get_height() // 2))


def draw_vent(surf: pygame.Surface, x: int, y: int,
              cols: int = 7, rows: int = 3, shell=None) -> None:
    """Speaker grille moulded into the case.

    Fills the dead space below the controls, which otherwise read as an
    unfinished slab, and is the detail that most cheaply says "object".
    """
    sh = shell or skinmod.SHELL_DEFAULT
    slot = sh.vent or sh.lo
    for r in range(rows):
        for c in range(cols):
            sx, sy = x + c * 9, y + r * 7
            pygame.draw.rect(surf, slot, (sx, sy, 5, 4), border_radius=2)
            pygame.draw.line(surf, sh.hi, (sx, sy + 4), (sx + 4, sy + 4))


def sample_bg(surf: pygame.Surface, rect: pygame.Rect) -> tuple:
    """The two extremes of what is actually behind a patch of lettering.

    Not the nominal case colour — the composited pixels. This is what makes the
    hard cases stop being hard: a translucent shell has a circuit board under
    the text, and Joy-Con's read-outs sit either side of the blue/red seam.
    Neither needs covering up: the internals are deterministic and cached, so
    they can simply be read back off the surface.

    Returns the 10th and 90th luminance percentiles, so one bright rivet does
    not drag the answer.
    """
    r = rect.clip(surf.get_rect())
    if r.w < 2 or r.h < 2:
        return ((128, 128, 128),)
    a = pygame.surfarray.array3d(surf.subsurface(r)).reshape(-1, 3)
    lum = a[:, 0] * 0.2126 + a[:, 1] * 0.7152 + a[:, 2] * 0.0722
    order = np.argsort(lum)
    lo = a[order[int(len(order) * 0.10)]]
    hi = a[order[int(len(order) * 0.90)]]
    return (tuple(int(v) for v in lo), tuple(int(v) for v in hi))


_INK: dict = {}


def ink_for(anchor, bgs, target=ink.TARGET_LC):
    """Cached solve. The case behind the text does not change between frames."""
    key = (anchor, bgs, target)
    got = _INK.get(key)
    if got is None:
        got = _INK[key] = ink.adapt(anchor, bgs, target=target)
    return got


def draw_ink_text(surf: pygame.Surface, pos, s: str, anchor, font: int,
                  *, bold: bool = True, target=ink.TARGET_LC):
    """Lettering pressed into the case, in an ink chosen for that case.

    Two jobs, split because they are genuinely separate. At this size letters
    are recognised by the LUMINANCE channel almost alone — the chromatic
    channels are low-pass and contribute nothing at the spatial frequency of a
    14px glyph. So the colour was never doing the reading:

      * the RELIEF does the reading. A dark tap up-left and a light tap
        down-right, both derived from the pixels behind the glyph, so the edge
        contrast is generated relative to whatever is back there. It cannot
        fail on a case it has never seen, which is exactly what a fixed ink
        does.
      * the INK does the naming. Gold means BITS, cyan means ECHOES. It is
        adapted in lightness only, holding hue and chroma, so it stays the same
        currency.

    An opaque plate behind all of this would solve the contrast ratio and ruin
    the object — a UI widget stuck onto a moulded case, in the one tone already
    used for the base, the screen recess, the vents and the disabled buttons.
    Nothing sits on top of the case.
    """
    x, y = pos
    probe = uikit.text(s, (255, 255, 255), font, bold=bold)
    bgs = sample_bg(surf, pygame.Rect(x - 1, y - 1,
                                      probe.get_width() + 3,
                                      probe.get_height() + 3))
    col = ink_for(tuple(anchor), bgs, target)
    dark, light = ink.relief(bgs[0] if len(bgs) == 1 else
                             tuple((a + b) // 2 for a, b in zip(*bgs)))
    # Order matters and is not decorative: shadow up-left then highlight
    # down-right reads as ENGRAVED. Swap them and the same two taps read as
    # raised, which fights the recessed screen beside it.
    surf.blit(uikit.text(s, dark, font, bold=bold), (x - 1, y - 1))
    surf.blit(uikit.text(s, light, font, bold=bold), (x + 1, y + 1))
    surf.blit(uikit.text(s, col, font, bold=bold), (x, y))
    return col


def draw_currency(surf: pygame.Surface, x: int, y: int, value: int,
                  label: str, col: tuple[int, int, int], shell=None) -> None:
    """Currency read-out, printed straight onto the case.

    The swatch stays CANONICAL gold or cyan on every case and is never adapted.
    It is a solid 12px shape, not a glyph, so it survives low contrast in a way
    letters do not — which lets it carry the whole semantic load and frees the
    numeral to be whatever lightness is actually readable.

    "Tolerates low contrast" is not "tolerates none", though: measured raw, the
    ECHOES swatch is **0.0 Lc** on Joy-Con and Seafoam — a cyan dot on cyan
    plastic, invisible. Contrast checks that look only at lettering never catch
    it.

    So the colour stays and the dot gets a seated rim, derived from the pixels
    behind it the same way the lettering's relief is. The dot is still
    canonical; it is a canonical dot with an edge, which is what a moulded
    indicator has anyway.
    """
    seat = pygame.Rect(x - 1, y + 5, 14, 14)
    rim = ink.relief(sample_bg(surf, seat)[0])[0]
    surf.blit(uikit.round_rect((12, 12), 6, col,
                               gradient_to=tuple(int(c * 0.4) for c in col),
                               border=None, top_highlight=140), (x, y + 6))
    nh = uikit.text(str(value), col, theme.FONT_TITLE, bold=True).get_height()
    ring = draw_ink_text(surf, (x + 18, y + 2), str(value), col,
                         theme.FONT_TITLE)
    # The caption is solved, not tweaked: lightening it toward white after the
    # contrast solve would mean the colour measured is not the colour drawn,
    # and on a pale case that lerp walks it into the background. Solved to a
    # HIGHER target than the numeral: 11px needs the help.
    draw_ink_text(surf, (x + 18, y + nh - 1), label, col,
                  theme.FONT_CAPTION, target=ink.TARGET_LC + 15)
    # Two rings: the outer one seats the dot against the case (guaranteed
    # contrast, derived from the background), the inner one ties it to its
    # numeral. Without the outer ring a cyan dot on cyan plastic has no edge
    # at all.
    pygame.draw.rect(surf, rim, seat, 1, border_radius=7)
    pygame.draw.rect(surf, ring, seat.inflate(2, 2), 1, border_radius=8)


def draw_sparkle(surf: pygame.Surface, shell, t: float,
                 suppress: bool = False) -> None:
    """The plating catching the light. Drawn LAST, and that is not cosmetic.

    `draw_ink_text` samples the composited surface to pick its ink and caches
    on what it sampled. If a glint landed under the read-out before the
    lettering was drawn, the sampled background would change every frame, the
    cache key with it, and the OkLCh solver would re-run its full sweep twice
    per frame forever. Drawing the sparkle after all lettering means the
    sampler never sees it, and the cache stays a cache.

    This is the only ambient animation in the chrome, and the chrome is
    otherwise deliberately static because this window sits on top of the user's
    real work. Plating that never catches the light does not read as plating,
    so the motion is rationed hard to stay near the spirit of that rule:

      * the sweep is present 1.6s in every 9-11s, absent 82% of the time, at a
        peak alpha of 24 — a modulation of an already bright surface, never a
        new object;
      * glints spawn 1.6 times a second across the whole case, at most three
        alive, and only on bevels, the screen lip and the screw bosses. An even
        scatter over the flat field is what makes a finish read as glitter;
      * nothing sparkles inside the screen. The pet is the subject.
    """
    if not getattr(shell, "metal", None) or suppress:
        return
    w, h = surf.get_size()
    face = pygame.Rect(BEZEL, BEZEL, w - BEZEL * 2, h - BEZEL * 2)
    sr = screen_rect()

    period = metalmod.SWEEP_PERIOD[shell.metal]
    phase = (t % period) / period
    if phase < 1.6 / period:
        band = metalmod.sweep(shell.metal, (w, h))
        k = phase / (1.6 / period)
        prev = surf.get_clip()
        surf.set_clip(face)
        surf.blit(band, (int(-band.get_width() + k * (w + band.get_width())),
                         -40))
        surf.set_clip(prev)

    pts = metalmod.edge_points(
        (w, h), sr, exclude=((14, 10, 150, 40), (w - 170, 10, 156, 40)))
    if not pts:
        return
    atlas = metalmod.atlas(shell.metal)
    slot = metalmod.LIFE / metalmod.MAX_LIVE
    for lane in range(metalmod.MAX_LIVE):
        # Deterministic from t: no per-frame RNG state, so a paused window and
        # a resumed one agree, and nothing accumulates.
        n = int((t + lane * slot) / (1.0 / metalmod.SPAWN_HZ))
        age = (t + lane * slot) % (1.0 / metalmod.SPAWN_HZ)
        if age > metalmod.LIFE:
            continue
        k = age / metalmod.LIFE
        seed = (n * 2654435761 + lane * 40503) & 0xFFFFFFFF
        px, py = pts[seed % len(pts)]
        arm = metalmod.GLINT_ARMS[(seed >> 8) % len(metalmod.GLINT_ARMS)]
        if k < 0.22:                       # bloom: light catches fast
            a, sc = k / 0.22, 0.30 + 0.70 * (k / 0.22)
        elif k < 0.40:                     # hold
            a, sc = 1.0, 1.0
        else:                              # and lingers as it goes
            a, sc = (1 - (k - 0.40) / 0.60) ** 2, 1.0 - 0.15 * (k - 0.40) / 0.60
        step = max(0, min(metalmod.ALPHA_STEPS - 1,
                          int(a * metalmod.ALPHA_STEPS) - 1))
        g = atlas[metalmod.GLINT_ARMS.index(arm)][step]
        if sc < 0.99:
            gw = max(1, int(g.get_width() * sc))
            g = pygame.transform.scale(g, (gw, gw))
        surf.blit(g, (px - g.get_width() // 2, py - g.get_height() // 2),
                  special_flags=pygame.BLEND_RGBA_ADD)
