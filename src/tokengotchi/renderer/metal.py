"""Plated finishes — True Gold and True Silver.

METAL IS NOT A COLOUR, IT IS A LUMINANCE PATTERN. Fill a case with flat gold
and it reads as mustard; fill it with the ramp below and it reads as bullion.
The hue is nearly the same in both. Two facts carry the whole illusion:

* **Plastic is monotonic; metal is not.** A plastic case goes bright at the top
  and dark at the bottom, once. Metal has TWO bright zones with a dark core
  between them — the key-light specular and the environment bounce. That
  inversion is the strongest single tell and it is free in a flat renderer.
* **The rise is fast and the fall is slow.** The specular is reached in ~2% of
  the height and decays over ~13%. A symmetric gradient reads as an airbrush.

Measured range, darkest stop to brightest: gold 12.5:1, silver 11.9:1, against
a flat control of 1.0:1. Below about 8:1 both collapse back into paint.

THE STOPS ARE PLACED AGAINST THE DEVICE LAYOUT, NOT CHOSEN ABSTRACTLY. Two
zones carry lettering — the silkscreen at y18-31 and the currency read-out at
y376-410 — and both are deliberately flat mid-tone, with the bright bands put
where nothing is printed. This is load-bearing rather than tidy: with the
specular sitting on the read-out, the ink solver could only reach Lc 37-55,
under its own floor of 45. Aligned as below it reaches 67-84.

Gold and silver are also given DIFFERENT finishes, polished and brushed. Two
metals differing only in hue read as one material recoloured — a boring solid
colour with the hue slider moved. Polished gold because plated gold on real
hardware is a mirror; brushed silver because polished silver is colourless and
the grain is what proves it is metal.
"""
from __future__ import annotations

import math

import numpy as np
import pygame

from . import uikit

Color = tuple[int, int, int]

GOLD_STOPS = (
    # BRIGHT, and the brightness is not a preference — a dark core reads as
    # brown plastic, not as metal. Bottom out around (70,40,13) and the whole
    # case looks muddy and, to the eye, soft: a large dim smooth area is
    # indistinguishable from a low-resolution one.
    #
    # AND SMOOTH. Blurriness is not answered by hard 2px specular lines in the
    # ramp, however tempting the theory that a single-pixel edge is what the
    # eye reads as sharp. That theory is right about edges and wrong about this
    # surface: on a mirror finish such lines read as horizontal BANDING, itself
    # a classic low-resolution artefact, so the fix reproduces the complaint it
    # answers. Polished metal is a smooth continuous reflection. Detail belongs
    # in the grain, at a frequency too fine to band — see `_anisotropy`.
    (0.000, (206, 152, 62)),     # rolled top edge
    (0.030, (226, 172, 72)),     # SILKSCREEN ZONE — flat on purpose
    (0.055, (242, 192, 88)),
    (0.068, (255, 253, 236)),    # specular lip
    (0.076, (255, 232, 158)),
    (0.200, (214, 156, 56)),
    (0.420, (160, 106, 34)),     # core — lifted well clear of brown
    (0.550, (146, 94, 30)),
    (0.645, (226, 168, 62)),
    (0.690, (255, 246, 204)),    # second band, just under the screen
    (0.745, (252, 208, 110)),
    (0.840, (220, 162, 62)),     # CURRENCY ZONE — flat again
    (0.930, (208, 150, 56)),
    (1.000, (170, 116, 40)),
)

SILVER_STOPS = (
    (0.000, (108, 113, 123)),
    (0.030, (140, 145, 155)),
    (0.055, (152, 157, 166)),
    (0.068, (255, 255, 255)),
    (0.076, (222, 226, 233)),
    (0.200, (112, 118, 130)),
    (0.420, (58, 65, 80)),       # the ONLY blue in the ramp; push it into the
    (0.550, (48, 55, 70)),       # mids and silver becomes gunmetal
    (0.645, (132, 138, 150)),
    (0.690, (238, 242, 248)),
    (0.745, (186, 191, 200)),
    (0.840, (128, 134, 145)),
    (0.930, (118, 124, 135)),
    (1.000, (82, 88, 99)),
)

STOPS = {"gold": GOLD_STOPS, "silver": SILVER_STOPS}
GLINT_TINT = {"gold": (255, 250, 230), "silver": (255, 255, 255)}
FINISH = {"gold": "polished", "silver": "brushed"}
SWEEP_PERIOD = {"gold": 9.0, "silver": 11.0}

