"""Screen skins — the display itself as a cosmetic surface.

The device metaphor makes the screen a thing you can own a different version
of. A skin is a bundle of values `device.py` already reads, plus two transforms
that make the weak ones worth buying.

**A skin is not a colour cast.** A merely tinted screen reads as "boring, solid
colour" and is not worth paying for. A real dot-matrix LCD or e-ink panel
*cannot represent* the pet's ~20 colours — it maps them onto its own few
shades. That reduction is the product.

Two gates, both enforced in code below, not left as documentation:

* **MoirÃ©.** A line period that is a multiple of the sprite's 3x upscale lands
  exactly on the pixel grid and greys the creature out. Measured, not guessed.
* **Legibility.** `draw_readout` shifts the meter colour as hunger drains. On a
  P3 amber phosphor the "getting hungry" amber collapses to 39.7 RGB distance
  from normal — a starving pet looks fed. Every skin therefore carries its OWN
  meter triple rather than borrowing fixed theme constants.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pygame

SPRITE_SCALE = 3          # sprites.PX_*_SCALE — patterns must not align with it

_BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6],
                   [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32) / 16.0

Color = tuple[int, int, int]


@dataclass(frozen=True)
class ScreenSkin:
    id: str
    name: str
    blurb: str
    base: Color                 # unlit glass
    edge: Color                 # vignette / well
    phosphor: Color             # readout text
    meter: tuple[Color, Color, Color]   # normal / warning / critical
    pattern: str = "scan"       # scan | grid | aperture | none
    period: int = 4
    alpha: int = 22
    glare: int = 16
    tint: tuple[int, int, int, int] | None = None
    background: bool = True
    palette: tuple[Color, ...] | None = None   # quantise target
    dither: float = 0.0
    grain: int = 0
    cost: int = 25
    rarity_locked: bool = False   # legendary: must be structural

    def __post_init__(self) -> None:
        if self.rarity_locked and not (self.palette or self.pattern not in
                                       ("scan", "none")):
            raise ValueError(
                f"skin {self.id!r}: a legendary screen must change more than "
                f"colour — set `palette` or a distinct `pattern`"
            )
        if self.pattern != "none" and self.period % SPRITE_SCALE == 0:
            raise ValueError(
                f"skin {self.id!r}: pattern period {self.period} is a multiple "
                f"of the sprite upscale {SPRITE_SCALE} — this moirÃ©s against "
                f"the pixel grid and greys the creature out"
            )
        d = _dist(self.meter[0], self.meter[1])
        if d < 70:
            raise ValueError(
                f"skin {self.id!r}: meter normal/warning are only {d:.1f} apart "
                f"— a starving pet would look fed"
            )


def _dist(a: Color, b: Color) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _rel_lum(c: Color) -> float:
    """WCAG relative luminance."""
    def ch(v: float) -> float:
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = c
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: Color, b: Color) -> float:
    """WCAG contrast ratio, 1.0 (identical) to 21.0 (black on white)."""
    la, lb = _rel_lum(a), _rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


MIN_CONTRAST = 3.0     # floor for bold UI text


# â”€â”€ The catalogue of skins â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
SKINS: tuple[ScreenSkin, ...] = (
    ScreenSkin(
        id="screen_p1", name="P1 Phosphor", blurb="Standard issue. Green on black.",
        base=(11, 22, 17), edge=(6, 13, 10), phosphor=(126, 246, 168),
        meter=((126, 246, 168), (255, 206, 92), (238, 106, 106)),
        cost=0,   # the default; owned from the start
    ),
    ScreenSkin(
        id="screen_amber", name="P3 Amber", blurb="Warm terminal glow.",
        base=(24, 15, 6), edge=(14, 8, 3), phosphor=(255, 176, 66),
        # Amber phosphor cannot use an amber warning. Shifted to magenta/red,
        # which is the whole reason meter colours are per-skin.
        meter=((255, 176, 66), (255, 104, 170), (255, 72, 72)),
        alpha=26, glare=18, tint=(255, 176, 66, 26), cost=200,
    ),
    ScreenSkin(
        id="screen_dmg", name="Dot-Matrix LCD", blurb="Four greens. Nothing else.",
        base=(155, 173, 90), edge=(120, 138, 70), phosphor=(35, 50, 24),
        meter=((35, 50, 24), (176, 82, 40), (150, 26, 26)),
        pattern="grid", alpha=34, glare=8, background=False,
        palette=((35, 50, 24), (78, 104, 54), (124, 152, 74), (170, 190, 108)),
        cost=450,
    ),
    ScreenSkin(
        id="screen_vfd", name="Vacuum Fluorescent", blurb="Hi-fi cyan, 1982.",
        base=(6, 16, 22), edge=(3, 9, 13), phosphor=(128, 246, 255),
        meter=((128, 246, 255), (255, 206, 92), (255, 96, 120)),
        period=5, alpha=20, glare=22, tint=(96, 220, 255, 22), cost=200,
    ),
    ScreenSkin(
        id="screen_grille", name="Aperture Grille", blurb="RGB phosphor stripes.",
        # Brighter base than the phosphor screens: a grille needs light behind
        # it to filter, and against near-black the stripes vanish entirely,
        # leaving something indistinguishable from P1.
        base=(26, 24, 34), edge=(12, 11, 17), phosphor=(240, 244, 255),
        meter=((240, 244, 255), (255, 196, 72), (255, 88, 88)),
        pattern="aperture", alpha=18, glare=24, cost=450,
    ),
    ScreenSkin(
        id="screen_scope", name="Oscilloscope",
        blurb="Vector traces on a long-persistence tube.",
        # Long-persistence green on near-black, with a graticule instead of
        # scanlines. Period 5 keeps it off the sprite's 3x grid.
        base=(5, 14, 9), edge=(3, 8, 5), phosphor=(150, 255, 170),
        meter=((150, 255, 170), (255, 214, 96), (255, 96, 96)),
        pattern="graticule", period=5, alpha=30, glare=14, cost=900,
        rarity_locked=True,
    ),
    ScreenSkin(
        id="screen_eink", name="E-Ink", blurb="Matte paper. No backlight.",
        base=(222, 219, 210), edge=(186, 183, 174), phosphor=(38, 36, 34),
        meter=((38, 36, 34), (168, 78, 30), (162, 28, 28)),
        pattern="none", period=0, alpha=0, glare=3, background=False,
        palette=((40, 38, 36), (104, 101, 96), (158, 155, 148), (206, 203, 195)),
        dither=34.0, grain=4, cost=900, rarity_locked=True,
    ),
    ScreenSkin(
        id="screen_true_silver", name="True Silver", blurb="Argent. Cold and exact.",
        base=(13, 16, 22), edge=(6, 8, 11), phosphor=(230, 238, 250),
        meter=((230, 238, 250), (255, 186, 66), (255, 74, 74)),
        pattern="scan", period=5, alpha=24, glare=30,
        palette=((32, 37, 47), (88, 96, 112), (160, 170, 186), (232, 239, 248)),
        dither=16.0, cost=450,
    ),
    ScreenSkin(
        id="screen_true_gold", name="True Gold", blurb="Every pixel struck in bullion.",
        base=(20, 13, 5), edge=(10, 6, 3), phosphor=(252, 214, 132),
        # The warning state CANNOT be amber on a gold phosphor -- it collapses
        # toward normal and a starving pet then looks fed. Hot magenta
        # instead: 129 apart from normal, against a floor of 70.
        meter=((252, 214, 132), (255, 108, 206), (255, 52, 52)),
        pattern="scan", period=5, alpha=24, glare=26,
        palette=((46, 27, 10), (118, 73, 22), (198, 143, 54), (252, 219, 142)),
        dither=18.0, cost=900, rarity_locked=True,
    ),
)

@dataclass(frozen=True)
class ShellSkin:
    """The case around the screen — the 'gameboy' body itself.

    Screens change what the pet is displayed ON. Shells change what the whole
    object IS. They are a separate slot for that reason: a player picking a
    green phosphor screen has said nothing about wanting a grey case.
    """
    id: str
    name: str
    blurb: str
    body: Color
    hi: Color                   # lit bevel / top edge
    lo: Color                   # base, and the recess the screen sits in
    text: Color                 # silkscreen lettering
    vent: Color | None = None   # speaker grille slots; None = derive from lo
    cost: int = 0
    translucent: bool = False   # draw internals through the case
    guts: float = 1.0           # how visible those internals are
    tinted_guts: bool = True    # does the plastic colour the machine?
    frosted: bool = True        # frosted diffuses; clear stays sharp
    body_right: Color | None = None   # asymmetric case, e.g. Joy-Con
    hi_right: Color | None = None
    metal: str | None = None          # "gold" | "silver" — a finish, not a fill
    rarity_locked: bool = False       # legendary: must be structural

    def __post_init__(self) -> None:
        """What a case must guarantee on its own, and nothing more.

        This gate deliberately does NOT assert `text` against `body`. The
        pixels actually drawn are `text` on `lo`, and measuring the wrong pair
        reports green on cases that are unreadable — 1.05 on Seafoam, 1.17 on
        Bone. A gate whose operands are not the operands the renderer uses is
        worse than no gate: it converts an open bug into a passing test.

        Nor does it assert `theme.BITS` and `theme.ECHOES`. Those are solved
        per case at draw time against the composited pixels — which a
        constructor cannot see and should not pretend to. That check lives in
        `scripts/verify_ink.py`, where it can sample a real frame. An assertion
        here pushes the design toward putting an opaque plate under the text,
        which ruins the illusion of a moulded screen: the pixels end up chosen
        to suit the test.

        What remains here is only what is knowable from the dataclass alone.

        `metal` counts toward the legendary rule, and that is a deliberate
        widening. The rule exists to keep out a case that is just another
        colour and nothing unique, so admitting anything new is the exact move
        the rule was written to prevent — unless the new case genuinely
        qualifies.

        It does. Metal is not a colour, it is a LUMINANCE PATTERN: a non-linear
        reflection ramp with a hard specular band. Fill a shape with flat gold
        and it reads as mustard; the ramp and the glints are what make it read
        as gold. So a metal finish changes how the surface is RENDERED, which
        is the same kind of claim `translucent` makes, and not the kind
        `body=(some other purple)` makes.
        """
        if self.rarity_locked and not (self.translucent or self.body_right
                                       or self.metal):
            raise ValueError(
                f"shell {self.id!r}: a legendary case must change more than "
                f"colour — set `translucent`, `body_right` or `metal`"
            )


SHELLS: tuple[ShellSkin, ...] = (
    ShellSkin(
        id="shell_amethyst", name="Amethyst", blurb="Standard issue.",
        body=(72, 58, 92), hi=(112, 94, 142), lo=(30, 24, 40),
        text=(157, 142, 185), cost=0,
    ),
    ShellSkin(
        id="shell_graphite", name="Graphite", blurb="Matte black, no nonsense.",
        body=(52, 52, 58), hi=(84, 84, 94), lo=(20, 20, 24),
        text=(128, 128, 140), cost=200,
    ),
    ShellSkin(
        id="shell_bone", name="Bone", blurb="Sun-yellowed since 1989.",
        body=(198, 190, 168), hi=(230, 224, 204), lo=(97, 92, 79),
        text=(108, 102, 86), cost=200,
    ),
    ShellSkin(
        id="shell_atomic", name="Atomic Purple", blurb="Tinted, and you can see through it.",
        # Reference #AD9CC1 is a pale, LOW-saturation lilac (19% sat, 76% val).
        # Anything near (118,96,158) -- 39% sat, 62% val, twice as saturated
        # and much darker -- stops reading as Atomic Purple and reads as
        # ordinary purple.
        body=(172, 154, 194), hi=(208, 194, 228), lo=(78, 60, 104),
        text=(46, 32, 66), cost=900, translucent=True, guts=1.0,
        rarity_locked=True,
        tinted_guts=True, frosted=True,
    ),
    ShellSkin(
        id="shell_clear", name="Clear", blurb="No tint at all. Every component on show.",
        # Barely tinted at all — the point is that you see the machine, not the
        # plastic. Atomic Purple is tinted see-through; this is see-through.
        # A real clear shell takes its colour FROM the board behind it, so the
        # plastic barely tints and the green PCB shows through almost raw.
        body=(206, 210, 212), hi=(236, 240, 242), lo=(89, 94, 97),
        text=(38, 44, 46), cost=900, translucent=True, guts=1.15,
        rarity_locked=True,
        tinted_guts=False, frosted=False,
    ),
    ShellSkin(
        id="shell_joycon", name="Joy-Con", blurb="Blue left, red right. Asymmetric on purpose.",
        # Deliberately two-tone. A single averaged purple would miss the whole
        # reference — the asymmetry IS the design.
        body=(0, 168, 221), hi=(84, 214, 255), lo=(20, 28, 40),
        text=(32, 70, 109), cost=450,
        body_right=(255, 60, 60), hi_right=(255, 122, 122),
    ),
    ShellSkin(
        id="shell_crimson", name="Crimson", blurb="Deep red, gloss finish.",
        body=(112, 40, 48), hi=(158, 66, 74), lo=(46, 16, 20),
        text=(226, 158, 162), cost=450,
    ),
    ShellSkin(
        id="shell_seafoam", name="Seafoam", blurb="Pastel, faintly medical.",
        body=(96, 148, 138), hi=(140, 194, 182), lo=(38, 62, 58),
        text=(23, 61, 51), cost=200,
    ),
    ShellSkin(
        id="shell_true_silver", name="True Silver", blurb="Argent. Brushed, and it catches the light.",
        # body/hi/lo are DERIVED from the ramp so every existing call site that
        # reads those three fields keeps working; the ramp is the real skin.
        body=(87, 93, 107), hi=(255, 255, 255), lo=(48, 55, 70),
        text=(44, 50, 62), vent=(96, 102, 116),
        cost=450, metal="silver",
    ),
    ShellSkin(
        id="shell_true_gold", name="True Gold", blurb="Struck, not painted.",
        body=(101, 61, 19), hi=(255, 247, 216), lo=(70, 40, 13),
        # Dark bronze, not pale gold. The case is bright, and the ink
        # solver holds an anchor within a lightness band -- give it a
        # near-white anchor on a near-white case and it has nowhere legal
        # to go. Silkscreen on real plated hardware is dark for the same
        # reason.
        text=(84, 52, 14), vent=(120, 78, 26),
        cost=900, metal="gold", rarity_locked=True,
    ),
)

_SHELL_BY_ID: dict[str, ShellSkin] = {s.id: s for s in SHELLS}
SHELL_DEFAULT = SHELLS[0]


def get_shell(shell_id: str | None) -> ShellSkin:
    """Resolve a shell id, tolerating unknown values from an old save."""
    return _SHELL_BY_ID.get(shell_id or "", SHELL_DEFAULT)


def purchasable_shells() -> tuple[ShellSkin, ...]:
    return tuple(s for s in SHELLS if s.cost > 0)


_BY_ID: dict[str, ScreenSkin] = {s.id: s for s in SKINS}
DEFAULT = SKINS[0]


def get(skin_id: str | None) -> ScreenSkin:
    """Resolve a skin id, falling back to the default.

    Tolerant by design: an unknown id in a save file (a skin removed in a later
    build) must degrade to the standard screen, never crash the app.
    """
    return _BY_ID.get(skin_id or "", DEFAULT)


def purchasable() -> tuple[ScreenSkin, ...]:
    return tuple(s for s in SKINS if s.cost > 0)


# â”€â”€ Transforms â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def quantise_layer(layer: pygame.Surface, palette, dither: float = 0.0
                   ) -> pygame.Surface:
    """Reduce a transparent content layer to a fixed palette, keeping alpha.

    Applied to the pet and the equipped background field ONLY, never to the
    composited frame: quantising the whole screen crushes the pet into the
    background because both map to the same bright level. A DMG draws sprites
    in its darker greens *on* a light field — the field is not quantised, it
    is the palette's lightest entry.
    """
    rgb = pygame.surfarray.array3d(layer).astype(np.float32)
    a = pygame.surfarray.array_alpha(layer).copy()
    lum = rgb[:, :, 0] * .299 + rgb[:, :, 1] * .587 + rgb[:, :, 2] * .114

    if dither:
        w, h = lum.shape
        tile = np.tile(_BAYER, (w // 4 + 1, h // 4 + 1))[:w, :h]
        lum = lum + (tile - 0.5) * dither

    n = len(palette)
    idx = np.clip((lum / 256.0 * n).astype(np.int32), 0, n - 1)
    pal = np.array(palette, dtype=np.uint8)

    out = pygame.Surface(layer.get_size(), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(out)[:] = pal[idx]
    pygame.surfarray.pixels_alpha(out)[:] = a
    return out


_grain_cache: dict = {}


def grain(size: tuple[int, int], amount: int) -> pygame.Surface:
    """Cached paper texture. Matte surfaces are not flat; a perfectly even
    off-white reads as a rectangle rather than paper."""
    key = (size, amount)
    got = _grain_cache.get(key)
    if got is not None:
        return got
    rng = np.random.default_rng(7)
    w, h = size
    n = rng.integers(0, max(1, amount), (w, h), dtype=np.uint8)
    s = pygame.Surface(size, pygame.SRCALPHA)
    px = pygame.surfarray.pixels3d(s)
    px[:, :, 0] = px[:, :, 1] = px[:, :, 2] = n
    pygame.surfarray.pixels_alpha(s)[:] = n * 6
    del px
    _grain_cache[key] = s
    return s
