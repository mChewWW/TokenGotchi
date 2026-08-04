"""Ink — legible lettering on a case whose colour the player chose.

Eight purchasable cases, and text printed straight onto them. One hardcoded ink
cannot serve all eight: it measures 1.01:1 on Seafoam. An opaque plate behind
the text would fix the contrast, but a static border ruins the overall
aesthetic and the illusion of a moulded screen with it. So the text colour
changes per skin instead. This module is that, plus the part that makes it work.

THE FINDING THAT SHAPES EVERYTHING HERE. At this size, letters are recognised
almost entirely by the LUMINANCE channel. The two chromatic opponent channels
are low-pass and contribute nothing above ~2-4 cycles/degree, while reading
small type needs 18-30. So gold and cyan were never carrying legibility. They
carry IDENTITY — which currency this is — and nothing else.

That splits the job cleanly, and the split is the design:

    colour carries the meaning; geometry carries the legibility.

**Geometry.** Every glyph is debossed: a dark tap up-left, a light tap
down-right, both derived from the pixels actually behind it. Engraved text is
read as shadow and highlight, so its contrast is relative to its background BY
CONSTRUCTION and cannot fail the way a fixed ink fails. Real hardware's version
of this has a real weakness — a recess needs raking light, and on translucent
plastic the light leaking through fills it in — but we own the light source, so
we do not inherit it.

**Colour.** The ink is then adapted per case: hue and chroma held, lightness
moved, in OkLCh. Not HLS — HLS lightness lies (a blue at 50% looks far darker
than a yellow at 50%), so one target would need per-currency, per-skin magic
numbers. Not CIELAB either: it has a documented hue shift for blues in the
270-330 region, which is exactly where cyan lands once you push it. OkLCh holds
hue.

**Gold may be lightened freely and must never be darkened much.** Brown is not
a hue — it is dark, desaturated yellow-orange — so darkening gold does not dim
the currency, it renames it. Worse, the boundary moves with the surround: the
same swatch reads gold on a dark case and brown on a pale one. `L_FLOOR_WARM`
is the stop. Cyan has no equivalent trap and moves either way.

**Measured with APCA, not WCAG 2.** WCAG 2's ratio is luminance-only and is
known to misjudge mid-tone coloured pairs — which is all eight cases. Its
canonical failure is literally ours: to pass on white, orange must be darkened
until it is brown. That is an artefact of the metric, not a readability
requirement, and following it is how the gold gets ruined. APCA is
polarity-aware and accounts for thin letterforms. (APCA is NOT "WCAG 3" — that
section was cut from the draft in 2023. It is used here as the better
instrument, not as a standard we claim to meet.)
"""
from __future__ import annotations

import math

Color = tuple[int, int, int]

# ---------------------------------------------------------------- Oklab/OkLCh