# Brushed silver's grain period. It does not share a factor with the sprite's
# 3x upscale, which is where moiré comes from: gcd(7,3)=1.
# Polished gold has no period at all -- see `_anisotropy` for why that is the
# whole point rather than an omission.
BRUSH_PERIOD = 7

_cache: dict = {}


def stop_at(metal: str, t: float) -> Color:
    """Sample the ramp. `ShellSkin.body/hi/lo` are all derived from this, so
    anything reading those three fields gets the ramp for free."""
    stops = STOPS[metal]
    t = max(0.0, min(1.0, t))
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t0 <= t <= t1:
            k = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(int(a + (b - a) * k) for a, b in zip(c0, c1))
    return stops[-1][1]


def _ramp_column(metal: str, h: int) -> np.ndarray:
    stops = STOPS[metal]
    ts = np.array([s[0] for s in stops], dtype=np.float32) * (h - 1)
    cols = np.array([s[1] for s in stops], dtype=np.float32)
    y = np.arange(h, dtype=np.float32)
    return np.stack([np.interp(y, ts, cols[:, c]) for c in range(3)], axis=1)


def _anisotropy(metal: str, w: int, h: int) -> np.ndarray:
    """The grain. Brushed is fine directional streaks; polished is broad bands.

    Returned as a signed additive field, so it modulates the ramp's lightness
    rather than tinting it — metal that shifts hue as it shades reads as
    oil-slick, not bullion.
    """
    rng = np.random.default_rng(hash(metal) & 0xFFFF)
    if FINISH[metal] == "brushed":
        # Coherent pulse plus per-row noise, then broken into segments so it
        # reads as grain rather than as scanlines.
        rows = (np.sin(np.arange(h) * (2 * math.pi / BRUSH_PERIOD)) * 0.55
                + rng.normal(0, 0.45, h))
        field = np.repeat(rows[:, None], w, axis=1) * 16.0
        gaps = rng.random((h, 1)) < 0.28
        field = np.where(gaps, field * 0.15, field)
        jitter = rng.normal(0, 0.25, (h, w))
        field = field + jitter * 6.0
    else:
        # POLISHED MEANS NO BANDING AT ALL. The obvious construction — a sum of
        # sines at period 23, plus a 3px roll-mark harmonic, on the reasoning
        # that polished metal shows broad soft bands — fails at 1:1. Every one
        # of those periodic terms reads as a horizontal stripe pattern, and
        # stripes are the single most recognisable signature of a
        # low-resolution image: lines in the texture itself, rather than a
        # smooth texture.
        #
        # A mirror has no periodic structure. Its detail is aperiodic
        # micro-pitting -- high enough frequency that no stripe can form, and
        # that is what supplies pixel-level detail without banding. So the
        # ONLY vertical variation left here is the ramp itself.
        field = rng.normal(0, 1.0, (h, w)) * 2.4                   # micro-pit
        # One very low-frequency horizontal term, or the surface reads as a
        # cylinder rather than a plate — the ramp varies in y alone. At period
        # 137 across a 356px case this is under three cycles: a gradient, not
        # a stripe.
        x = np.arange(w)[None, :]
        field = field + np.sin(x * (2 * math.pi / 137.0)) * 5.0
    return field


def face(metal: str, size: tuple[int, int]) -> pygame.Surface:
    """The plated face: ramp plus grain, built once and cached.

    This is the whole static cost of a metal shell — one surface, one blit.
    """
    key = ("face", metal, size)
    got = _cache.get(key)
    if got is not None:
        return got
    w, h = size
    arr = np.repeat(_ramp_column(metal, h)[:, None, :], w, axis=1)
    arr = arr + _anisotropy(metal, w, h)[:, :, None]
    surf = pygame.Surface(size).convert()
    pygame.surfarray.blit_array(
        surf, np.clip(arr, 0, 255).astype(np.uint8).transpose(1, 0, 2))
    _cache[key] = surf
    return surf


# ------------------------------------------------------------------- sparkle

GLINT_ARMS = (2, 3, 5, 7, 9)
ALPHA_STEPS = 6
LIFE = 0.55
SPAWN_HZ = 1.6
MAX_LIVE = 3


