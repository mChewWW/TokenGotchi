"""Sprite drawing module — all creature sprites drawn programmatically using pygame.draw.

No external image files are required. Each draw function takes a surface,
position, animation frame (0 or 1 for idle cycle), and optional flags.
"""
from __future__ import annotations

import math
import pygame

# Colour palette
CREATURE_BASE = (120, 220, 150)   # soft green
CREATURE_DARK = (60, 140, 80)     # darker green for shading
CREATURE_LIGHT = (160, 240, 180)  # lighter highlight green
EYE_WHITE = (240, 240, 245)       # white of eye
EYE_PUPIL = (25, 25, 35)          # pupil / near-black
EYE_SHINE = (255, 255, 255)       # eye highlight
CHEEK_COLOR = (220, 110, 130)     # rosy cheek pink
ACCENT_GOLD = (255, 200, 80)      # golden yellow (BITS)
ACCENT_BLUE = (100, 180, 255)     # sky blue (ECHOES)
EGG_BASE = (210, 210, 230)        # light lavender-white for egg
EGG_SHADE = (170, 170, 195)       # shading on egg
EGG_SPECKLE = (155, 155, 180)     # slightly darker for speckles
EGG_CRACK = (130, 130, 155)       # crack lines on egg
DORMANT_TINT = (80, 100, 140)     # blue-grey dormancy tint
HAT_COLOR = (22, 16, 10)          # dark top-hat colour

# Hunger-state colour palettes
# Sad state — muted, slightly grey-green
SAD_BASE = (90, 160, 110)
SAD_DARK = (50, 100, 65)

# Distressed state — jaundiced/grey-green, very sickly
DISTRESSED_BASE = (120, 145, 75)
DISTRESSED_DARK = (80, 100, 40)

# Horror state — corpse-pale, slightly yellow-grey like dead flesh
HORROR_BASE = (195, 185, 165)
HORROR_DARK = (30, 20, 15)
HORROR_VEIN = (60, 20, 30)      # dark red-purple veins
HORROR_DROOL = (180, 220, 180)  # pale drool

# Dying state — near-monochrome with red tint
DYING_BASE = (160, 100, 100)
DYING_DARK = (80, 40, 40)
HAT_BAND = (180, 140, 30)         # hat band gold stripe
HAT_BRIM = (32, 24, 14)           # slightly lighter hat brim
CROWN_COLOR = (255, 200, 80)      # golden crown
CROWN_HIGHLIGHT = (255, 230, 140) # crown highlight
CROWN_GEM = (255, 90, 110)        # gem colour on crown

# Gore palette
BLOOD_RED = (160, 20, 30)          # dark blood
BLOOD_BRIGHT = (200, 40, 50)       # fresh blood
BLOOD_DARK = (90, 10, 15)          # dried/dark blood
FLESH_PINK = (176, 96, 86)         # exposed flesh/muscle — raw, not rosy
FLESH_DARK = (132, 54, 50)         # deeper flesh
BONE_WHITE = (230, 220, 200)       # bone colour
VEIN_DARK = (60, 20, 40)           # dark vein/bruise
BRUISE = (80, 50, 100)             # bruise purple

# NOMI — uncanny valley humanoid
NOMI_SKIN = (235, 225, 210)        # healthy pale cream
NOMI_SKIN_DARK = (200, 185, 168)   # shadow/shading
NOMI_SKIN_LIGHT = (248, 242, 232)  # highlight
NOMI_IRIS = (140, 160, 185)        # glassy pale blue-grey iris
NOMI_PUPIL = (20, 18, 22)          # near-black pupil
NOMI_LIP = (195, 155, 145)         # lip colour
NOMI_TEETH = (245, 243, 238)       # too-white teeth
NOMI_HAIR = (55, 45, 38)           # dark brown hair
NOMI_SHIRT = (100, 120, 160)       # shirt colour

# NOMI hunger states
NOMI_SAD_SKIN = (210, 198, 185)    # slightly greyer
NOMI_DIST_SKIN = (185, 175, 155)   # sallow, jaundiced tinge
NOMI_HORROR_SKIN = (215, 205, 190) # too smooth, waxy — corpse pallor
NOMI_DYING_SKIN = (175, 165, 152)  # ashen

# ── Pixel-art creature ──────────────────────────────────────────────────────
# True pixel art: painted on a small low-res canvas then integer nearest-scaled.
# Limited, deliberate palette. Healthy = purely cute chibi.
PX_ADULT_W = 32          # low-res canvas width (logical pixels)
PX_ADULT_H = 36          # low-res canvas height
PX_ADULT_SCALE = 3       # integer upscale → 96×108, fits the 100×110 adult area

PX_BABY_W = 26           # baby canvas — rounder, bigger head chibi
PX_BABY_H = 30
PX_BABY_SCALE = 3        # → 78×90, fits the 80×90 baby area

PX_SKIN = (238, 205, 178)      # warm cream skin
PX_SKIN_SH = (206, 168, 142)   # skin shadow
PX_SKIN_HI = (250, 228, 205)   # skin highlight
PX_HAIR = (74, 54, 46)         # dark brown hair
PX_HAIR_HI = (104, 78, 66)     # hair highlight
PX_EYE_W = (250, 250, 252)     # eye white / catchlight
PX_EYE_D = (52, 44, 60)        # big cute pupil
PX_CHEEK = (240, 150, 150)     # rosy blush
PX_MOUTH = (170, 96, 92)       # mouth
PX_SHIRT = (112, 162, 210)     # friendly blue shirt
PX_SHIRT_SH = (84, 130, 182)   # shirt shadow
PX_SHOE = (92, 66, 58)         # little shoes
PX_OUTLINE = (44, 32, 46)      # soft dark silhouette outline

# Per-state skin (abrupt palette swaps — the horror storytelling)
PX_SKIN_SAD = (206, 186, 170)    # drained, greyer
PX_SKIN_SICK = (178, 158, 144)   # dry parchment — starved, NOT olive/jaundiced
PX_SKIN_CORPSE = (174, 170, 166) # waxy grey-ivory corpse pallor
PX_SKIN_DEAD = (150, 138, 146)   # cold ashen grey-violet
PX_ROT = (96, 110, 74)           # greenish rot patch
PX_ROT_DK = (66, 78, 50)         # deep rot
PX_SOCKET = (18, 12, 18)         # hollow eye socket black
PX_BONE = (238, 230, 208)        # bone / rib showing through skin
PX_BONE_SH = (150, 140, 118)     # shaded underside of a bone
PX_BRAIN = (206, 138, 150)       # exposed brain (pinkish grey)
PX_BRAIN_SH = (168, 96, 112)     # brain fold shadow
PX_SKULL = (224, 214, 196)       # cracked skull bone rim

# Dormancy blend factor (0.0 = no tint, 1.0 = full tint)
DORMANT_BLEND = 0.55


def _hunger_state(hunger: float) -> str:
    """Return hunger state string from 0-100 float."""
    if hunger >= 75:
        return "healthy"
    if hunger >= 50:
        return "sad"
    if hunger >= 25:
        return "distressed"
    if hunger >= 10:
        return "horror"
    return "dying"


