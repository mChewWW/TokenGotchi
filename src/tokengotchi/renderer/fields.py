"""Field cosmetics — the animated backdrop behind the pet.

`Starfield` (in `background.py`) used to be the only backdrop. This module
adds the other five and a registry so `window.py` can hold a single
`self._field` reference resolved from `game_state.field_slot` and treat all
six interchangeably, mirroring `skins.py`'s `SKINS`/`get()` pattern.

Every class here implements the SAME interface `Starfield` already has:
`__init__(width, height, seed=42)`, `update(dt)`, `draw(surface)`. Drawing
stays to primitive calls (`set_at`, small `pygame.draw.circle`/`rect`), never
per-particle Surface blits and never numpy/surfarray — that is what keeps six
interchangeable fields inside the same per-frame budget the starfield already
holds at 30 FPS.

Each field carries a `motion_model` tag distinct enough that no lower tier
shares the legendary's model — enforced below, not left as documentation
(mirrors the `rarity_locked` gate already enforced in `skins.py`).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

from .background import Starfield

# Bottom 140px is the HUD/shop strip — every field stays clear of it, exactly
# like Starfield.
_HUD_MARGIN = 140

# The known dark near-black night-sky base every field's content layer sits
# against (Aurora's base fill; also the target Embers' bottom wash and
# Skulls' fade lifecycle pre-blend toward, per direction_v15's "fake
# transparency via a pre-blended solid colour" technique — an ordinary
# opaque `draw.rect`/`set_at` colour, never a `SRCALPHA` surface or blit).
_NIGHT_BG = (10, 14, 22)


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


# ── Hearts — twinkle ────────────────────────────────────────────────────────

# A small hand-authored heart, stamped via set_at. 5 wide, 4 tall.
_HEART_GLYPH = (
    ".#.#.",
    "#####",
    ".###.",
    "..#..",
)

_HEART_COLOURS = [
    (255, 120, 150),   # rose
    (255, 170, 190),   # pale pink
    (230, 80, 110),    # deeper red-pink
]


class Hearts:
    """Twinkling field of small pixel hearts. Same math as Starfield's
    brightness sine, a heart glyph instead of a point/circle."""

    motion_model = "twinkle"

    def __init__(self, width: int, height: int, seed: int = 42) -> None:
        self._time = 0.0
        rng = random.Random(seed)
        usable_height = height - _HUD_MARGIN

        self._hearts: list[dict] = []
        for _ in range(70):
            self._hearts.append({
                "x": rng.uniform(0.0, float(width)),
                "y": rng.uniform(0.0, float(usable_height)),
                "brightness": 1.0,
                "base_brightness": rng.uniform(0.35, 1.0),
                "twinkle_speed": rng.uniform(0.3, 1.8),
                "twinkle_phase": rng.uniform(0.0, math.tau),
                "colour": rng.choice(_HEART_COLOURS),
            })

    def update(self, dt: float) -> None:
        self._time += dt
        t = self._time
        for h in self._hearts:
            phase = h["twinkle_phase"] + t * h["twinkle_speed"] * math.tau
            h["brightness"] = h["base_brightness"] * (0.5 + 0.5 * math.sin(phase))

    def draw(self, surface: pygame.Surface) -> None:
        w, hgt = surface.get_size()
        for h in self._hearts:
            b = h["brightness"]
            r, g, bl = h["colour"]
            colour = (int(r * b), int(g * b), int(bl * b))
            ox, oy = int(h["x"]), int(h["y"])
            for ry, row in enumerate(_HEART_GLYPH):
                for rx, ch in enumerate(row):
                    if ch != "#":
                        continue
                    px, py = ox + rx, oy + ry
                    if 0 <= px < w and 0 <= py < hgt:
                        surface.set_at((px, py), colour)


# ── Skulls — fade_cycle ─────────────────────────────────────────────────────

# Non-gory 9x9 skull, second redesign: rounded cranium silhouette tapering
# straight to a jaw (no flat brow band this time — the cranium runs directly
# into the eye band), 3x3 eye sockets (widened from 2x2) separated by a
# visible nose-bridge gap, and a smooth, unbroken jaw (no teeth dividers —
# stays clear of "jagged jaw"). No red, no blood, off-white/bone/pale-grey/
# charcoal-shadow only. `e` marks the eye-socket pixels; `n` marks the
# nose-bridge gap.
_SKULL_GLYPH = (
    "..#####..",
    ".#######.",
    "#########",
    "#eeeneee#",
    "#eeeneee#",
    "#eeeneee#",
    ".#######.",
    "..#####..",
    "...###...",
)

_BONE = (225, 220, 205)
_SOCKET_CHARCOAL = (55, 55, 58)   # near-charcoal — substantially darker than the old muted-grey sockets, for real silhouette contrast
_NOSE = (185, 180, 168)


class Skulls:
    """8-bit skulls on a fade-in -> hold -> fade-out -> reposition lifecycle
    — replaces the retired static "blink" behaviour (the eyes no longer
    toggle; the whole glyph now fades). Each instance fades in (~0.6s),
    holds at full brightness (~2.5-4.5s, randomized per cycle), fades out
    (~0.6s), then reposits to a new random (x, y) and repeats. Initial ages
    are randomized across the full cycle length so the 24 instances never
    sync visually.

    The fade is implemented with the same pre-blended-solid-colour technique
    as Embers' bottom wash: at each frame, every glyph colour is blended
    toward the known dark background colour (`_NIGHT_BG`) by the current
    0->1->0 fade envelope, then drawn as an ordinary opaque colour — never a
    per-pixel alpha surface."""

    motion_model = "fade_cycle"

    _FADE = 0.6           # seconds to fade in / fade out
    _HOLD_MIN = 2.5
    _HOLD_MAX = 4.5
    _COUNT = 24

    def __init__(self, width: int, height: int, seed: int = 42) -> None:
        self._width = width
        self._usable_height = height - _HUD_MARGIN
        self._rng = random.Random(seed)

        self._skulls: list[dict] = []
        for _ in range(self._COUNT):
            self._skulls.append(self._spawn(partial=True))

    def _spawn(self, partial: bool = False) -> dict:
        rng = self._rng
        hold = rng.uniform(self._HOLD_MIN, self._HOLD_MAX)
        total = self._FADE * 2.0 + hold
        return {
            "x": rng.uniform(0.0, float(self._width)),
            "y": rng.uniform(0.0, float(self._usable_height)),
            "hold": hold,
            "total": total,
            "age": rng.uniform(0.0, total) if partial else 0.0,
            # A small independent shimmer during the hold phase (mirrors the
            # sine-driven brightness every other field in this module
            # already uses, e.g. Hearts' twinkle) — keeps "holding" from
            # rendering as one perfectly frozen brightness value forever.
            "shimmer_phase": rng.uniform(0.0, math.tau),
            "shimmer_speed": rng.uniform(0.3, 0.9),
        }

    def update(self, dt: float) -> None:
        for i, s in enumerate(self._skulls):
            s["age"] += dt
            if s["age"] >= s["total"]:
                self._skulls[i] = self._spawn()

    @staticmethod
    def _envelope(s: dict, fade: float) -> float:
        age = s["age"]
        if age < fade:
            return age / fade
        if age < fade + s["hold"]:
            hold_age = age - fade
            phase = s["shimmer_phase"] + hold_age * s["shimmer_speed"] * math.tau
            return 0.94 + 0.06 * math.sin(phase)
        out_age = age - fade - s["hold"]
        return max(0.0, 1.0 - out_age / fade)

    def draw(self, surface: pygame.Surface) -> None:
        w, hgt = surface.get_size()
        fade = self._FADE
        for s in self._skulls:
            env = self._envelope(s, fade)
            if env <= 0.0:
                continue
            ox, oy = int(s["x"]), int(s["y"])
            bone_colour = _lerp(_NIGHT_BG, _BONE, env)
            socket_colour = _lerp(_NIGHT_BG, _SOCKET_CHARCOAL, env)
            nose_colour = _lerp(_NIGHT_BG, _NOSE, env)
            for ry, row in enumerate(_SKULL_GLYPH):
                for rx, ch in enumerate(row):
                    if ch == ".":
                        continue
                    if ch == "#":
                        colour = bone_colour
                    elif ch == "e":
                        colour = socket_colour
                    else:
                        colour = nose_colour
                    px, py = ox + rx, oy + ry
                    if 0 <= px < w and 0 <= py < hgt:
                        surface.set_at((px, py), colour)


# ── Snow — drift ─────────────────────────────────────────────────────────────

_SNOW_COLOURS = [
    (255, 255, 255),
    (235, 240, 250),
    (210, 225, 245),
]


class Snow:
    """Pale flecks falling straight down with a gentle horizontal sway —
    genuinely falling motion, distinct from the static, twinkling fields."""

    motion_model = "drift"

    def __init__(self, width: int, height: int, seed: int = 42) -> None:
        self._width = width
        self._usable_height = height - _HUD_MARGIN
        rng = random.Random(seed)

        self._flakes: list[dict] = []
        for _ in range(90):
            self._flakes.append({
                "x0": rng.uniform(0.0, float(width)),
                "y": rng.uniform(0.0, float(self._usable_height)),
                "fall_speed": rng.uniform(10.0, 30.0),
                "sway_amp": rng.uniform(3.0, 12.0),
                "sway_speed": rng.uniform(0.5, 1.6),
                "phase": rng.uniform(0.0, math.tau),
                "radius": rng.uniform(0.5, 1.6),
                "colour": rng.choice(_SNOW_COLOURS),
                "t": 0.0,
            })

    def update(self, dt: float) -> None:
        for f in self._flakes:
            f["t"] += dt
            f["y"] += f["fall_speed"] * dt
            if f["y"] > self._usable_height:
                f["y"] -= self._usable_height

    def draw(self, surface: pygame.Surface) -> None:
        w = self._width
        for f in self._flakes:
            sway = math.sin(f["phase"] + f["t"] * f["sway_speed"] * math.tau) * f["sway_amp"]
            x = int((f["x0"] + sway) % w)
            y = int(f["y"])
            if f["radius"] <= 1.0:
                surface.set_at((x, y), f["colour"])
            else:
                pygame.draw.circle(surface, f["colour"], (x, y), max(1, int(round(f["radius"]))))


# ── Embers — lifecycle ───────────────────────────────────────────────────────

# Colour is a function of `life_frac`, not a fixed per-particle pick — this
# is the physically-correct fire-cooling direction: hot ember red near
# spawn/the bottom, through the mid-orange, cooling to a pale highlight as
# the ember rises and fades near the top.
_EMBER_HOT = (255, 70, 20)     # deep ember red, life_frac ~= 0
_EMBER_MID = (255, 140, 40)    # existing mid-orange, life_frac ~= 0.5
_EMBER_COOL = (235, 235, 245)  # pale, cooled highlight, life_frac ~= 1

# Bottom ambient fire-glow wash: 4 horizontal `pygame.draw.rect` bands, each
# an ordinary opaque pre-blended solid RGB colour (no SRCALPHA, no blit) —
# a weighted average of a single warm ember tone (the midpoint of the
# existing `_EMBER_HOT`/`_EMBER_MID` particle tones, not a new saturated
# red) against the known dark base background colour. Weight decreases
# going up the screen so the glow reads strongest/reddest at the very
# bottom, fading to almost nothing near the top of the wash.
_EMBER_GLOW = _lerp(_EMBER_HOT, _EMBER_MID, 0.5)
_EMBER_BASE_BAND_WEIGHTS = (0.5, 0.3, 0.15, 0.05)   # bottom-to-top, unmodulated base weights
_EMBER_BAND_HEIGHT = 16                             # px per band; 4 bands span 64px (within the 60-80px range)
_EMBER_BAND_MAX_WEIGHT = 0.65                       # hard clamp so jitter/breathing can never push a band into strobing territory

# direction_v16: the human's round-3 verdict asked for a *dynamic* reddish
# heat glow, not the static per-import pre-blended wash this used to be
# (`_EMBER_BAND_COLOURS` was a module-level constant, confirmed zero
# per-frame variation). Weights are now recomputed every frame in
# `Embers.draw` from the same `self._time` accumulator every other animated
# field in this module already uses (Aurora/Skulls precedent) — a slow
# "breathing" sine plus a faster low-amplitude multi-sine "crackle" plus a
# small clamped jitter, per band, with a small phase stagger bottom-to-top
# so the glow reads as breathing outward rather than one flat pulse.
_EMBER_BREATHE_HZ = 0.45     # within the 0.3-0.6Hz range
_EMBER_BREATHE_AMP = 0.16    # +/-16% of base weight
_EMBER_CRACKLE_HZ = (2.3, 3.1, 3.7)   # incommensurate frequencies, ~2-4Hz
_EMBER_CRACKLE_AMP = 0.06    # +/-6% of base weight, summed across the 3 waves then scaled
_EMBER_JITTER_AMP = 0.02     # +/-2% small per-frame random jitter
_EMBER_PHASE_STAGGER = 0.35  # radians of phase offset per band, bottom leads


class Embers:
    """Particles spawn near the bottom, rise, and fade out before respawning
    — a spawn/rise/die lifecycle, not a persistent field. A dynamically
    recomputed ambient fire-glow wash (bottom-to-top bands, strongest at the
    bottom, each band's blend weight breathing/crackling over time) draws
    first, underneath the particles, same draw order as before."""

    motion_model = "lifecycle"

    def __init__(self, width: int, height: int, seed: int = 42) -> None:
        self._width = width
        self._usable_height = height - _HUD_MARGIN
        self._rng = random.Random(seed)
        self._time = 0.0

        self._embers: list[dict] = []
        for _ in range(60):
            self._embers.append(self._spawn(partial=True))

    def _spawn(self, partial: bool = False) -> dict:
        rng = self._rng
        lifespan = rng.uniform(2.0, 4.5)
        return {
            "x": rng.uniform(0.0, float(self._width)),
            "y0": rng.uniform(self._usable_height * 0.7, float(self._usable_height)),
            "rise": rng.uniform(40.0, 90.0),
            "sway_amp": rng.uniform(2.0, 8.0),
            "sway_speed": rng.uniform(0.5, 1.5),
            "phase": rng.uniform(0.0, math.tau),
            "lifespan": lifespan,
            "age": rng.uniform(0.0, lifespan) if partial else 0.0,
            "radius": rng.uniform(0.6, 1.8),
        }

    def update(self, dt: float) -> None:
        self._time += dt
        for i, e in enumerate(self._embers):
            e["age"] += dt
            if e["age"] >= e["lifespan"]:
                self._embers[i] = self._spawn()

    def _band_weight(self, band_index: int, base_weight: float) -> float:
        """Base weight modulated by a slow breathing sine, a faster
        low-amplitude multi-sine crackle, and small clamped jitter — the
        layered-noise fire-flicker technique, not one clean metronomic pulse
        and not unbounded randomness. `band_index` (0 = bottom) staggers the
        phase slightly per band for an outward-breathing feel."""
        phase_offset = band_index * _EMBER_PHASE_STAGGER
        t = self._time

        breathe = _EMBER_BREATHE_AMP * math.sin(
            t * _EMBER_BREATHE_HZ * math.tau + phase_offset
        )

        crackle = 0.0
        for hz in _EMBER_CRACKLE_HZ:
            crackle += math.sin(t * hz * math.tau + phase_offset)
        crackle = crackle / len(_EMBER_CRACKLE_HZ) * _EMBER_CRACKLE_AMP

        jitter = self._rng.uniform(-_EMBER_JITTER_AMP, _EMBER_JITTER_AMP)

        weight = base_weight * (1.0 + breathe + crackle) + jitter
        return max(0.0, min(_EMBER_BAND_MAX_WEIGHT, weight))

    def draw(self, surface: pygame.Surface) -> None:
        w = self._width
        h = self._usable_height

        # Bottom fire-glow wash first, particles rise on top of it — same
        # under-then-over ordering as the base fill in every other field.
        # Weights (and therefore colours) are recomputed fresh every frame —
        # no module-level precomputed constant survives this pass.
        for i, base_weight in enumerate(_EMBER_BASE_BAND_WEIGHTS):
            weight = self._band_weight(i, base_weight)
            colour = _lerp(_NIGHT_BG, _EMBER_GLOW, weight)
            y1 = max(0, h - i * _EMBER_BAND_HEIGHT)
            y0 = max(0, y1 - _EMBER_BAND_HEIGHT)
            if y1 <= y0:
                continue
            pygame.draw.rect(surface, colour, (0, y0, w, y1 - y0))

        for e in self._embers:
            life_frac = min(1.0, e["age"] / e["lifespan"])
            y = e["y0"] - e["rise"] * life_frac
            sway = math.sin(e["phase"] + e["age"] * e["sway_speed"] * math.tau) * e["sway_amp"]
            x = int((e["x"] + sway) % w)
            iy = int(y)
            if iy < 0:
                continue
            # Fade in fast, fade out over the back half of the lifespan.
            brightness = min(1.0, life_frac * 4.0) * (1.0 - life_frac) ** 0.6
            # Two-stage lerp: hot red-orange near spawn -> mid-orange ->
            # pale cool highlight as the ember rises and cools near the top.
            if life_frac < 0.5:
                r, g, b = _lerp(_EMBER_HOT, _EMBER_MID, life_frac / 0.5)
            else:
                r, g, b = _lerp(_EMBER_MID, _EMBER_COOL, (life_frac - 0.5) / 0.5)
            colour = (int(r * brightness), int(g * brightness), int(b * brightness))
            if e["radius"] <= 1.0:
                surface.set_at((x, iy), colour)
            else:
                pygame.draw.circle(surface, colour, (x, iy), max(1, int(round(e["radius"]))))


# ── Petals — drift_sway ──────────────────────────────────────────────────────

# Warmer, more saturated sakura pink family — anchored near #FFB7C5, not the
# old pale dusty pink.
_PETAL_COLOURS = [
    (255, 183, 197),   # sakura pink (anchor, ~#FFB7C5)
    (255, 160, 180),   # deeper, more saturated warm pink
    (255, 205, 215),   # lighter warm pink highlight
]

# Two glyph orientations stamped alternately, so it doesn't read as reskinned
# snow — a slight rotation-like flicker rather than a single dot per
# particle. Each carries a small V-notch/cleft at the outer tip — the
# sakura-specific shape cue that separates a cherry blossom petal from
# generic confetti.
_PETAL_A = (
    ".#.#.",
    "#####",
    "#####",
    ".###.",
)
_PETAL_B = (
    "#.#..",
    ".####",
    "####.",
    ".###.",
)


class Petals:
    """Falling petals with a wide, slow lateral sway and a slight
    rotation-like flicker between two glyph orientations."""

    motion_model = "drift_sway"

    def __init__(self, width: int, height: int, seed: int = 42) -> None:
        self._width = width
        self._usable_height = height - _HUD_MARGIN
        rng = random.Random(seed)

        self._petals: list[dict] = []
        for _ in range(40):
            self._petals.append({
                "x0": rng.uniform(0.0, float(width)),
                "y": rng.uniform(0.0, float(self._usable_height)),
                "fall_speed": rng.uniform(8.0, 20.0),
                "sway_amp": rng.uniform(18.0, 40.0),
                "sway_speed": rng.uniform(0.2, 0.6),
                "phase": rng.uniform(0.0, math.tau),
                "flicker_interval": rng.uniform(0.3, 0.7),
                "flicker_timer": rng.uniform(0.0, 0.7),
                "orient_a": True,
                "colour": rng.choice(_PETAL_COLOURS),
                "t": 0.0,
            })

    def update(self, dt: float) -> None:
        for p in self._petals:
            p["t"] += dt
            p["y"] += p["fall_speed"] * dt
            if p["y"] > self._usable_height:
                p["y"] -= self._usable_height
            p["flicker_timer"] += dt
            if p["flicker_timer"] >= p["flicker_interval"]:
                p["flicker_timer"] = 0.0
                p["orient_a"] = not p["orient_a"]

    def draw(self, surface: pygame.Surface) -> None:
        w, hgt = surface.get_size()
        for p in self._petals:
            sway = math.sin(p["phase"] + p["t"] * p["sway_speed"] * math.tau) * p["sway_amp"]
            ox = int((p["x0"] + sway) % w)
            oy = int(p["y"])
            glyph = _PETAL_A if p["orient_a"] else _PETAL_B
            for ry, row in enumerate(glyph):
                for rx, ch in enumerate(row):
                    if ch != "#":
                        continue
                    px, py = ox + rx, oy + ry
                    if 0 <= px < w and 0 <= py < hgt:
                        surface.set_at((px, py), p["colour"])


# ── Storm — strike_flash ─────────────────────────────────────────────────────

# direction_v16: Aurora's soft radial-gradient "nebula bloom" concept was
# retired after two structurally distinct constructions (linear curtains,
# then radial blobs) both failed the same human "doesn't read as an aurora"
# complaint — diagnosed as a concept/engine mismatch, not a tuning gap
# (see .bureau/contracts/direction_v16_field_aurora_replacement.md). Storm
# replaces it in the same `field_aurora` slot: hard-edged jagged lightning is
# exactly what opaque primitive-only draws render correctly, the same
# constraint that defeated a soft aurora glow.
_STORM_CLOUD_BASE = (32, 40, 56)     # muted slate-blue-grey cloud base, distinct from _NIGHT_BG
_STORM_STRIKE_FLASH = (66, 84, 112)  # whole-canvas flash lifted toward on a burst's FIRST bolt only.
                                     # ΔL vs base = 0.0656 < the WCAG 2.3.1 magnitude limb (0.10); fired at
                                     # burst cadence (<=~0.7/s) it clears the 3/s frequency limb too (direction_v18).
_STORM_BOLT_CORE = (255, 255, 255)   # overexposed pure-white bolt filament
_STORM_BOLT_HALO = (150, 176, 232)   # blue bloom drawn wider UNDER the core — the "white filament in a blue glow" look
_STORM_BOLT_FORK = (176, 200, 255)   # branch forks
# Drizzle must be SPARSE, not FAINT: window.py quantises the field by luminance,
# so a low-contrast drop lands in the cloud-base bucket and vanishes (measured
# 0/45 px survive at w=0.10 on true_silver/true_gold). Pre-blending the rain
# tint at w=0.35 against the cloud base clears the quantiser on every skin with
# margin; "light" then comes from how FEW and THIN the streaks are.
_STORM_DRIZZLE_TINT = (176, 200, 255)
_STORM_DRIZZLE = _lerp(_STORM_CLOUD_BASE, _STORM_DRIZZLE_TINT, 0.35)


class Storm:
    """Dark storm-cloud base with VIOLENT forked lightning arriving in bursts,
    over a continuous light drizzle (direction_v18).

    Bolts no longer arrive one at a time on a lazy timer: 1-3 strike in a tight
    burst (0.06-0.32s apart), bursts 1.4-3.2s apart — the clumping is what reads
    as violence. Each bolt SNAPS (near-instant attack, brief hold, squared
    decay) rather than blooming, has an overexposed pure-white core inside a
    wider blue halo, and forks more aggressively than before. On a burst's first
    bolt the whole canvas flashes once toward `_STORM_STRIKE_FLASH` — the "the
    sky lit up" punch, kept to burst cadence so it stays WCAG-compliant.

    A sparse light drizzle falls continuously behind the bolts. Unlike every
    other field, the lightning motion is still event-driven (bursts at random
    intervals); the drizzle is the one continuous layer."""

    motion_model = "strike_flash"

    # Burst scheduling — clumps, not a metronome.
    _BURST_GAP_MIN = 1.4      # seconds between bursts
    _BURST_GAP_MAX = 3.2
    _BURST_BOLTS_MIN = 1      # bolts per burst
    _BURST_BOLTS_MAX = 3
    _BOLT_GAP_MIN = 0.06      # seconds between bolts WITHIN a burst
    _BOLT_GAP_MAX = 0.32
    _BOLT_LIFE_MIN = 0.10     # snappier than the old 0.15-0.30
    _BOLT_LIFE_MAX = 0.18
    _FLASH_LIFE = 0.18        # whole-canvas flash duration (once per burst)

    # Drizzle — sparse on purpose. 90 drops is far under the contract's measured
    # 240-drop ceiling (~1.49us/drop), so the field stays the cheapest one.
    _DRIZZLE_COUNT = 90

    def __init__(self, width: int, height: int, seed: int = 42) -> None:
        self._width = width
        self._usable_height = height - _HUD_MARGIN
        self._rng = random.Random(seed)
        self._time = 0.0

        self._bolts: list[dict] = []
        # Burst state: how many bolts remain in the active burst, the size it
        # started at (so the FIRST bolt — which fires the flash — is
        # identifiable), and the two countdown timers.
        self._burst_bolts_left = 0
        self._burst_size = 0
        self._next_bolt_at = 0.0
        self._next_burst_at = self._rng.uniform(self._BURST_GAP_MIN, self._BURST_GAP_MAX)
        self._flash_age: float | None = None

        rng = self._rng
        self._drops: list[dict] = []
        for _ in range(self._DRIZZLE_COUNT):
            self._drops.append({
                "x": rng.uniform(0.0, float(width)),
                "y": rng.uniform(0.0, float(self._usable_height)),
                "speed": rng.uniform(180.0, 320.0),   # rain is fast
                "length": rng.uniform(4.0, 8.0),       # short 1px streaks
                "lean": rng.uniform(0.6, 1.8),         # near-vertical, slight lean
            })

    def _build_bolt(self) -> dict:
        """A single jagged bolt path via recursive midpoint displacement from
        a random top point down to a random bottom point, plus 2-4 short
        branch forks angling off partway down the main path (more, and more
        displaced, than the pre-v18 bolt)."""
        rng = self._rng
        w, h = self._width, self._usable_height
        top = (rng.uniform(w * 0.1, w * 0.9), 0.0)
        bottom = (rng.uniform(w * 0.1, w * 0.9), float(h))

        points = [top, bottom]
        # Midpoint displacement: repeatedly split every segment, offsetting
        # the new midpoint sideways by a shrinking random amount, so the path
        # reads as a jagged bolt rather than a straight line. v18 widens the
        # initial displacement (0.12w -> 0.16w) and slows the shrink
        # (0.5 -> 0.55) for a more ragged, aggressive path.
        displace = w * 0.16
        for _ in range(4):
            next_points = [points[0]]
            for i in range(len(points) - 1):
                (x0, y0), (x1, y1) = points[i], points[i + 1]
                mx = (x0 + x1) / 2.0 + rng.uniform(-displace, displace)
                my = (y0 + y1) / 2.0
                next_points.append((mx, my))
                next_points.append((x1, y1))
            points = next_points
            displace *= 0.55

        # 2-4 short branch forks, each starting from a point roughly in the
        # bolt's middle third and trailing off at a random angle.
        forks: list[list[tuple[float, float]]] = []
        for _ in range(rng.randint(2, 4)):
            idx = rng.randint(len(points) // 3, (len(points) * 2) // 3)
            fx, fy = points[idx]
            angle = rng.uniform(0.3, 1.2) * (1 if rng.random() < 0.5 else -1)
            length = rng.uniform(h * 0.08, h * 0.2)
            fork_pts = [(fx, fy)]
            steps = 3
            for s in range(1, steps + 1):
                seg_len = length * s / steps
                fx2 = fx + math.sin(angle) * seg_len + rng.uniform(-4.0, 4.0)
                fy2 = fy + math.cos(angle) * seg_len
                fork_pts.append((fx2, fy2))
            forks.append(fork_pts)

        return {
            "points": points,
            "forks": forks,
            "life": rng.uniform(self._BOLT_LIFE_MIN, self._BOLT_LIFE_MAX),
            "age": 0.0,
        }

    def update(self, dt: float) -> None:
        self._time += dt

        # Drizzle falls continuously; wrap to the top like Snow.
        h = self._usable_height
        for d in self._drops:
            d["y"] += d["speed"] * dt
            if d["y"] > h:
                d["y"] -= h

        # Age and cull bolts.
        for bolt in self._bolts:
            bolt["age"] += dt
        self._bolts = [b for b in self._bolts if b["age"] < b["life"]]

        # Age the whole-canvas flash.
        if self._flash_age is not None:
            self._flash_age += dt
            if self._flash_age >= self._FLASH_LIFE:
                self._flash_age = None

        # Burst scheduling. While a burst is active, fire its bolts at short
        # random gaps; otherwise count down to the next burst. The `while`
        # handles a dt large enough to release more than one bolt at once.
        if self._burst_bolts_left > 0:
            self._next_bolt_at -= dt
            while self._burst_bolts_left > 0 and self._next_bolt_at <= 0.0:
                is_first = self._burst_bolts_left == self._burst_size
                self._bolts.append(self._build_bolt())
                if is_first:
                    # ONE flash per burst, on the first bolt only — the
                    # frequency limb of WCAG 2.3.1 is what a per-bolt flash
                    # would breach (3 bolts in 0.32s = 3 flashes/s).
                    self._flash_age = 0.0
                self._burst_bolts_left -= 1
                if self._burst_bolts_left > 0:
                    self._next_bolt_at += self._rng.uniform(
                        self._BOLT_GAP_MIN, self._BOLT_GAP_MAX)
                else:
                    self._next_burst_at = self._rng.uniform(
                        self._BURST_GAP_MIN, self._BURST_GAP_MAX)
        else:
            self._next_burst_at -= dt
            if self._next_burst_at <= 0.0:
                self._burst_size = self._rng.randint(
                    self._BURST_BOLTS_MIN, self._BURST_BOLTS_MAX)
                self._burst_bolts_left = self._burst_size
                self._next_bolt_at = 0.0     # first bolt fires immediately

    @staticmethod
    def _bolt_envelope(bolt: dict) -> float:
        """SNAP, don't bloom: a near-instant attack over the first ~8% of
        life, a brief hold to 35%, then a squared decay. The old envelope spent
        a quarter of its life ramping in, which read as the bolt blooming into
        view rather than striking."""
        frac = bolt["age"] / bolt["life"]
        if frac < 0.08:
            return frac / 0.08
        if frac < 0.35:
            return 1.0
        decay = (frac - 0.35) / 0.65
        return max(0.0, (1.0 - decay) ** 2)

    def _flash_envelope(self) -> float:
        """Brief brighten-then-settle for the whole-canvas flash."""
        if self._flash_age is None:
            return 0.0
        frac = min(1.0, self._flash_age / self._FLASH_LIFE)
        return math.sin(frac * math.pi)

    def _clamp_point(self, x: float, y: float) -> tuple[int, int]:
        """Clamp a bolt/fork vertex strictly inside the field's own canvas —
        the midpoint-displacement construction (main path endpoints sit
        exactly on the top/bottom edge; fork lateral offsets can drift past
        either side) can otherwise place a vertex on or past the HUD-margin
        boundary or off either horizontal edge, the same class of geometry
        bug prior field rebuilds hit (see decision 032). Proof-by-construction
        fix: every drawn point is clamped here, so no per-bolt sampling proof
        is needed the way the curtain coverage fix needed one."""
        cx = min(max(int(x), 0), self._width - 1)
        cy = min(max(int(y), 0), self._usable_height - 1)
        return cx, cy

    def draw(self, surface: pygame.Surface) -> None:
        w = self._width
        h = self._usable_height

        base = _STORM_CLOUD_BASE
        flash_env = self._flash_envelope()
        if flash_env > 0.0:
            base = _lerp(_STORM_CLOUD_BASE, _STORM_STRIKE_FLASH, flash_env)

        pygame.draw.rect(surface, base, (0, 0, w, h))

        # Drizzle sits behind the bolts. Pre-blended constant colour (w=0.35)
        # so it survives the luminance quantiser on every skin; each drop is a
        # short, near-vertical 1px streak.
        for d in self._drops:
            x0 = int(d["x"])
            y0 = int(d["y"])
            x1 = int(d["x"] + d["lean"])
            y1 = int(d["y"] + d["length"])
            if y1 > h:
                y1 = h
            p0 = self._clamp_point(x0, y0)
            p1 = self._clamp_point(x1, y1)
            pygame.draw.line(surface, _STORM_DRIZZLE, p0, p1, 1)

        for bolt in self._bolts:
            env = self._bolt_envelope(bolt)
            if env <= 0.0:
                continue
            core_colour = _lerp(base, _STORM_BOLT_CORE, env)
            halo_colour = _lerp(base, _STORM_BOLT_HALO, env)
            fork_colour = _lerp(base, _STORM_BOLT_FORK, env)

            points = bolt["points"]
            clamped = [self._clamp_point(*p) for p in points]
            # Halo underneath (wider), then the white core on top — the
            # overexposed filament-in-a-glow look.
            for i in range(len(clamped) - 1):
                pygame.draw.line(surface, halo_colour, clamped[i], clamped[i + 1], 3)
            for i in range(len(clamped) - 1):
                pygame.draw.line(surface, core_colour, clamped[i], clamped[i + 1], 1)

            for fork_pts in bolt["forks"]:
                fclamped = [self._clamp_point(*p) for p in fork_pts]
                for i in range(len(fclamped) - 1):
                    pygame.draw.line(surface, fork_colour, fclamped[i], fclamped[i + 1], 1)


# ── Registry ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FieldSpec:
    id: str
    name: str
    blurb: str
    cls: type            # the class implementing __init__/update/draw
    motion_model: str
    cost: int = 0
    rarity_locked: bool = False


FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(id="field_stars", name="Starfield", blurb="Standard issue.",
              cls=Starfield, motion_model="twinkle", cost=0),
    FieldSpec(id="field_hearts", name="Hearts", blurb="Warm and a little sentimental.",
              cls=Hearts, motion_model="twinkle", cost=200),
    FieldSpec(id="field_skulls", name="Skulls", blurb="Friendly bones. Nothing to fear.",
              cls=Skulls, motion_model="fade_cycle", cost=200),
    FieldSpec(id="field_snow", name="Snow", blurb="Quiet, and always falling.",
              cls=Snow, motion_model="drift", cost=200),
    FieldSpec(id="field_embers", name="Embers", blurb="Rising light, never quite out.",
              cls=Embers, motion_model="lifecycle", cost=450),
    FieldSpec(id="field_petals", name="Petals", blurb="Drifting on a wind that isn't there.",
              cls=Petals, motion_model="drift_sway", cost=450),
    FieldSpec(id="field_aurora", name="Storm", blurb="Rain, and the sky breaking open.",
              cls=Storm, motion_model="strike_flash", cost=900, rarity_locked=True),
)

_BY_ID: dict[str, FieldSpec] = {f.id: f for f in FIELDS}
DEFAULT = FIELDS[0]


def get_field(field_id: str | None) -> FieldSpec:
    """Resolve a field id, falling back to the default. Tolerant like
    `skins.get()`: an unknown id from an old save must degrade quietly."""
    return _BY_ID.get(field_id or "", DEFAULT)


def purchasable_fields() -> tuple[FieldSpec, ...]:
    return tuple(f for f in FIELDS if f.cost > 0)


# Legendary substance gate: a legendary field's motion model must not be
# shared by any lower tier, or "legendary" means nothing (mirrors the
# rarity_locked check in skins.py's ScreenSkin/ShellSkin __post_init__).
_legendary_models = {f.motion_model for f in FIELDS if f.rarity_locked}
_other_models = {f.motion_model for f in FIELDS if not f.rarity_locked}
_clash = _legendary_models & _other_models
if _clash:
    raise ValueError(f"legendary field motion model(s) {_clash} reused by a lower tier")