def _glint(arm: int, tint: Color) -> pygame.Surface:
    """A four-point star, drawn as pixels rather than scaled.

    At arm=1 this is literally a plus: five pixels. Larger sizes redraw the
    same shape — smoothscaling one rounds the tips off and turns a star into a
    blob, which is the difference between a glint and a smudge.
    """
    n = arm * 4 + 1
    c = n // 2
    s = pygame.Surface((n, n), pygame.SRCALPHA)
    r = max(1, int(arm * 0.5))
    bloom = pygame.Surface((n, n), pygame.SRCALPHA)
    pygame.draw.circle(bloom, (*tint, 66), (c, c), r * 2)
    s.blit(uikit._blur(bloom, 0.34), (0, 0))
    for i in range(1, arm * 2 + 1):
        a = int(255 * (1.0 - (i / (arm * 2 + 1)) ** 1.6))
        wide = i <= max(1, (arm * 2) // 3)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            px, py = c + dx * i, c + dy * i
            s.fill((*tint, a), (px, py, 1, 1))
            if wide:
                # The taper is what makes it a spike instead of a cross.
                s.fill((*tint, a // 2), (px + dy, py + dx, 1, 1))
                s.fill((*tint, a // 2), (px - dy, py - dx, 1, 1))
    for i in range(1, max(1, arm // 2) + 1):
        a = int(255 * 0.30 * (1.0 - i / (arm // 2 + 1)))
        for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            s.fill((*tint, a), (c + dx * i, c + dy * i, 1, 1))
    s.fill((*tint, 255), (c, c, 1, 1))
    return s


def atlas(metal: str) -> list[list[pygame.Surface]]:
    """5 sizes x 6 alpha steps = 30 sprites, built once.

    Quantising the life curve to six steps is what makes a glint a lookup
    instead of a per-frame redraw. At 0.55s that is one step per three frames,
    and the stepping is invisible under a blooming star.
    """
    key = ("atlas", metal)
    got = _cache.get(key)
    if got is not None:
        return got
    tint = GLINT_TINT[metal]
    out = []
    for arm in GLINT_ARMS:
        base = _glint(arm, tint)
        row = []
        for step in range(ALPHA_STEPS):
            s = base.copy()
            s.set_alpha(int(255 * (step + 1) / ALPHA_STEPS))
            row.append(s)
        out.append(row)
    _cache[key] = out
    return out


def edge_points(size: tuple[int, int], screen: pygame.Rect,
                exclude: tuple = ()) -> list:
    """Where light actually catches: bevels, the screen lip, the screw bosses.

    NEVER the flat field. An even scatter over an open surface reads as glitter
    or dust — it is the single clearest tell between a premium finish and a
    phone case from a service station. Real specular runs along geometry.
    """
    key = ("pts", size, tuple(screen), exclude)
    got = _cache.get(key)
    if got is not None:
        return got
    w, h = size
    pts = []
    for x in range(22, w - 22, 6):
        pts += [(x, 14), (x, h - 14)]
    for y in range(22, h - 22, 6):
        pts += [(14, y), (w - 14, y)]
    r = screen.inflate(24, 24)
    for x in range(r.left, r.right, 6):
        pts += [(x, r.top), (x, r.bottom)]
    for y in range(r.top, r.bottom, 6):
        pts += [(r.left, y), (r.right, y)]
    keep = [p for p in pts
            if 0 < p[0] < w and 0 < p[1] < h
            and not any(pygame.Rect(e).collidepoint(p) for e in exclude)
            and not screen.collidepoint(p)]
    _cache[key] = keep
    return keep


def sweep(metal: str, size: tuple[int, int]) -> pygame.Surface:
    """A soft diagonal band that crosses the case and is then gone.

    Present for 1.6s in every 9-11s — absent 82% of the time. Peak alpha 24: it
    is a lightness modulation of an already bright surface, never an added
    object. This window sits on top of whatever the user is actually doing, so
    ambient motion is rationed rather than decorated with.
    """
    key = ("sweep", metal, size)
    got = _cache.get(key)
    if got is not None:
        return got
    w, h = size
    band, diag = 96, int(math.hypot(w, h)) + 96
    s = pygame.Surface((band, diag), pygame.SRCALPHA)
    tint = GLINT_TINT[metal]
    for x in range(band):
        a = int(24 * math.sin(math.pi * x / band) ** 2)
        if a:
            s.fill((*tint, a), (x, 0, 1, diag))
    s = pygame.transform.rotate(uikit._blur(s, 0.5), -24)
    _cache[key] = s
    return s