def _to_linear(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(c: float) -> int:
    c = 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
    return max(0, min(255, int(round(c * 255.0))))


def _cbrt(x: float) -> float:
    """Signed cube root. `x ** (1/3)` raises on negatives; these go negative."""
    return math.copysign(abs(x) ** (1 / 3), x)


def rgb_to_oklch(rgb: Color) -> tuple[float, float, float]:
    r, g, b = (_to_linear(v) for v in rgb)
    l = _cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m = _cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s = _cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(a, bb), math.atan2(bb, a)


def oklch_to_rgb(L: float, C: float, H: float) -> Color:
    a, b = C * math.cos(H), C * math.sin(H)
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        _to_srgb(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
        _to_srgb(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
        _to_srgb(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s),
    )


def _in_gamut(L: float, C: float, H: float) -> bool:
    a, b = C * math.cos(H), C * math.sin(H)
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    for v in (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
              -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
              -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s):
        if v < -0.001 or v > 1.001:
            return False
    return True


def _fit(L: float, C: float, H: float) -> Color:
    """Hold hue and lightness; give up chroma only as far as the gamut demands.

    Chroma is the last thing to sacrifice: small glyphs need HIGH saturation,
    because the chromatic channels are low-resolution and a washed-out gold is
    both harder to identify AND no easier to read.
    """
    if _in_gamut(L, C, H):
        return oklch_to_rgb(L, C, H)
    lo, hi = 0.0, C
    for _ in range(20):
        mid = (lo + hi) / 2
        if _in_gamut(L, mid, H):
            lo = mid
        else:
            hi = mid
    return oklch_to_rgb(L, lo, H)


# ------------------------------------------------------------------- contrast

_APCA = dict(nBG=0.56, nTX=0.57, rTX=0.62, rBG=0.65,
             blkThrs=0.022, blkClmp=1.414, scale=1.14, offset=0.027,
             loClip=0.1, deltaYmin=0.0005)


def _apca_y(rgb: Color) -> float:
    y = (0.2126729 * (rgb[0] / 255.0) ** 2.4
         + 0.7151522 * (rgb[1] / 255.0) ** 2.4
         + 0.0721750 * (rgb[2] / 255.0) ** 2.4)
    if y < _APCA["blkThrs"]:
        y += (_APCA["blkThrs"] - y) ** _APCA["blkClmp"]
    return y


def apca(text: Color, bg: Color) -> float:
    """Lightness contrast, signed. Positive = dark text on light background.

    Not symmetric, unlike WCAG — swapping the arguments is a different figure,
    which is the whole point of a polarity-aware metric.
    """
    yt, yb = _apca_y(text), _apca_y(bg)
    if abs(yb - yt) < _APCA["deltaYmin"]:
        return 0.0
    if yb > yt:
        s = (yb ** _APCA["nBG"] - yt ** _APCA["nTX"]) * _APCA["scale"]
        return 0.0 if s < _APCA["loClip"] else (s - _APCA["offset"]) * 100
    s = (yb ** _APCA["rBG"] - yt ** _APCA["rTX"]) * _APCA["scale"]
    return 0.0 if s > -_APCA["loClip"] else (s + _APCA["offset"]) * 100


# ----------------------------------------------------------------- adaptation

TARGET_LC = 60.0        # spot-readable for a short glyph run
FLOOR_LC = 45.0         # below this the deboss is doing all the work

# Warm hues cross into brown when darkened. Measured against the anchor gold:
# below this Oklab L the swatch stops being named "gold" and starts being
# named "brown", and the boundary drifts UP against a pale surround.
L_FLOOR_WARM = 0.58
WARM_LO, WARM_HI = 0.9, 2.2   # OkLCh hue radians that behave like gold


def _is_warm(H: float) -> bool:
    return WARM_LO <= (H % (2 * math.pi)) <= WARM_HI


CHROMA_KEEP = 0.62      # identity dies before contrast does — see below
L_BAND = 0.30           # how far the ink may drift from the anchor lightness


def _worst(fg: Color, bgs) -> float:
    return min(abs(apca(fg, b)) for b in bgs)


def adapt(anchor: Color, bg, *, target: float = TARGET_LC) -> Color:
    """Move `anchor` in lightness only until it is readable on `bg`.

    `bg` is a colour, or several. Several is the honest case: a translucent
    shell has a circuit board composited under the lettering, and Joy-Con's
    read-outs straddle the seam between a blue half and a red half. Passing the
    dark and light extremes of what is actually behind the glyphs — rather than
    one nominal case colour — makes both of those fall out for free.

    Returns the anchor unchanged when it already clears the target — the three
    dark cases need no adaptation at all, and touching them would be a cost
    with no benefit.

    THE CHROMA FLOOR IS NOT AN OPTIMISATION, IT IS THE WHOLE GUARD. Without it
    this function is actively harmful, and measurably so: told to hit a
    contrast target on the pale cases with gold forbidden from darkening, it
    runs gold to the top of the lightness range, where the sRGB gamut has no
    chroma left to give. Both currencies solve to PURE WHITE on Atomic and
    Joy-Con. Perfect contrast, separation exactly 0.000, and the colour that
    tells you which currency you are looking at is gone.

    So chroma is a hard constraint and contrast is the objective, not the other
    way round. Where the two cannot both be had, contrast yields — because the
    relief underneath is already holding a floor, and an ink that is slightly
    hard to read still says GOLD, while a white one says nothing.
    """
    bgs = (bg,) if isinstance(bg[0], int) else tuple(bg)
    if _worst(anchor, bgs) >= target:
        return anchor

    L0, C, H = rgb_to_oklch(anchor)
    C0 = C
    floor = L_FLOOR_WARM if _is_warm(H) else 0.0
    keep = C0 * CHROMA_KEEP
    # A chroma floor alone does NOT contain this. Dark blue keeps its chroma
    # all the way down, so cyan happily solves to #000020 -- chromatic on
    # paper, and to the eye simply black. Identity needs a lightness band too.
    lo_L, hi_L = max(floor, L0 - L_BAND), min(1.0, L0 + L_BAND)

    best: Color = anchor
    best_lc = _worst(anchor, bgs)
    # Sweep rather than binary-search: contrast against a mid-tone background
    # is not monotonic in L. It falls to zero as the ink passes THROUGH the
    # background lightness and rises again on the far side, so a bisection can
    # converge on the wrong branch entirely.
    for i in range(101):
        L = i / 100.0
        if not (lo_L <= L <= hi_L):
            continue
        cand = _fit(L, C, H)
        if rgb_to_oklch(cand)[1] < keep:
            continue                      # washed out — not this currency any more
        lc = _worst(cand, bgs)
        if lc >= target:
            # First crossing wins: the smallest departure from the anchor that
            # works, so identity is disturbed as little as possible.
            # Overshooting to maximum contrast is how you get a near-black
            # "gold" that the player reads as brown.
            return cand
        if lc > best_lc + 1e-6:
            best, best_lc = cand, lc
    return best


def separation(a: Color, b: Color) -> float:
    """Perceptual distance between the two currency inks, in Oklab.

    The failure this guards against is specific and measured: adapt both
    anchors toward a contrast floor by lightness alone and gold and cyan
    converge — on the darkest case they come within a whisker of the project's
    own "these two colours are indistinguishable" threshold. Two currencies
    that look the same are worse than one that is slightly hard to read.
    """
    La, Ca, Ha = rgb_to_oklch(a)
    Lb, Cb, Hb = rgb_to_oklch(b)
    ax, ay = Ca * math.cos(Ha), Ca * math.sin(Ha)
    bx, by = Cb * math.cos(Hb), Cb * math.sin(Hb)
    return math.sqrt((La - Lb) ** 2 + (ax - bx) ** 2 + (ay - by) ** 2)


MIN_SEPARATION = 0.16


# --------------------------------------------------------------------- relief

MIN_RELIEF_LC = 11.0


def relief(bg: Color) -> tuple[Color, Color]:
    """The two taps that make a glyph read as pressed into the case.

    Derived from the background, so the pair is always lighter-than-here and
    darker-than-here whatever "here" happens to be. That is why this survives a
    case colour it has never seen.

    A FIXED lightness offset does not survive it. A flat ±0.20 is plenty on a
    mid-tone case and nothing at all on Graphite — the dark tap runs into the
    bottom of the range and the relief vanishes on the four darkest cases. The
    offset is therefore grown until each tap is actually visible against the
    case, rather than assumed to be.
    """
    L, C, H = rgb_to_oklch(bg)
    out = []
    for sign, chroma in ((-1, 0.85), (1, 0.70)):
        tap = _fit(max(0.0, min(1.0, L + sign * 0.20)), C * chroma, H)
        d = 0.20
        while abs(apca(tap, bg)) < MIN_RELIEF_LC and d < 0.75:
            d += 0.05
            nl = L + sign * d
            if not 0.0 <= nl <= 1.0:
                # Out of headroom on this side — take it from the other
                # direction rather than returning an invisible tap.
                nl = L - sign * d
            tap = _fit(max(0.0, min(1.0, nl)), C * chroma, H)
        out.append(tap)
    return out[0], out[1]


def legibility(fg: Color, bg: Color) -> float:
    """What the glyph actually delivers, ink and geometry together.

    Scoring the ink alone against the case understates every mid-tone shell,
    because it ignores the relief — which on those very shells is the thing
    doing the reading. The glyph's edges abut the two taps, so the contrast
    available to the eye is the best of the three boundaries, not just the one.
    """
    dark, light = relief(bg)
    return max(abs(apca(fg, bg)), abs(apca(fg, dark)), abs(apca(fg, light)))