def _tint_color(color: tuple[int, int, int], tint: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """Blend color toward tint by factor (0.0–1.0)."""
    r = int(color[0] * (1 - factor) + tint[0] * factor)
    g = int(color[1] * (1 - factor) + tint[1] * factor)
    b = int(color[2] * (1 - factor) + tint[2] * factor)
    return (r, g, b)


def _dormant_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    """Apply dormancy blue-grey tint to a colour."""
    return _tint_color(color, DORMANT_TINT, DORMANT_BLEND)


def _draw_top_hat(surface: pygame.Surface, cx: int, head_top: int) -> None:
    """A top hat, drawn on the creature's own pixel grid.

    Two things decide whether this reads as a hat at all, both structural
    rather than stylistic:

    1. **Proportion.** A square crown (say 24x26) reads as a lump. A top hat
       reads as a top hat because the crown is markedly TALLER than it is
       wide; this one is 21x33, i.e. 1.6:1.
    2. **Resolution.** Drawn in 1px display units with 1px highlight lines, it
       would sit on a creature made of chunky 3px blocks. Smooth detail next
       to pixel art reads as a sticker from another game.

    Everything here is therefore snapped to `PX_ADULT_SCALE` blocks so the hat
    is made of the same pixels as the head it sits on.
    """
    px = PX_ADULT_SCALE                      # one sprite pixel, in display px

    def block(bx: int, by: int, bw: int, bh: int, color) -> None:
        """One rectangle measured in SPRITE pixels, not display pixels."""
        pygame.draw.rect(surface, color,
                         (cx + bx * px, head_top + by * px, bw * px, bh * px))

    # Crown — 7 sprite-px wide, 11 tall. Taller than wide is the whole read.
    block(-3, -12, 7, 10, HAT_COLOR)
    # Lit left face and shaded right, so the cylinder has a form
    block(-3, -12, 1, 10, (58, 44, 30))
    block(3, -12, 1, 10, (18, 13, 8))
    # Slight dome on the crown top rather than a hard flat edge
    block(-2, -13, 5, 1, HAT_COLOR)
    block(-2, -13, 4, 1, (58, 44, 30))

    # Band, sitting just above the brim
    block(-3, -4, 7, 2, HAT_BAND)
    block(-3, -4, 7, 1, (210, 170, 70))

    # Brim — 11 wide, 2 tall, wider than the crown on both sides
    block(-5, -2, 11, 2, HAT_BRIM)
    block(-5, -2, 11, 1, (52, 40, 24))       # lit upper surface
    block(-5, -1, 11, 1, (14, 10, 6))        # shadow underside
    # Turned-up tips, the detail that stops it reading as a plank
    block(-6, -2, 1, 1, HAT_BRIM)
    block(5, -2, 1, 1, HAT_BRIM)


def _hat_block(surface, cx, head_top, bx, by, bw, bh, color):
    """One rectangle measured in SPRITE pixels, relative to the head top.

    Every hat is built from these so headwear sits on the same grid as the
    creature. Smooth 1px detail beside chunky 3px pixels reads as a sticker
    from another game.
    """
    px = PX_ADULT_SCALE
    pygame.draw.rect(surface, color,
                     (cx + bx * px, head_top + by * px, bw * px, bh * px))


def _draw_cap(surface: pygame.Surface, cx: int, head_top: int) -> None:
    """Ball cap, worn backwards — the peak points behind."""
    b = lambda *a: _hat_block(surface, cx, head_top, *a)
    crown, shade, band = (58, 96, 168), (40, 70, 128), (228, 232, 240)
    b(-4, -2, 9, 4, crown)
    b(-4, -2, 9, 1, (86, 128, 206))      # lit dome
    b(-3, -3, 7, 1, crown)
    b(2, -2, 3, 4, shade)                # right side in shadow
    b(-4, 2, 9, 1, band)                # brow band
    b(4, -1, 3, 2, shade)                # peak, turned backwards
    b(-1, -3, 2, 1, (228, 232, 240))     # button


def _draw_beanie(surface: pygame.Surface, cx: int, head_top: int) -> None:
    """Knitted beanie with a folded brim and a bobble."""
    b = lambda *a: _hat_block(surface, cx, head_top, *a)
    wool, dark, bob = (176, 76, 96), (138, 54, 74), (240, 214, 222)
    b(-4, -3, 9, 5, wool)
    b(-3, -4, 7, 1, wool)
    b(2, -3, 3, 5, dark)                 # shaded right
    for i in range(-4, 5, 2):            # knit ribbing
        b(i, -5, 1, 3, dark)
    b(-5, 2, 11, 2, wool)               # folded brim
    b(-5, 2, 11, 1, (206, 106, 126))
    b(-1, -6, 2, 2, bob)                 # bobble


def _draw_wizard(surface: pygame.Surface, cx: int, head_top: int) -> None:
    """Tall conical hat, drooping slightly, with stars."""
    b = lambda *a: _hat_block(surface, cx, head_top, *a)
    cloth, dark, star = (74, 56, 132), (52, 38, 98), (255, 226, 120)
    for i, (w, y) in enumerate(((1, -13), (2, -12), (3, -10), (4, -8),
                                (5, -6), (6, -4), (7, -2), (8, 0))):
        b(-w // 2 - 1, y, w, 2, cloth)
    b(1, -10, 2, 10, dark)               # shaded flank
    b(-6, 1, 13, 2, cloth)              # wide brim
    b(-6, 1, 13, 1, (98, 76, 166))
    b(-1, -9, 1, 1, star)               # stars
    b(1, -5, 1, 1, star)
    b(-3, -3, 1, 1, star)


def _draw_halo(surface: pygame.Surface, cx: int, head_top: int) -> None:
    """A floating ring. Nothing touches the head — that is the joke."""
    b = lambda *a: _hat_block(surface, cx, head_top, *a)
    gold, glow = (255, 220, 96), (255, 246, 190)
    b(-4, -6, 9, 1, gold)
    b(-5, -5, 1, 1, gold)
    b(5, -5, 1, 1, gold)
    b(-4, -4, 9, 1, gold)
    b(-3, -6, 3, 1, glow)                # highlight on the near edge
    b(-3, -4, 2, 1, (214, 174, 56))      # underside in shadow


def _draw_crown(surface: pygame.Surface, cx: int, head_top: int) -> None:
    """Draw a proper pixel-art crown above the creature's head."""
    crown_w = 36
    base_h = 7
    crown_x = cx - crown_w // 2
    crown_base_y = head_top + 2  # sits just at top of head

    # Crown base band
    pygame.draw.rect(surface, CROWN_COLOR, (crown_x, crown_base_y - base_h, crown_w, base_h), border_radius=2)
    # Highlight on crown base
    pygame.draw.rect(surface, CROWN_HIGHLIGHT, (crown_x + 1, crown_base_y - base_h, crown_w - 2, 2), border_radius=2)

    # Five crown points via polygons
    spike_ys = [crown_base_y - base_h - 12,  # tall middle
                crown_base_y - base_h - 9,   # medium left & right of mid
                crown_base_y - base_h - 6]   # short outer two

    # Left outer spike
    pygame.draw.polygon(surface, CROWN_COLOR, [
        (crown_x, crown_base_y - base_h),
        (crown_x + 5, spike_ys[2]),
        (crown_x + 10, crown_base_y - base_h),
    ])
    # Left-middle spike
    pygame.draw.polygon(surface, CROWN_COLOR, [
        (crown_x + 7, crown_base_y - base_h),
        (crown_x + 13, spike_ys[1]),
        (crown_x + 19, crown_base_y - base_h),
    ])
    # Centre spike (tallest)
    pygame.draw.polygon(surface, CROWN_COLOR, [
        (crown_x + 13, crown_base_y - base_h),
        (cx, spike_ys[0]),
        (crown_x + 23, crown_base_y - base_h),
    ])
    # Right-middle spike
    pygame.draw.polygon(surface, CROWN_COLOR, [
        (crown_x + 17, crown_base_y - base_h),
        (crown_x + 23, spike_ys[1]),
        (crown_x + 29, crown_base_y - base_h),
    ])
    # Right outer spike
    pygame.draw.polygon(surface, CROWN_COLOR, [
        (crown_x + 26, crown_base_y - base_h),
        (crown_x + 31, spike_ys[2]),
        (crown_x + 36, crown_base_y - base_h),
    ])

    # Gems on the band
    gem_y = crown_base_y - base_h // 2
    pygame.draw.circle(surface, CROWN_GEM, (crown_x + 6, gem_y), 2)
    pygame.draw.circle(surface, CROWN_GEM, (cx, gem_y), 2)
    pygame.draw.circle(surface, CROWN_GEM, (crown_x + crown_w - 6, gem_y), 2)
    # Gem shine dots
    pygame.draw.circle(surface, (255, 200, 200), (crown_x + 6, gem_y - 1), 1)
    pygame.draw.circle(surface, (255, 200, 200), (cx, gem_y - 1), 1)
    pygame.draw.circle(surface, (255, 200, 200), (crown_x + crown_w - 6, gem_y - 1), 1)


def _draw_eye(surface: pygame.Surface, ex: int, ey: int, radius: int, squint: bool, dormant: bool) -> None:
    """Draw a detailed eye with white, pupil, shine. squint=True for frame-1 blink."""
    white = _dormant_color(EYE_WHITE) if dormant else EYE_WHITE
    pupil = _dormant_color(EYE_PUPIL) if dormant else EYE_PUPIL
    shine = EYE_SHINE  # shine stays bright even when dormant

    # Eye white
    pygame.draw.circle(surface, white, (ex, ey), radius)
    # Pupil
    pygame.draw.circle(surface, pupil, (ex, ey + 1), max(1, radius - 2))
    # Shine dot (upper-right of eye)
    pygame.draw.circle(surface, shine, (ex + max(1, radius // 2), ey - max(1, radius // 2)), max(1, radius // 3))

    # Eyelid line (blink-squint on frame 1)
    if squint:
        # Draw a thin dark arc across top half to simulate squinting
        eyelid_rect = (ex - radius, ey - radius, radius * 2, radius * 2)
        pygame.draw.arc(surface, pupil, eyelid_rect, math.pi * 0.1, math.pi * 0.9, max(2, radius // 2))


def _draw_zzz(surface: pygame.Surface, x: int, y: int, font: pygame.font.Font | None = None) -> None:
    """Draw floating Zzz text using simple line art if no font available."""
    # We'll draw simple pixel "Z" shapes manually in varying sizes
    zzz_positions = [
        (x + 10, y + 0, 10),    # right, high
        (x - 2, y + 10, 7),     # left, mid
        (x + 14, y + 18, 6),    # right, low
    ]
    zzz_color = (140, 160, 210)  # muted blue-grey for Zzz
    for zx, zy, size in zzz_positions:
        # Top horizontal line
        pygame.draw.line(surface, zzz_color, (zx, zy), (zx + size, zy), 1)
        # Diagonal
        pygame.draw.line(surface, zzz_color, (zx + size, zy), (zx, zy + size), 1)
        # Bottom horizontal line
        pygame.draw.line(surface, zzz_color, (zx, zy + size), (zx + size, zy + size), 1)


def draw_egg(surface: pygame.Surface, x: int, y: int, frame: int, dormant: bool) -> None:
    """Draw an egg sprite as true pixel art. 80×80 drawing area at (x, y)."""
    W, H, S = 24, 26, 3  # → 72×78, fits the 80×80 area
    canvas = pygame.Surface((W, H), pygame.SRCALPHA)

    base = _dormant_color(EGG_BASE) if dormant else EGG_BASE
    shade = _dormant_color(EGG_SHADE) if dormant else EGG_SHADE
    speckle = _dormant_color(EGG_SPECKLE) if dormant else EGG_SPECKLE
    crack = _dormant_color(EGG_CRACK) if dormant else EGG_CRACK
    shine = _dormant_color((235, 235, 250)) if dormant else (235, 235, 250)

    def row(yy, x0, x1, c):
        if x1 >= x0:
            pygame.draw.rect(canvas, c, (x0, yy, x1 - x0 + 1, 1))

    def dot(xx, yy, c):
        if 0 <= xx < W and 0 <= yy < H:
            canvas.set_at((xx, yy), c)

    b = 1 if frame == 1 else 0

    # Egg silhouette — narrow top, round bottom
    egg_rows = {
        2: (10, 13), 3: (9, 14), 4: (8, 15), 5: (7, 16), 6: (7, 16),
        7: (6, 17), 8: (6, 17), 9: (5, 18), 10: (5, 18), 11: (4, 19),
        12: (4, 19), 13: (4, 19), 14: (4, 19), 15: (4, 19), 16: (4, 19),
        17: (5, 18), 18: (5, 18), 19: (6, 17), 20: (7, 16), 21: (9, 14),
    }
    for yy, (x0, x1) in egg_rows.items():
        row(yy + b, x0, x1, base)
    # Shading down the lower-right
    for yy in range(11, 20):
        x0, x1 = egg_rows[yy]
        row(yy + b, x1 - 2, x1, shade)
    # Highlight top-left
    row(4 + b, 9, 11, shine)
    dot(8, 6 + b, shine); dot(9, 5 + b, shine)

    # Speckles
    for sx, sy in [(8, 9), (15, 12), (7, 15), (13, 17), (11, 7), (16, 15)]:
        dot(sx, sy + b, speckle)

    # Crack — zig-zag across the middle
    crack_pts = [(7, 12), (9, 11), (10, 13), (12, 12), (14, 14), (16, 13)]
    for cxp, cyp in crack_pts:
        dot(cxp, cyp + b, crack)

    scaled = pygame.transform.scale(canvas, (W * S, H * S))
    blit_x = x + (80 - W * S) // 2
    blit_y = y + (80 - H * S) // 2
    surface.blit(scaled, (blit_x, blit_y))

    if dormant:
        _draw_zzz(surface, blit_x + W * S - 8, blit_y + 2)






def _nomi_skin_for_state(state: str, dormant: bool) -> tuple[tuple, tuple, tuple]:
    """Return (skin, skin_dark, skin_light) for the given NOMI hunger state."""
    if dormant:
        skin = _dormant_color(NOMI_SKIN)
        dark = _dormant_color(NOMI_SKIN_DARK)
        light = _dormant_color(NOMI_SKIN_LIGHT)
    elif state == "healthy":
        skin = NOMI_SKIN
        dark = NOMI_SKIN_DARK
        light = NOMI_SKIN_LIGHT
    elif state == "sad":
        skin = NOMI_SAD_SKIN
        dark = _tint_color(NOMI_SKIN_DARK, (150, 145, 138), 0.3)
        light = _tint_color(NOMI_SKIN_LIGHT, (200, 198, 192), 0.2)
    elif state == "distressed":
        skin = NOMI_DIST_SKIN
        dark = _tint_color(NOMI_SKIN_DARK, (140, 132, 115), 0.4)
        light = _tint_color(NOMI_SKIN_LIGHT, (195, 190, 178), 0.25)
    elif state == "horror":
        skin = NOMI_HORROR_SKIN
        dark = _tint_color(NOMI_SKIN_DARK, (160, 150, 135), 0.3)
        light = (252, 250, 246)  # too bright — waxy
    else:  # dying
        skin = NOMI_DYING_SKIN
        dark = _tint_color(NOMI_SKIN_DARK, (130, 122, 108), 0.5)
        light = _tint_color(NOMI_SKIN_LIGHT, (175, 168, 155), 0.4)
    return skin, dark, light


def _draw_nomi_eye(
    surface: pygame.Surface,
    ex: int,
    ey: int,
    sclera_r: int,
    iris_r: int,
    pupil_r: int,
    iris_offset_x: int = 0,
    blink: bool = False,
    half_closed: bool = False,
    dormant: bool = False,
) -> None:
    """Draw a NOMI eye — uncanny valley style with glassy iris and doll-like gaze.

    iris_offset_x: shift iris/pupil toward nose (positive = toward nose from left eye).
    """
    white = _dormant_color(EYE_WHITE) if dormant else EYE_WHITE
    iris_col = _dormant_color(NOMI_IRIS) if dormant else NOMI_IRIS
    pupil_col = _dormant_color(NOMI_PUPIL) if dormant else NOMI_PUPIL

    # Sclera
    pygame.draw.circle(surface, white, (ex, ey), sclera_r)
    # Iris (slightly pale blue-grey — unsettling)
    ix = ex + iris_offset_x
    pygame.draw.circle(surface, iris_col, (ix, ey), iris_r)
    # Pupil
    pygame.draw.circle(surface, pupil_col, (ix, ey), pupil_r)
    # Catchlight — upper right of iris
    cl_x = ix + max(1, iris_r // 2)
    cl_y = ey - max(1, iris_r // 2)
    pygame.draw.circle(surface, (255, 255, 255), (cl_x, cl_y), max(1, pupil_r // 2))

    # Eyelid — blink or half-closed
    if blink:
        # Thin dark line across top half — watching you
        eyelid_rect = (ex - sclera_r, ey - sclera_r, sclera_r * 2, sclera_r * 2)
        pygame.draw.arc(surface, pupil_col, eyelid_rect, math.pi * 0.15, math.pi * 0.85, max(2, sclera_r // 2))
    elif half_closed:
        # Eyelid at halfway point — heavy, still watching
        lid_y = ey - sclera_r // 2
        pygame.draw.ellipse(
            surface, _dormant_color(NOMI_SKIN) if dormant else NOMI_SKIN,
            (ex - sclera_r, ey - sclera_r, sclera_r * 2, sclera_r),
        )
        # Keep pupil visible below lid
        pygame.draw.circle(surface, pupil_col, (ix, ey), pupil_r)


def draw_nomi_baby(
    surface: pygame.Surface,
    x: int,
    y: int,
    frame: int,
    dormant: bool,
    hunger: float = 100.0,
) -> None:
    """Draw baby — true pixel-art chibi. 80×90 drawing area at (x, y)."""
    state = "healthy" if dormant else _hunger_state(hunger)
    draw_px_baby(surface, x, y, frame, dormant, state)
    return


def _px_tint(color: tuple[int, int, int], dormant: bool) -> tuple[int, int, int]:
    """Dormancy tint passthrough for the pixel-art palette."""
    return _dormant_color(color) if dormant else color


# Per-state (shadow, highlight) blend strength. A flat ramp cannot sculpt bone:
# at 3 display-pixels per logical pixel the only modelling that survives is a
# hard value step, so the starved states get a much deeper shadow and — for
# distressed — a brighter highlight, so taut skin over bone reads as taut.
PX_SKIN_RAMP = {
    "healthy": (0.28, 0.30),
    "sad": (0.28, 0.30),
    "distressed": (0.46, 0.38),
    "horror": (0.44, 0.26),
    "dying": (0.50, 0.14),
}
PX_SHADOW_TINT = (34, 26, 38)      # cool shadow target
PX_HILIGHT_TINT = (255, 252, 240)  # warm highlight target


def _px_skin_for_state(state: str, dormant: bool) -> tuple:
    """Return (skin, skin_sh, skin_hi) pixel palette for a hunger state."""
    if dormant or state == "healthy":
        base = PX_SKIN
    elif state == "sad":
        base = PX_SKIN_SAD
    elif state == "distressed":
        base = PX_SKIN_SICK
    elif state == "horror":
        base = PX_SKIN_CORPSE
    else:  # dying
        base = PX_SKIN_DEAD
    base = _px_tint(base, dormant)
    sh_f, hi_f = PX_SKIN_RAMP["healthy" if dormant else state]
    sh = _tint_color(base, PX_SHADOW_TINT, sh_f)
    hi = _tint_color(base, PX_HILIGHT_TINT, hi_f)
    return base, sh, hi


def _px_skeletal_torso(row, dot, b, body_rows, inset, skin, skin_sh, spec) -> None:
    """Paint a bare, emaciated ribcage over the torso rows.

    Shared by distressed / horror / dying so starvation reads the same way at
    every stage past the halfway mark — only the wounds painted on top differ.
    An intact shirt on horror or dying would make them read as *better fed*
    than distressed, which inverts the whole progression.

    At three display pixels per logical pixel, hue contributes almost nothing;
    a skeleton reads because a bright bone stripe sits against a near-black
    intercostal void. ``spec`` carries the per-form geometry, already offset
    for ``inset`` by the caller.
    """
    skin_deep = _tint_color(skin_sh, PX_SHADOW_TINT, 0.45)
    skin_void = _tint_color(skin_deep, PX_SHADOW_TINT, 0.40)

    # Bare skin first — for distressed the envelope itself is unbroken.
    for yy, (x0, x1) in body_rows.items():
        row(yy + b, x0 + inset, x1 - inset, skin)

    # Sink the whole chest into shadow before anything is lit. A starved chest
    # is a hollow, not a bright slab; the ribs have to be the only lit thing on
    # it or the torso reads as a striped bib.
    for yy, (x0, x1) in spec["hollow"]:
        row(yy + b, x0, x1, skin_deep)

    # Collarbones — two ridges below the throat.
    cy, (cl0, cl1), (cr0, cr1) = spec["collar"]
    row(cy + b, cl0, cl1, PX_BONE)
    row(cy + b, cr0, cr1, PX_BONE)

    # Rib ridges — thin lit lines, left and right held apart by the sternum
    # column below. Each gets a shaded pixel under its inboard end so the arc
    # turns away from the light rather than stopping dead.
    for ry, (l0, l1), (r0, r1) in spec["ribs"]:
        row(ry + b, l0, l1, PX_BONE)
        row(ry + b, r0, r1, PX_BONE)
        dot(l1, ry + 1 + b, PX_BONE_SH)
        dot(r0, ry + 1 + b, PX_BONE_SH)

    # Sternum — deliberately NOT lit. Drawn in the mid-tone it separates the
    # two halves; drawn in bone it bridges them and the whole ribcage collapses
    # into one horizontal bar.
    sx0, sx1 = spec["sternum"]
    for sy in spec["sternum_rows"]:
        row(sy + b, sx0, sx1, skin)

    # Hollow abdomen, deeper still, so the cage has something to sit above.
    for by, (x0, x1) in spec["belly"]:
        row(by + b, x0, x1, skin_void)


def draw_px_adult(
    surface: pygame.Surface,
    x: int,
    y: int,
    frame: int,
    dormant: bool,
    state: str,
) -> int:
    """Draw the adult as true pixel art for a given hunger state.

    Same chibi geometry across all states — identity stays stable while the
    body degrades: cute (healthy) → gaunt/sallow (distressed) → corpse-pale with
    exposed flesh and blood (horror) → grey rotting with bone (dying).
    Returns the display-space y of the top of the head (hat anchor).
    """
    W, H, S = PX_ADULT_W, PX_ADULT_H, PX_ADULT_SCALE
    canvas = pygame.Surface((W, H), pygame.SRCALPHA)

    skin, skin_sh, skin_hi = _px_skin_for_state(state, dormant)
    hair = _px_tint(PX_HAIR, dormant)
    hair_hi = _px_tint(PX_HAIR_HI, dormant)
    eye_w = PX_EYE_W
    eye_d = _px_tint(PX_EYE_D, dormant)
    cheek = _px_tint(PX_CHEEK, dormant)
    mouth = _px_tint(PX_MOUTH, dormant)
    shirt = _px_tint(PX_SHIRT, dormant)
    shirt_sh = _px_tint(PX_SHIRT_SH, dormant)
    shoe = _px_tint(PX_SHOE, dormant)

    def row(yy: int, x0: int, x1: int, c: tuple) -> None:
        if x1 < x0:
            return
        pygame.draw.rect(canvas, c, (x0, yy, x1 - x0 + 1, 1))

    def dot(xx: int, yy: int, c: tuple) -> None:
        if 0 <= xx < W and 0 <= yy < H:
            canvas.set_at((xx, yy), c)

    b = 1 if frame == 1 else 0
    # Dying slumps down instead of bobbing up
    if state == "dying":
        b = 1 if frame == 1 else 0

    gaunt = state in ("distressed", "horror", "dying")
    # Body narrows as it starves (inset each side)
    inset = 0
    if state == "distressed":
        inset = 2
    elif state == "horror":
        inset = 2
    elif state == "dying":
        inset = 3

    # ── Head silhouette (narrows / hollows when gaunt) ────────────────────
    head_rows = {
        4: (11, 20), 5: (9, 22), 6: (8, 23), 7: (7, 24), 8: (7, 24),
        9: (6, 25), 10: (6, 25), 11: (6, 25), 12: (6, 25), 13: (6, 25),
        14: (6, 25), 15: (7, 24), 16: (7, 24), 17: (8, 23), 18: (9, 22),
        19: (11, 20), 20: (13, 18),
    }
    hi = int(inset * 0.7)
    for yy, (x0, x1) in head_rows.items():
        row(yy + b, x0 + hi, x1 - hi, skin)
    for yy in range(11, 19):
        x0, x1 = head_rows[yy]
        row(yy + b, x1 - hi - 1, x1 - hi, skin_sh)
    row(9 + b, 8 + hi, 12, skin_hi)
    row(10 + b, 8 + hi, 11, skin_hi)
    # Skull showing through for gaunt states: a lit cheekbone ridge with the
    # wasted plane hollowed out beneath it. At 32×36 the cheekbone is most of
    # what separates a starving face from a merely sad one — sinking the
    # cheeks alone just makes the face dirty.
    if gaunt:
        row(16 + b, 7 + hi, 8 + hi, skin_sh)
        row(16 + b, 23 - hi, 24 - hi, skin_sh)
        row(17 + b, 8 + hi, 10 + hi, skin_hi)     # cheekbone ridge
        row(17 + b, 21 - hi, 23 - hi, skin_hi)
        row(18 + b, 9 + hi, 12, skin_sh)          # hollow beneath it
        row(18 + b, 19, 22 - hi, skin_sh)

    # ── Hair (thins slightly when starving) ───────────────────────────────
    hair_rows = {
        2: (12, 19), 3: (10, 21), 4: (9, 22), 5: (8, 23), 6: (7, 24),
    }
    for yy, (x0, x1) in hair_rows.items():
        row(yy + b, x0 + hi, x1 - hi, hair)
    row(7 + b, 7 + hi, 12, hair)
    row(7 + b, 19, 24 - hi, hair)
    dot(15, 7 + b, hair)
    dot(16, 7 + b, hair)
    for yy in range(6, 14):
        dot(6 + hi, yy + b, hair)
        dot(25 - hi, yy + b, hair)
    for yy in range(6, 12):
        dot(7 + hi, yy + b, hair)
        dot(24 - hi, yy + b, hair)
    if state == "healthy" or state in ("sad", "distressed"):
        row(3 + b, 12, 15, hair_hi)
        dot(9, 5 + b, hair_hi)
    else:
        # patchy balding tufts (horror/dying)
        dot(11, 3 + b, hair)
        dot(14, 2 + b, hair)
        dot(19, 3 + b, hair)

    # ── Exposed brain — cracked skull top (horror + dying) ────────────────
    if state in ("horror", "dying"):
        # Skull cracked open across the crown; scalp/hair peeled back
        # Bone rim of the broken skull
        row(4 + b, 9, 22, PX_SKULL)
        row(5 + b, 8, 23, PX_SKULL)
        # Wrinkled brain bulging out of the opening
        for yy, (x0, x1) in {2: (11, 20), 3: (9, 22), 4: (10, 21)}.items():
            row(yy + b, x0, x1, PX_BRAIN)
        # Brain folds/sulci (darker grooves)
        dot(12, 2 + b, PX_BRAIN_SH); dot(16, 2 + b, PX_BRAIN_SH); dot(19, 2 + b, PX_BRAIN_SH)
        dot(10, 3 + b, PX_BRAIN_SH); dot(14, 3 + b, PX_BRAIN_SH)
        dot(18, 3 + b, PX_BRAIN_SH); dot(21, 3 + b, PX_BRAIN_SH)
        dot(12, 4 + b, PX_BRAIN_SH); dot(16, 4 + b, PX_BRAIN_SH); dot(20, 4 + b, PX_BRAIN_SH)
        # A trickle of blood from the skull crack down the temple
        dot(9, 6 + b, BLOOD_DARK); dot(9, 7 + b, BLOOD_RED)
        dot(23, 5 + b, BLOOD_DARK); dot(23, 6 + b, BLOOD_RED)

    # ── Eyes ──────────────────────────────────────────────────────────────
    blink = frame == 1
    eye_l, eye_r = 11, 20
    if state == "healthy":
        for ex in (eye_l, eye_r):
            if blink:
                row(13 + b, ex - 2, ex + 2, eye_d)
                dot(ex - 2, 12 + b, eye_d); dot(ex + 2, 12 + b, eye_d)
            else:
                for yy in range(11, 16):
                    row(yy + b, ex - 1, ex + 2, eye_d)
                dot(ex - 2, 12 + b, eye_d); dot(ex - 2, 13 + b, eye_d)
                dot(ex + 3, 12 + b, eye_d); dot(ex + 3, 13 + b, eye_d)
                dot(ex, 11 + b, eye_w); dot(ex + 1, 11 + b, eye_w)
                dot(ex, 12 + b, eye_w); dot(ex + 1, 14 + b, eye_w)
    elif state == "sad":
        for ex in (eye_l, eye_r):
            for yy in range(12, 16):
                row(yy + b, ex - 1, ex + 1, eye_d)
            dot(ex, 13 + b, eye_w)
        # drooped brows slanting inward
        dot(eye_l - 2, 10 + b, hair); dot(eye_l - 1, 10 + b, hair); dot(eye_l, 11 + b, hair)
        dot(eye_r, 11 + b, hair); dot(eye_r + 1, 10 + b, hair); dot(eye_r + 2, 10 + b, hair)
    elif state == "distressed":
        # sunken: dark socket ring, small dull eye, eyebags
        for ex in (eye_l, eye_r):
            for yy in range(11, 16):
                row(yy + b, ex - 2, ex + 2, skin_sh)
            row(13 + b, ex - 1, ex + 1, eye_d)
            row(14 + b, ex - 1, ex + 1, eye_d)
            row(16 + b, ex - 2, ex + 2, skin_sh)  # eyebag
    elif state == "horror":
        # hollow black sockets + pinpoint red glow
        for ex in (eye_l, eye_r):
            for yy in range(10, 17):
                row(yy + b, ex - 2, ex + 2, PX_SOCKET)
            dot(ex, 13 + b, BLOOD_RED)
        # temple veins
        dot(eye_l - 4, 12 + b, VEIN_DARK); dot(eye_l - 4, 13 + b, VEIN_DARK)
        dot(eye_r + 4, 12 + b, VEIN_DARK); dot(eye_r + 4, 13 + b, VEIN_DARK)
    else:  # dying — X eyes + dried blood tears
        for ex in (eye_l, eye_r):
            for yy in range(11, 17):
                row(yy + b, ex - 2, ex + 2, PX_SOCKET)
            dot(ex - 2, 11 + b, eye_w); dot(ex + 2, 11 + b, eye_w)
            dot(ex - 1, 12 + b, eye_w); dot(ex + 1, 12 + b, eye_w)
            dot(ex, 13 + b, eye_w)
            dot(ex - 1, 14 + b, eye_w); dot(ex + 1, 14 + b, eye_w)
            dot(ex - 2, 15 + b, eye_w); dot(ex + 2, 15 + b, eye_w)
            dot(ex - 1, 17 + b, BLOOD_DARK); dot(ex - 1, 18 + b, BLOOD_DARK)

    # ── Cheeks (blush only when healthy) ──────────────────────────────────
    if state == "healthy":
        row(16 + b, 8, 9, cheek); row(17 + b, 8, 9, cheek)
        row(16 + b, 22, 23, cheek); row(17 + b, 22, 23, cheek)

    # ── Nose + mouth ──────────────────────────────────────────────────────
    dot(15, 16 + b, skin_sh); dot(16, 16 + b, skin_sh)
    if state == "healthy":
        dot(13, 18 + b, mouth); dot(18, 18 + b, mouth); row(19 + b, 14, 17, mouth)
    elif state == "sad":
        row(19 + b, 14, 17, mouth); dot(13, 20 + b, mouth); dot(18, 20 + b, mouth)  # frown
    elif state == "distressed":
        row(19 + b, 14, 17, mouth)  # flat grimace
    elif state == "horror":
        # open screaming maw with teeth
        for yy in range(18, 22):
            row(yy + b, 13, 18, PX_SOCKET)
        dot(14, 18 + b, NOMI_TEETH); dot(16, 18 + b, NOMI_TEETH); dot(18, 18 + b, NOMI_TEETH)
        dot(13, 20 + b, BLOOD_RED)  # blood at lip
    else:  # dying — slack jaw, dried blood
        for yy in range(19, 22):
            row(yy + b, 14, 17, PX_SOCKET)
        dot(13, 19 + b, BLOOD_DARK); dot(18, 20 + b, BLOOD_DARK)

    # ── Body / shirt (narrows when gaunt) ─────────────────────────────────
    body_rows = {
        21: (11, 20), 22: (10, 21), 23: (9, 22), 24: (9, 22),
        25: (9, 22), 26: (9, 22), 27: (9, 22), 28: (10, 21),
    }
    if gaunt:
        # Starved: bare emaciated torso with the ribcage showing through intact
        # skin. Horror and dying share it and paint their wounds over the top.
        def rib_band(yy: int, taper: int = 0) -> tuple:
            """Rib spans for one torso row — held 1px clear of the silhouette
            edge (bone touching the outline fuses the cage to the arms) and
            stopped either side of the sternum column at x15–16."""
            x0, x1 = body_rows[yy]
            return (x0 + inset + 1 + taper, 14), (17, x1 - inset - 1 - taper)

        _px_skeletal_torso(
            row, dot, b, body_rows, inset, skin, skin_sh,
            {
                "hollow": [(yy, (x0 + inset, x1 - inset))
                           for yy, (x0, x1) in body_rows.items() if yy >= 22],
                "collar": (21, (11 + inset, 14), (17, 20 - inset)),
                "sternum": (15, 16),
                "sternum_rows": range(21, 27),
                "ribs": [
                    (22, *rib_band(22)),
                    (24, *rib_band(24)),
                    (26, *rib_band(26, taper=1)),
                ],
                "belly": [
                    (27, (10 + inset, 21 - inset)),
                    (28, (11 + inset, 20 - inset)),
                ],
            },
        )
    else:
        for yy, (x0, x1) in body_rows.items():
            row(yy + b, x0 + inset, x1 - inset, shirt)
        for yy in range(24, 29):
            row(yy + b, 20 - inset, 21 - inset, shirt_sh)
        dot(15, 21 + b, shirt_sh); dot(16, 21 + b, shirt_sh)

    # ── Exposed flesh / wounds (horror + dying), painted over the ribcage ──
    if state == "horror":
        # The envelope is breached: the chest wall is torn away on the left,
        # raw muscle beneath, ribs still bridging the hole. The right half of
        # the cage is left intact so the skeleton still reads.
        wl0 = 11 + inset
        for yy in range(23, 27):
            row(yy + b, wl0, 14, FLESH_DARK)
        for yy in range(24, 26):
            row(yy + b, wl0 + 1, 13, FLESH_PINK)
        # ribs bridging the wound — bone over raw muscle
        row(23 + b, wl0, 14, PX_BONE)
        row(25 + b, wl0, 14, PX_BONE)
        # Ragged torn skin edge. Drawn in the highlight, not the base skin:
        # base skin would only read against the blue shirt, and on a bare
        # torso it is invisible against itself.
        dot(15, 23 + b, skin_hi); dot(15, 26 + b, skin_hi)
        dot(wl0, 22 + b, skin_hi); dot(wl0 + 1, 27 + b, skin_hi)
        # bleeding down into the belly hollow
        dot(13, 27 + b, BLOOD_DARK); dot(13, 28 + b, BLOOD_RED)
        dot(16, 28 + b, BLOOD_DARK)
    elif state == "dying":
        # The same breach, further gone — the muscle has darkened and dried.
        wl0 = 11 + inset
        for yy in range(23, 26):
            row(yy + b, wl0, 13, FLESH_DARK)
        dot(wl0 + 1, 24 + b, BLOOD_DARK)
        dot(wl0 + 1, 26 + b, BLOOD_DARK)
        dot(wl0 + 1, 27 + b, BLOOD_RED)
        dot(18 - inset, 24 + b, VEIN_DARK); dot(19 - inset, 25 + b, VEIN_DARK)

    # ── Arms (stick-thin with a knobbly elbow once starved) ───────────────
    arm_lx = 7 + inset
    arm_rx = 24 - inset
    for yy in range(22, 27):
        w = 1 if not gaunt else (1 if yy in (24, 25) else 0)
        row(yy + b, arm_lx, arm_lx + w, skin)
        row(yy + b, arm_rx - w, arm_rx, skin)
        if gaunt and w:
            # shade the joint bulge so it reads as bone, not as a thicker arm
            dot(arm_lx + w, yy + b, skin_sh)
            dot(arm_rx - w, yy + b, skin_sh)
    dot(arm_lx, 27 + b, skin); dot(arm_rx, 27 + b, skin)
    if not gaunt:
        dot(arm_lx + 1, 27 + b, skin_sh); dot(arm_rx - 1, 27 + b, skin_sh)

    # Exposed bone on left arm (dying)
    if state == "dying":
        dot(arm_lx, 25 + b, BONE_WHITE)
        dot(arm_lx - 1, 26 + b, BONE_WHITE)
        dot(arm_lx, 26 + b, BLOOD_RED)

    # ── Legs + shoes (wasted limbs — silhouette is what survives upscale) ──
    leg_in = 1 if gaunt else 0
    for yy in range(29, 32):
        row(yy + b, 12 + leg_in, 14, skin)
        row(yy + b, 17, 19 - leg_in, skin)
    if gaunt:
        # knobbly knees — the joint stays wide while the limb wastes away
        dot(12 + leg_in - 1, 30 + b, skin_sh)
        dot(19 - leg_in + 1, 30 + b, skin_sh)
    row(32 + b, 11 + leg_in, 14, shoe); row(33 + b, 11 + leg_in, 14, shoe)
    row(32 + b, 17, 20 - leg_in, shoe); row(33 + b, 17, 20 - leg_in, shoe)

    # ── Rot patches (dying) ───────────────────────────────────────────────
    if state == "dying":
        for (rx, ry) in ((10 + inset, 24), (18 - inset, 22)):
            dot(rx, ry + b, PX_ROT); dot(rx + 1, ry + b, PX_ROT_DK)
            dot(rx, ry + 1 + b, PX_ROT_DK)

    # ── Scale up (nearest-neighbor) ───────────────────────────────────────
    scaled = pygame.transform.scale(canvas, (W * S, H * S))

    if state == "dying":
        # DEAD: the corpse has collapsed onto its side on the floor.
        # Rotate the whole sprite 90° so it lies horizontally.
        corpse = pygame.transform.rotate(scaled, 90)
        cw, ch = corpse.get_size()
        # Rest it on the floor of the 100×110 area
        floor_y = y + 110
        blit_x = x + (100 - cw) // 2
        blit_y = floor_y - ch - 4
        # Spreading blood pool on the floor beneath the body
        pool = pygame.Surface((100, 16), pygame.SRCALPHA)
        pygame.draw.ellipse(pool, (*BLOOD_DARK, 235), (6, 4, 88, 11))
        pygame.draw.ellipse(pool, (*BLOOD_RED, 220), (16, 6, 60, 7))
        pygame.draw.ellipse(pool, (150, 20, 24, 180), (34, 7, 26, 4))
        surface.blit(pool, (x, floor_y - 13))
        surface.blit(corpse, (blit_x, blit_y))
        # No death tint. A translucent ellipse over the rotated bounding box
        # spills across the transparent corners and reads as a red halo around
        # the corpse rather than a tint on it; PX_SKIN_DEAD carries the
        # deadness instead. The floor pool above is the only red that stays.
        # dying doesn't wear a hat; head-top irrelevant but return something sane
        return blit_y
    else:
        blit_x = x + (100 - W * S) // 2
        blit_y = y + (110 - H * S) // 2
        surface.blit(scaled, (blit_x, blit_y))

    if dormant:
        _draw_zzz(surface, blit_x + W * S - 6, blit_y + 6)

    return blit_y + (2 + b) * S


def draw_px_adult_healthy(
    surface: pygame.Surface, x: int, y: int, frame: int, dormant: bool,
) -> int:
    """Convenience wrapper — healthy pixel-art adult."""
    return draw_px_adult(surface, x, y, frame, dormant, "healthy")


def draw_px_baby(
    surface: pygame.Surface,
    x: int,
    y: int,
    frame: int,
    dormant: bool,
    state: str,
) -> int:
    """Draw the baby as true pixel art — a rounder, bigger-headed chibi.

    Same character DNA and 5-state horror progression as the adult, but with
    baby proportions (huge head, tiny body, stubby limbs). Returns display-space
    head-top y for the hat anchor.
    """
    W, H, S = PX_BABY_W, PX_BABY_H, PX_BABY_SCALE
    canvas = pygame.Surface((W, H), pygame.SRCALPHA)

    skin, skin_sh, skin_hi = _px_skin_for_state(state, dormant)
    hair = _px_tint(PX_HAIR, dormant)
    hair_hi = _px_tint(PX_HAIR_HI, dormant)
    eye_w = PX_EYE_W
    eye_d = _px_tint(PX_EYE_D, dormant)
    cheek = _px_tint(PX_CHEEK, dormant)
    mouth = _px_tint(PX_MOUTH, dormant)
    shirt = _px_tint(PX_SHIRT, dormant)
    shirt_sh = _px_tint(PX_SHIRT_SH, dormant)

    def row(yy: int, x0: int, x1: int, c: tuple) -> None:
        if x1 < x0:
            return
        pygame.draw.rect(canvas, c, (x0, yy, x1 - x0 + 1, 1))

    def dot(xx: int, yy: int, c: tuple) -> None:
        if 0 <= xx < W and 0 <= yy < H:
            canvas.set_at((xx, yy), c)

    b = 1 if frame == 1 else 0
    gaunt = state in ("distressed", "horror", "dying")
    inset = 0
    if state == "distressed":
        inset = 1
    elif state == "horror":
        inset = 1
    elif state == "dying":
        inset = 2

    # ── Big round head (cx=13, spans ~rows 3-19) ──────────────────────────
    head_rows = {
        3: (9, 16), 4: (7, 18), 5: (6, 19), 6: (5, 20), 7: (5, 20),
        8: (4, 21), 9: (4, 21), 10: (4, 21), 11: (4, 21), 12: (4, 21),
        13: (4, 21), 14: (4, 21), 15: (5, 20), 16: (5, 20), 17: (6, 19),
        18: (8, 17), 19: (10, 15),
    }
    # Full inset, not a fraction of it: a fraction such as int(inset * 0.6)
    # floors to 0 at the baby's inset of 1, which would make a starving baby's
    # head byte-identical to a healthy one — and the head is 17 of its 30 rows.
    hi = inset
    for yy, (x0, x1) in head_rows.items():
        row(yy + b, x0 + hi, x1 - hi, skin)
    for yy in range(9, 18):
        x0, x1 = head_rows[yy]
        row(yy + b, x1 - hi - 1, x1 - hi, skin_sh)
    row(7 + b, 6 + hi, 9, skin_hi)
    row(8 + b, 6 + hi, 8, skin_hi)
    if gaunt:
        # Cheekbone ridge over a hollow, as on the adult — see draw_px_adult.
        row(15 + b, 5 + hi, 6 + hi, skin_sh)
        row(15 + b, 19 - hi, 20 - hi, skin_sh)
        row(16 + b, 6 + hi, 8 + hi, skin_hi)
        row(16 + b, 17 - hi, 19 - hi, skin_hi)
        row(17 + b, 7 + hi, 9 + hi, skin_sh)
        row(17 + b, 16 - hi, 18 - hi, skin_sh)

    # ── Hair — little curl/tuft on top ────────────────────────────────────
    hair_rows = {1: (11, 14), 2: (9, 16), 3: (8, 17)}
    for yy, (x0, x1) in hair_rows.items():
        row(yy + b, x0 + hi, x1 - hi, hair)
    row(4 + b, 7 + hi, 10, hair)   # fringe left
    row(4 + b, 15, 18 - hi, hair)  # fringe right
    dot(12, 4 + b, hair); dot(13, 4 + b, hair)
    # side locks
    for yy in range(4, 10):
        dot(5 + hi, yy + b, hair)
        dot(20 - hi, yy + b, hair)
    if state in ("healthy", "sad", "distressed"):
        dot(10, 1 + b, hair_hi); dot(11, 2 + b, hair_hi)
        # cute cowlick curl
        dot(13, 0 + b, hair); dot(14, 0 + b, hair); dot(14, 1 + b, hair)
    else:
        dot(8, 2 + b, hair); dot(17, 1 + b, hair)  # patchy

    # ── Exposed brain — cracked skull top (horror + dying) ────────────────
    if state in ("horror", "dying"):
        # Broken skull rim
        row(5 + b, 6, 19, PX_SKULL)
        # Brain bulging out of the crown
        for yy, (x0, x1) in {2: (9, 16), 3: (7, 18), 4: (7, 18), 5: (8, 17)}.items():
            row(yy + b, x0, x1, PX_BRAIN)
        # Folds
        dot(9, 2 + b, PX_BRAIN_SH); dot(13, 2 + b, PX_BRAIN_SH); dot(16, 2 + b, PX_BRAIN_SH)
        dot(8, 3 + b, PX_BRAIN_SH); dot(12, 3 + b, PX_BRAIN_SH); dot(15, 3 + b, PX_BRAIN_SH)
        dot(10, 4 + b, PX_BRAIN_SH); dot(14, 4 + b, PX_BRAIN_SH); dot(17, 4 + b, PX_BRAIN_SH)
        # blood trickle from skull
        dot(6, 7 + b, BLOOD_DARK); dot(6, 8 + b, BLOOD_RED)
        dot(19, 6 + b, BLOOD_DARK)

    # ── Eyes — extra large for baby cuteness ──────────────────────────────
    blink = frame == 1
    eye_l, eye_r = 9, 16
    if state == "healthy":
        for ex in (eye_l, eye_r):
            if blink:
                row(11 + b, ex - 2, ex + 2, eye_d)
                dot(ex - 2, 10 + b, eye_d); dot(ex + 2, 10 + b, eye_d)
            else:
                for yy in range(9, 14):
                    row(yy + b, ex - 2, ex + 2, eye_d)
                # big sparkle
                dot(ex - 1, 9 + b, eye_w); dot(ex, 9 + b, eye_w)
                dot(ex - 1, 10 + b, eye_w)
                dot(ex + 1, 12 + b, eye_w)
    elif state == "sad":
        for ex in (eye_l, eye_r):
            for yy in range(10, 14):
                row(yy + b, ex - 1, ex + 1, eye_d)
            dot(ex, 11 + b, eye_w)
        dot(eye_l - 2, 8 + b, hair); dot(eye_l - 1, 8 + b, hair)
        dot(eye_r + 1, 8 + b, hair); dot(eye_r + 2, 8 + b, hair)
    elif state == "distressed":
        for ex in (eye_l, eye_r):
            for yy in range(9, 14):
                row(yy + b, ex - 2, ex + 2, skin_sh)
            row(11 + b, ex - 1, ex + 1, eye_d)
            row(12 + b, ex - 1, ex + 1, eye_d)
            row(14 + b, ex - 2, ex + 2, skin_sh)
    elif state == "horror":
        for ex in (eye_l, eye_r):
            for yy in range(8, 15):
                row(yy + b, ex - 2, ex + 2, PX_SOCKET)
            dot(ex, 11 + b, BLOOD_RED)
        dot(eye_l - 3, 10 + b, VEIN_DARK); dot(eye_r + 3, 10 + b, VEIN_DARK)
    else:  # dying — X eyes
        for ex in (eye_l, eye_r):
            for yy in range(9, 15):
                row(yy + b, ex - 2, ex + 2, PX_SOCKET)
            dot(ex - 2, 9 + b, eye_w); dot(ex + 2, 9 + b, eye_w)
            dot(ex - 1, 10 + b, eye_w); dot(ex + 1, 10 + b, eye_w)
            dot(ex, 11 + b, eye_w)
            dot(ex - 1, 12 + b, eye_w); dot(ex + 1, 12 + b, eye_w)
            dot(ex - 2, 13 + b, eye_w); dot(ex + 2, 13 + b, eye_w)
            dot(ex - 1, 15 + b, BLOOD_DARK)

    # ── Cheeks (blush only healthy) ───────────────────────────────────────
    if state == "healthy":
        row(14 + b, 6, 7, cheek); row(15 + b, 6, 7, cheek)
        row(14 + b, 18, 19, cheek); row(15 + b, 18, 19, cheek)

    # ── Mouth ─────────────────────────────────────────────────────────────
    if state == "healthy":
        dot(11, 16 + b, mouth); dot(14, 16 + b, mouth); row(17 + b, 12, 13, mouth)
    elif state == "sad":
        row(16 + b, 11, 14, mouth); dot(11, 17 + b, mouth); dot(14, 17 + b, mouth)
    elif state == "distressed":
        row(16 + b, 11, 14, mouth)
    elif state == "horror":
        for yy in range(15, 18):
            row(yy + b, 10, 15, PX_SOCKET)
        dot(11, 15 + b, NOMI_TEETH); dot(13, 15 + b, NOMI_TEETH)
        dot(10, 17 + b, BLOOD_RED)
    else:  # dying
        for yy in range(16, 18):
            row(yy + b, 11, 14, PX_SOCKET)
        dot(10, 16 + b, BLOOD_DARK)

    # ── Tiny body / shirt ─────────────────────────────────────────────────
    body_rows = {20: (8, 17), 21: (7, 18), 22: (7, 18), 23: (7, 18), 24: (8, 17)}
    if gaunt:
        # Starved: bare torso, ribcage through intact skin. Shared with horror
        # and dying so a hungrier baby can never look better fed than this one.
        def rib_band(yy: int, taper: int = 0) -> tuple:
            x0, x1 = body_rows[yy]
            return (x0 + inset + 1 + taper, 11), (14, x1 - inset - 1 - taper)

        _px_skeletal_torso(
            row, dot, b, body_rows, inset, skin, skin_sh,
            {
                "hollow": [(yy, (x0 + inset, x1 - inset))
                           for yy, (x0, x1) in body_rows.items() if yy >= 21],
                "collar": (20, (9 + inset, 11), (14, 16 - inset)),
                "sternum": (12, 13),
                "sternum_rows": range(20, 24),
                # Only row 22: the baby has five torso rows, so a rib on 21
                # would sit flush against the collarbone on 20 and the two
                # would fuse into a single bright mass.
                "ribs": [(22, *rib_band(22))],
                "belly": [(24, (9 + inset, 16 - inset))],
            },
        )
    else:
        for yy, (x0, x1) in body_rows.items():
            row(yy + b, x0 + inset, x1 - inset, shirt)
        for yy in range(21, 25):
            row(yy + b, 17 - inset, 18 - inset, shirt_sh)

    # Exposed flesh / wound, painted over the ribcage
    if state == "horror":
        # Chest wall torn open on the left; the right half of the cage survives.
        wl0 = 8 + inset
        for yy in range(21, 24):
            row(yy + b, wl0, 11, FLESH_DARK)
        row(22 + b, wl0, 11, PX_BONE)   # a rib bridging the wound
        # ragged edge in the highlight — on a bare torso, base skin would be
        # invisible against itself (it only reads against the shirt)
        dot(12, 21 + b, skin_hi); dot(12, 23 + b, skin_hi)
        dot(wl0, 20 + b, skin_hi)
        dot(10, 24 + b, BLOOD_DARK); dot(10, 25 + b, BLOOD_RED)
    elif state == "dying":
        wl0 = 8 + inset
        for yy in range(21, 24):
            row(yy + b, wl0, 10, FLESH_DARK)
        dot(wl0 + 1, 24 + b, BLOOD_DARK)
        dot(wl0 + 1, 25 + b, BLOOD_RED)

    # ── Stubby arms (thin to a stick with an elbow knob when starved) ─────
    arm_lx = 5 + inset
    arm_rx = 20 - inset
    for yy in range(20, 23):
        w = 1 if not gaunt else (1 if yy == 21 else 0)
        row(yy + b, arm_lx, arm_lx + w, skin)
        row(yy + b, arm_rx - w, arm_rx, skin)
        if gaunt and w:
            dot(arm_lx + w, yy + b, skin_sh)
            dot(arm_rx - w, yy + b, skin_sh)
    if state == "dying":
        dot(arm_lx, 22 + b, BONE_WHITE); dot(arm_lx, 23 + b, BLOOD_RED)

    # ── Stubby legs / feet (waste away with the rest of the silhouette) ───
    leg_in = 1 if gaunt else 0
    for yy in range(25, 27):
        row(yy + b, 9 + leg_in, 11, skin)
        row(yy + b, 14, 16 - leg_in, skin)
    row(27 + b, 8 + leg_in, 11, skin_sh)
    row(27 + b, 14, 17 - leg_in, skin_sh)

    if state == "dying":
        for (rx, ry) in ((8 + inset, 22), (15 - inset, 20)):
            dot(rx, ry + b, PX_ROT); dot(rx, ry + 1 + b, PX_ROT_DK)

    # ── Scale + blit into the 80×90 baby area ────────────────────────────
    scaled = pygame.transform.scale(canvas, (W * S, H * S))

    if state == "dying":
        # DEAD: collapsed on its side on the floor
        corpse = pygame.transform.rotate(scaled, 90)
        cw, ch = corpse.get_size()
        floor_y = y + 90
        blit_x = x + (80 - cw) // 2
        blit_y = floor_y - ch - 3
        pool = pygame.Surface((80, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(pool, (*BLOOD_DARK, 235), (4, 3, 72, 10))
        pygame.draw.ellipse(pool, (*BLOOD_RED, 215), (14, 5, 48, 6))
        surface.blit(pool, (x, floor_y - 11))
        surface.blit(corpse, (blit_x, blit_y))
        # No death tint — see draw_px_adult for why.
        return blit_y

    blit_x = x + (80 - W * S) // 2
    blit_y = y + (90 - H * S) // 2
    surface.blit(scaled, (blit_x, blit_y))

    if dormant:
        _draw_zzz(surface, blit_x + W * S - 6, blit_y + 4)

    return blit_y + (1 + b) * S


def draw_nomi_adult(
    surface: pygame.Surface,
    x: int,
    y: int,
    frame: int,
    dormant: bool,
    hunger: float = 100.0,
) -> None:
    """Draw adult NOMI — uncanny valley humanoid. 100×110 drawing area at (x, y)."""
    state = "healthy" if dormant else _hunger_state(hunger)

    # The adult is true pixel art across all hunger states.
    draw_px_adult(surface, x, y, frame, dormant, state)
    return


def draw_creature(
    surface: pygame.Surface,
    x: int,
    y: int,
    stage: str,
    hat: str | None,
    frame: int,
    dormant: bool,
    hunger: float = 100.0,
) -> None:
    """Draw the creature sprite at (x, y) using pygame.draw primitives.

    Args:
        surface: Pygame surface to draw onto.
        x, y:    Top-left of the drawing area.
        stage:   One of "egg", "baby", "adult".
        hat:     None, "hat_a" (top hat), or "hat_b" (crown).
        frame:   Animation frame: 0 or 1 (alternates every second for idle bob).
        dormant: If True, applies a blue-grey dormancy tint (takes priority over hunger).
        hunger:  Hunger level 0–100. Controls horror deterioration visuals.
    """
    stage_lower = stage.lower() if stage else "egg"

    if stage_lower == "egg":
        draw_egg(surface, x, y, frame, dormant)
        # Eggs don't wear hats
        return

    # Draw the pixel-art creature, then overlay the hat
    if stage_lower == "baby":
        draw_nomi_baby(surface, x, y, frame, dormant, hunger)
        cx = x + 40
        # Pixel-art baby: head top is canvas row 1 after upscale.
        b = 1 if frame == 1 else 0
        blit_y = y + (90 - PX_BABY_H * PX_BABY_SCALE) // 2
        head_top = blit_y + (1 + b) * PX_BABY_SCALE
    else:
        # adult (also handles unknown stages)
        draw_nomi_adult(surface, x, y, frame, dormant, hunger)
        cx = x + 50
        # Pixel-art adult (all states): head top is canvas row 2 after upscale.
        b = 1 if frame == 1 else 0
        blit_y = y + (110 - PX_ADULT_H * PX_ADULT_SCALE) // 2
        head_top = blit_y + (2 + b) * PX_ADULT_SCALE

    # A dead (dying) creature lies sideways on the floor — no hat.
    state = "healthy" if dormant else _hunger_state(hunger)
    if state == "dying":
        return

    _HATS = {
        "hat_a": _draw_top_hat,
        "hat_b": _draw_crown,
        "hat_cap": _draw_cap,
        "hat_beanie": _draw_beanie,
        "hat_wizard": _draw_wizard,
        "hat_halo": _draw_halo,
    }
    fn = _HATS.get(hat)
    if fn is not None:
        fn(surface, cx, head_top)
