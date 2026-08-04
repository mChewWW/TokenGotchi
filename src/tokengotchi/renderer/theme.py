"""Design tokens — the single source of truth for the game's visual language.

Every module that draws — `window.py`, `shop_panel.py`, `device.py` and the
rest — pulls its palette, spacing and corner radii from here rather than
declaring near-identical constants of its own. Studio UI reads as coherent
because everything is drawn from one small, deliberate set of values;
scattered magic numbers are what make an interface look assembled rather
than designed.

Nothing here draws. See `uikit.py` for the primitives that consume these.
"""
from __future__ import annotations

Color = tuple[int, int, int]

# ── Surfaces ────────────────────────────────────────────────────────────────
# A dark, cool base with a violet undertone. Each step up is a *lighter*
# surface, which is how elevation reads on dark UI.
#
# Chrome alone is a narrow band: fourteen tokens inside roughly **4.2 degrees
# of hue** is one colour with a brightness ramp, not a palette, and it puts
# something like 81% of the frame's coloured pixel energy into a single
# violet — which reads as boring and basic. The shell tokens below therefore
# introduce a second hue family, and the screen a third.
BG_VOID = (14, 12, 22)         # behind everything; the starfield sits on it
BG_BASE = (22, 19, 33)         # window background
SURFACE = (32, 28, 47)         # cards, HUD
SURFACE_RAISED = (43, 38, 62)  # buttons at rest
SURFACE_HOVER = (55, 49, 79)   # buttons under the cursor
SURFACE_SUNKEN = (18, 16, 28)  # wells, track backgrounds, disabled fills

# ── The shell (the device) ──────────────────────────────────────────────────
# A moulded handheld case. Warmer and lighter than the screen it surrounds, so
# the screen reads as a hole cut into an object rather than a panel painted on
# a background.
SHELL = (72, 58, 92)           # case body — warm and saturated enough not to
                               # read as flat grey plastic
SHELL_HI = (112, 94, 142)      # lit top edge / bevel
SHELL_LO = (30, 24, 40)        # case base, recess shadow
SHELL_TEXT = (146, 130, 178)   # silkscreen lettering on the case
SHELL_VENT = (46, 37, 60)      # speaker-grille slots

# ── The screen ──────────────────────────────────────────────────────────────
# A CRT panel. Green-black, not violet-black — the third hue family, and the
# thing that makes the pet look like it is being *displayed* rather than drawn.
SCREEN = (11, 22, 17)
SCREEN_EDGE = (6, 13, 10)
PHOSPHOR = (126, 246, 168)     # readout text and meters inside the screen
PHOSPHOR_DIM = (52, 128, 84)

# Scanlines. MEASURED, not chosen by eye: a 3px period aligns exactly with the
# sprite's 3x pixel grid and visibly greys the creature. 4px breaks that
# alignment. If PX_*_SCALE ever changes, re-measure before changing this.
SCANLINE_PERIOD = 4
SCANLINE_ALPHA = 22
GLARE_ALPHA = 16

# ── Borders ─────────────────────────────────────────────────────────────────
BORDER_SUBTLE = (52, 46, 76)
BORDER = (72, 64, 104)
BORDER_STRONG = (104, 92, 150)
BORDER_FOCUS = (150, 128, 235)

# ── Text ────────────────────────────────────────────────────────────────────
TEXT = (232, 228, 245)
TEXT_SECONDARY = (163, 154, 192)
TEXT_MUTED = (112, 104, 140)
TEXT_DISABLED = (78, 72, 100)
TEXT_ON_ACCENT = (18, 14, 28)

# ── Accents ─────────────────────────────────────────────────────────────────
ACCENT = (146, 122, 240)       # primary violet — focus, selection
ACCENT_DIM = (96, 80, 168)
BITS = (255, 206, 92)          # warm gold
BITS_DIM = (150, 118, 48)
ECHOES = (104, 198, 255)       # cool cyan
ECHOES_DIM = (52, 108, 148)
SUCCESS = (108, 220, 150)
DANGER = (238, 106, 106)

# ── Elevation ───────────────────────────────────────────────────────────────
# (y-offset, blur radius, alpha) — soft and low-contrast; hard black drop
# shadows are a hallmark of amateur UI.
SHADOW_CARD = (2, 6, 90)
SHADOW_PANEL = (6, 18, 150)
SCRIM_ALPHA = 172              # modal backdrop dim

# ── Spacing ─────────────────────────────────────────────────────────────────
# A 4pt scale. Every gap and pad in the UI must come from here.
SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_5 = 24
SPACE_6 = 32

# ── Radii ───────────────────────────────────────────────────────────────────
RADIUS_SM = 5
RADIUS_MD = 9
RADIUS_LG = 14
RADIUS_PILL = 999

# ── Type ramp ───────────────────────────────────────────────────────────────
# Named sizes, not raw ints at call sites.
FONT_CAPTION = 11
FONT_BODY = 13
FONT_LABEL = 14
FONT_READOUT = 15   # dense numeric tables: at 14 digit counters start to blur
FONT_TITLE = 17
FONT_DISPLAY = 22

# ── Motion ──────────────────────────────────────────────────────────────────
# Seconds. Nothing below ~0.13s: at 30fps that is under 4 frames and reads as
# a glitch rather than as motion.
DUR_INSTANT = 0.09
DUR_HOVER = 0.13
DUR_FAST = 0.16
DUR_PANEL_IN = 0.22
DUR_PANEL_OUT = 0.15       # closing is deliberately faster than opening
DUR_COUNTER = 0.45
DUR_STAGGER = 0.045        # per-row delay in a staggered reveal

# Global multiplier. Set to 0.0 to make every transition instant — the escape
# hatch if motion ever makes the app feel slow, and what lets the modal be
# inspected at its end state without waiting.
ANIM_SCALE = 1.0


def currency_color(currency: str, *, dim: bool = False) -> Color:
    """Accent for a currency id from the shop catalogue."""
    if currency == "bits":
        return BITS_DIM if dim else BITS
    return ECHOES_DIM if dim else ECHOES
