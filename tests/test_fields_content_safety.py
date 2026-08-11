"""tests/test_fields_content_safety.py — field content-safety verification.

Required gate from `.bureau/contracts/direction_v14_field_polish.md`: no
automated content-safety test existed for the Skulls field before this file
(confirmed by an earlier critic's search). Two checks, per the contract:

(a) STATIC — every colour Skulls' glyph is drawn with (found by introspecting
    `fields.py`'s source via AST rather than a hardcoded name list, so a
    future pass that adds e.g. a new brow-shading tone stays covered without
    editing this file) must read as neutral bone/grey: no red-channel
    dominance, channels reasonably close together (not a saturated single
    hue), and far from `theme.BITS` (the live currency HUD colour — no field
    may resemble it, per decision 031).

(b) RENDERED — actually draw Skulls onto a real (dummy-driver) pygame
    surface at production surface size and sample every distinct pixel
    colour that lands on it, then apply the same heuristic. This catches
    anything the static constant scan alone could miss: an inline literal
    colour never promoted to a named constant, a blend/lerp result, etc.

Both checks reuse the same `_assert_bone_safe` heuristic so "bone-toned" is
defined exactly once.

Extended per `.bureau/contracts/direction_v15_field_redesign.md` (three new
required gates, all in this same file so the bone-safe-style heuristics stay
colocated):

(c) Skulls' fade-in/hold/fade-out/reposition lifecycle (`motion_model`
    renamed `"blink"` -> `"fade_cycle"`) blends glyph colours toward the
    background as they fade, which is new surface area the original static/
    full-brightness rendered check never exercised. `TestSkullsFadeLifecycle`
    below drives `update()` across a long simulated run and samples many
    frames along the way (rather than driving the internal envelope
    directly, which is an implementation detail owned by the builder) so it
    naturally lands on a range of fade levels.

(d) Embers gets a brand-new bottom ambient fire-glow wash (pre-blended solid
    `pygame.draw.rect` bands, not a new saturated colour) with no prior
    content-safety coverage at all. `TestEmbersContentSafety` below checks
    the wash's rendered colours stay clear of a pure/blood-red and of
    `theme.BITS`, and that the wash is confined to the field's own bottom
    region rather than reading as a flat wash across the whole canvas.

(e) Aurora is rebuilt from per-column linear "curtain" gradients to per-blob
    *radial* gradients (`motion_model` renamed `"gradient_wash"` ->
    `"radial_bloom"`). `TestAuroraRadialGradient` below verifies this is a
    genuine colour-gradient change (not geometry-only) by sampling outward
    from the brightest point on the rendered canvas and confirming colour
    actually varies over several pixels rather than cutting to background
    instantly, and stays clear of `theme.BITS` throughout.

Extended per `.bureau/contracts/direction_v16_field_aurora_replacement.md`
(Aurora replaced entirely, Embers upgraded to a dynamic glow):

(f) Aurora is retired and replaced by `Storm` (`motion_model` renamed
    `"radial_bloom"` -> `"strike_flash"`) in the same `field_aurora` slot —
    a dark storm-cloud base with rare hard-edged jagged lightning bolts that
    flash in and fade out fast, plus occasional dim whole-canvas heat
    lightning. `TestStormContentSafety` below drives a long simulated run
    (long enough that multiple bolts and at least one heat-lightning pulse
    are near-certain to fire) and checks every rendered pixel across every
    sampled frame stays storm-toned (blue-grey/white-blue family, not a
    retired Aurora tone) and clear of `theme.BITS`.

(g) Embers' bottom glow, previously a `_EMBER_BAND_COLOURS` constant
    computed once at import time (confirmed zero per-frame variation), is
    now recomputed every frame from a breathing + crackle + jitter model.
    `TestEmbersContentSafety` is upgraded from a single static-render sample
    to multi-phase sampling across the pulse/crackle cycle (mirroring the
    `TestSkullsFadeLifecycle` precedent) so a peak-brightness moment is
    checked too, not just the average case.
"""
from __future__ import annotations

import ast
import inspect
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((1, 1))

from tokengotchi.renderer import fields  # noqa: E402
from tokengotchi.renderer import theme  # noqa: E402

RGB = tuple


def _is_rgb_tuple(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) == 3
        and all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in value)
    )


def _skulls_section_source() -> str:
    """The slice of `fields.py` from the Skulls section header up to the
    next section header, so any new module-level colour constant landing
    alongside the class (not just ones referenced by name inside its
    methods) stays in scope."""
    source = inspect.getsource(fields)
    start = source.index("# ── Skulls")
    try:
        end = source.index("# ── ", start + 1)
    except ValueError:
        end = len(source)
    return source[start:end]


def _skulls_colour_constants() -> dict[str, tuple[int, int, int]]:
    """Every colour Skulls' glyph is drawn with: module-level tuple
    constants assigned in the Skulls section (covers named constants like
    `_BONE`/`_SOCKET_DARK`/`_SOCKET_LIT`/`_NOSE` and any new one added
    alongside them, including ones nested inside a dict/list literal),
    plus any bare `Name` reference inside the `Skulls` class body that
    resolves to a module-level RGB tuple (covers reuse of a constant
    defined slightly outside the section boundary)."""
    section = _skulls_section_source()
    colours: dict[str, tuple[int, int, int]] = {}

    tree = ast.parse(section)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Tuple):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                continue
            if not _is_rgb_tuple(value):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    colours[target.id] = value
        elif isinstance(node, ast.Tuple):
            try:
                value = ast.literal_eval(node)
            except (ValueError, SyntaxError):
                continue
            if _is_rgb_tuple(value):
                colours.setdefault(f"<literal {value}>", value)

    class_node = next(
        n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "Skulls"
    )
    for node in ast.walk(class_node):
        if isinstance(node, ast.Name):
            value = getattr(fields, node.id, None)
            if _is_rgb_tuple(value):
                colours.setdefault(node.id, value)

    return colours


def _rgb_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _assert_bone_safe(name: str, rgb: tuple[int, int, int]) -> None:
    r, g, b = rgb
    assert not (r > g + 30 and r > b + 30), (
        f"{name}={rgb} reads as reddish (red channel dominates the other two) "
        "-- violates the non-gory skull checklist (no red, no blood)."
    )
    spread = max(r, g, b) - min(r, g, b)
    assert spread <= 50, (
        f"{name}={rgb} is too saturated / too single-channel (channel spread "
        f"{spread}) to read as a neutral bone/grey tone."
    )
    dist = _rgb_distance(rgb, theme.BITS)
    assert dist > 60, (
        f"{name}={rgb} is too close to theme.BITS={theme.BITS} (distance "
        f"{dist:.1f}) -- the live currency HUD colour every field must stay "
        "clear of."
    )


class TestSkullsContentSafetyStatic:
    """(a) -- every colour constant the Skulls glyph is drawn with."""

    def test_skull_glyph_colours_are_bone_toned(self):
        colours = _skulls_colour_constants()
        assert colours, "expected to find at least one Skulls colour constant"
        for name, rgb in colours.items():
            _assert_bone_safe(name, rgb)


class TestSkullsContentSafetyRendered:
    """(b) -- an actual rendered-pixel readback, not a visual guess."""

    def test_rendered_skulls_pixels_are_bone_toned(self):
        width, height = 348, 250
        fill_colour = (10, 10, 10)  # a colour no real field palette uses
        surface = pygame.Surface((width, height))
        surface.fill(fill_colour)

        skulls = fields.Skulls(width, height)
        # Several update/draw passes so both blink states (lit/dark sockets)
        # have a chance to land on the surface, not just whichever state
        # __init__ happened to randomise first.
        for _ in range(20):
            skulls.update(0.5)
            skulls.draw(surface)

        seen: set[tuple[int, int, int]] = set()
        for x in range(width):
            for y in range(height):
                pixel = surface.get_at((x, y))
                rgb = (pixel[0], pixel[1], pixel[2])
                if rgb != fill_colour:
                    seen.add(rgb)

        assert seen, "Skulls drew no pixels at all onto the surface"
        for rgb in seen:
            _assert_bone_safe(f"rendered pixel {rgb}", rgb)


class TestSkullsFadeLifecycle:
    """(c) -- direction_v15's required gate: the new fade-in/hold/fade-out/
    reposition lifecycle must be sampled at multiple fade-envelope levels,
    not just full brightness, since blended intermediate colours (glyph
    colour lerped toward the background) are new surface area this pass
    introduces.

    We don't know (and shouldn't couple to) the builder's internal envelope
    API, so instead of driving fade state directly this runs a long
    simulated duration -- long enough to cover several full lifecycles per
    the contract's ~0.6s fade-in + ~2.5-4.5s hold + ~0.6s fade-out envelope
    (staggered per-skull so they don't all sync) -- and samples rendered
    pixels at many points along the way. That naturally lands on a range of
    fade levels without needing to know the exact internal implementation.
    """

    def test_fade_lifecycle_pixels_stay_bone_safe_across_many_frames(self):
        width, height = 348, 250
        fill_colour = (10, 10, 10)  # a colour no real field palette uses
        surface = pygame.Surface((width, height))

        skulls = fields.Skulls(width, height)
        dt = 1.0 / 30.0
        total_frames = 300  # a simulated 10s run at 30 FPS
        sample_every = 15   # 20 sampled frames spread across the run

        per_frame_max_brightness: list[int] = []

        for frame in range(total_frames):
            skulls.update(dt)
            if frame % sample_every != 0:
                continue

            surface.fill(fill_colour)
            skulls.draw(surface)

            frame_max_brightness = 0
            for x in range(width):
                for y in range(height):
                    rgb = surface.get_at((x, y))[:3]
                    if rgb == fill_colour:
                        continue
                    _assert_bone_safe(f"frame {frame} pixel {rgb}", rgb)
                    frame_max_brightness = max(frame_max_brightness, sum(rgb))
            per_frame_max_brightness.append(frame_max_brightness)

        assert any(b > 0 for b in per_frame_max_brightness), (
            "Skulls drew no pixels at all across the whole sampled run"
        )

        # The fade lifecycle should produce genuinely varying brightness
        # levels across the sampled frames (fade-in ramping up, fade-out
        # ramping down, and legitimately fully-dark/faded-out frames in
        # between) -- not a statically fully-lit glyph every single frame,
        # which is what the retired static "blink" behaviour effectively
        # was for the glyph body (only the eyes toggled).
        distinct_levels = set(per_frame_max_brightness)
        assert len(distinct_levels) > 1, (
            "every sampled frame had the exact same max-brightness value "
            f"({distinct_levels}) across a 10s simulated run -- expected the "
            "fade-in/hold/fade-out lifecycle to produce varying brightness "
            "levels over time, not a static full-brightness render."
        )


# ── Embers ───────────────────────────────────────────────────────────────────

_EMBER_TEST_SIZE = (348, 250)  # matches device.SCREEN_W/SCREEN_H
_EMBER_FILL_COLOUR = (10, 10, 10)  # a colour no real field palette uses


def _render_embers(frames: int = 30):
    width, height = _EMBER_TEST_SIZE
    surface = pygame.Surface((width, height))
    surface.fill(_EMBER_FILL_COLOUR)

    embers = fields.Embers(width, height)
    for _ in range(frames):
        embers.update(1.0 / 30.0)
        embers.draw(surface)

    return surface, width, height


class TestEmbersContentSafety:
    """direction_v15's required gate: no automated content-safety coverage
    existed for Embers before this pass. The new bottom ambient fire-glow
    wash is a pre-blended solid colour (weighted average of `_EMBER_HOT`/
    `_EMBER_MID` against the dark background) -- this must (a) never drift
    toward a new, pure/near-blood-red, (b) stay clear of `theme.BITS`, and
    (c) stay confined to the field's own bottom usable-height region rather
    than reading as a flat wash across the whole canvas."""

    def test_ember_wash_pixels_avoid_pure_red_and_bits(self):
        surface, width, height = _render_embers()

        seen: set[tuple[int, int, int]] = set()
        for x in range(width):
            for y in range(height):
                rgb = surface.get_at((x, y))[:3]
                if rgb != _EMBER_FILL_COLOUR:
                    seen.add(rgb)

        assert seen, "Embers drew no pixels at all onto the surface"
        for rgb in seen:
            r, g, b = rgb
            assert not (r > 180 and g < 60 and b < 60), (
                f"pixel {rgb} reads as a near-pure/blood red -- the bottom "
                "ember wash must stay a pre-blended tone within the existing "
                "hot/mid ember family, not drift toward a new saturated red."
            )
            dist = _rgb_distance(rgb, theme.BITS)
            assert dist > 60, (
                f"pixel {rgb} is too close to theme.BITS={theme.BITS} "
                f"(distance {dist:.1f}) -- the live currency HUD colour "
                "every field must stay clear of."
            )

    def test_ember_wash_confined_to_bottom_region(self):
        surface, width, height = _render_embers()
        usable_height = height - fields._HUD_MARGIN

        def _row_non_background_fraction(y: int) -> float:
            hits = 0
            for x in range(width):
                if surface.get_at((x, y))[:3] != _EMBER_FILL_COLOUR:
                    hits += 1
            return hits / width

        top_y = 2                       # well above the bottom ~60-80px band
        bottom_y = usable_height - 5    # inside the bottom wash band region

        top_frac = _row_non_background_fraction(top_y)
        bottom_frac = _row_non_background_fraction(bottom_y)

        assert bottom_frac > 0.8, (
            f"expected the bottom ambient glow band to cover most of row "
            f"y={bottom_y} (near the bottom of the usable field height "
            f"{usable_height}), but only {bottom_frac:.0%} of pixels there "
            "were non-background."
        )
        assert top_frac < 0.2, (
            f"row y={top_y}, near the TOP of the field, is {top_frac:.0%} "
            "non-background -- the ember wash must fade out with height and "
            "stay confined near the bottom, not paint a flat wash across the "
            "whole canvas."
        )


class TestEmbersDynamicGlowMultiPhase:
    """(g) -- direction_v16's required gate: the bottom glow's blend weight
    is now recomputed every frame (breathing + crackle + jitter), replacing
    the retired `_EMBER_BAND_COLOURS` module-level constant. Mirrors the
    `TestSkullsFadeLifecycle` precedent: rather than driving the internal
    weight formula directly (an implementation detail owned by the
    builder), this runs a long simulated duration covering several full
    breathing/crackle cycles and samples rendered pixels at many points
    along the way, so a peak-brightness moment is checked too, not just one
    static render."""

    def test_bottom_row_colour_varies_and_stays_safe_across_many_frames(self):
        width, height = _EMBER_TEST_SIZE
        surface = pygame.Surface((width, height))

        embers = fields.Embers(width, height)
        dt = 1.0 / 30.0
        total_frames = 300   # a simulated 10s run at 30 FPS -- several breathing cycles at ~0.3-0.6Hz
        sample_every = 5     # 60 sampled frames spread across the run

        usable_height = height - fields._HUD_MARGIN
        bottom_row = usable_height - 2  # inside the bottom-most glow band every frame

        seen_bottom_colours: set[tuple[int, int, int]] = set()

        for frame in range(total_frames):
            embers.update(dt)
            if frame % sample_every != 0:
                continue

            surface.fill(_EMBER_FILL_COLOUR)
            embers.draw(surface)

            for x in range(0, width, 4):  # stride for speed; still many samples per frame
                rgb = surface.get_at((x, bottom_row))[:3]
                if rgb == _EMBER_FILL_COLOUR:
                    continue
                r, g, b = rgb
                assert not (r > 180 and g < 60 and b < 60), (
                    f"frame {frame} pixel {rgb} on the bottom glow row reads "
                    "as a near-pure/blood red -- the dynamic weight must stay "
                    "clamped within a sane range, never strobing into a new "
                    "saturated red."
                )
                dist = _rgb_distance(rgb, theme.BITS)
                assert dist > 60, (
                    f"frame {frame} pixel {rgb} is too close to "
                    f"theme.BITS={theme.BITS} (distance {dist:.1f})."
                )
                seen_bottom_colours.add(rgb)

        assert len(seen_bottom_colours) > 1, (
            "the bottom glow row rendered the exact same colour "
            f"({seen_bottom_colours}) across a 10s simulated run with many "
            "sampled frames -- expected the breathing/crackle/jitter model "
            "to produce genuinely varying weight over time, not a static "
            "precomputed constant."
        )


# ── Storm ────────────────────────────────────────────────────────────────────

class TestStormContentSafety:
    """(f) -- direction_v16's required gate, updated for direction_v18: Aurora
    is retired and replaced by Storm (dark storm-cloud base, VIOLENT forked
    lightning arriving in bursts, a once-per-burst whole-canvas flash, over a
    continuous light drizzle) in the same `field_aurora` slot. Bursts fire
    every ~1.4-3.2s, so a short render is likely to show only the base fill and
    drizzle -- this drives a long simulated run (several burst intervals) so at
    least one strike is near-certain, and samples every distinct rendered pixel
    across many frames (mirroring the `TestSkullsFadeLifecycle` multi-frame
    precedent) rather than a single static render."""

    @staticmethod
    def _rgb_dominant_channel_check(name: str, rgb: tuple[int, int, int]) -> None:
        r, g, b = rgb
        # Storm's whole palette (cloud base, strike flash, bolt core/halo/fork,
        # drizzle) is a blue-grey/white-blue family: blue is never the weakest
        # channel, and red never dominates the way a warm palette (embers,
        # retired Aurora pink/violet-on-black highlights) would. Pure white
        # (the overexposed bolt core) is exempt -- r==g==b breaches nothing.
        assert b >= r - 20, (
            f"{name}={rgb} has red dominating blue -- Storm's palette must "
            "read as blue-grey/white-blue (storm/lightning), not a warm tone."
        )
        dist = _rgb_distance(rgb, theme.BITS)
        assert dist > 60, (
            f"{name}={rgb} is too close to theme.BITS={theme.BITS} "
            f"(distance {dist:.1f}) -- the live currency HUD colour every "
            "field must stay clear of."
        )

    def test_storm_pixels_stay_blue_grey_and_clear_of_bits_across_many_frames(self):
        width, height = 348, 250
        fill_colour = (255, 0, 255)  # a colour no real field palette uses
        surface = pygame.Surface((width, height))

        storm = fields.Storm(width, height)
        dt = 1.0 / 30.0
        total_frames = 900   # a simulated 30s run -- several bolt intervals and at least one heat pulse
        sample_every = 10

        max_brightness_seen = 0
        distinct_colours: set[tuple[int, int, int]] = set()

        for frame in range(total_frames):
            storm.update(dt)
            if frame % sample_every != 0:
                continue

            surface.fill(fill_colour)
            storm.draw(surface)

            for x in range(0, width, 3):       # stride for speed
                for y in range(0, height - fields._HUD_MARGIN, 3):
                    rgb = surface.get_at((x, y))[:3]
                    if rgb == fill_colour:
                        continue
                    self._rgb_dominant_channel_check(f"frame {frame} pixel {rgb}", rgb)
                    distinct_colours.add(rgb)
                    max_brightness_seen = max(max_brightness_seen, sum(rgb))

        assert distinct_colours, "Storm drew no pixels at all across the whole sampled run"

        # Over a long enough run, at least one bolt or heat-lightning pulse
        # should have fired and pushed brightness well above the flat cloud
        # base -- otherwise this test would quietly pass even if bolts never
        # fire at all.
        assert max_brightness_seen > 250, (
            "expected at least one lightning bolt or heat-lightning pulse to "
            f"brighten the canvas over a 30s simulated run; brightest pixel "
            f"sum seen was only {max_brightness_seen}."
        )

        # The base fill alone is a single flat colour; bolts/heat-lightning
        # should introduce genuine variation across the sampled run.
        assert len(distinct_colours) > 1, (
            f"only one distinct colour ({distinct_colours}) rendered across "
            "the whole sampled run -- expected bolts/heat-lightning to "
            "introduce colour variation over time."
        )

    def test_storm_strike_flash_is_wcag_compliant(self):
        """direction_v18 accessibility resolution: the whole-canvas strike
        flash must clear BOTH limbs of WCAG 2.3.1.

        Magnitude limb: the flash colour's relative-luminance rise over the
        cloud base must stay under 0.10. Frequency limb: the flash fires once
        per burst (on the first bolt only), not once per bolt, so flashes never
        exceed 3 in any one second even during a dense 3-bolt burst.
        """
        def rel_lum(rgb):
            def lin(c):
                c /= 255.0
                return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            r, g, b = rgb
            return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

        delta = rel_lum(fields._STORM_STRIKE_FLASH) - rel_lum(fields._STORM_CLOUD_BASE)
        assert delta < 0.10, (
            f"strike flash luminance rise {delta:.4f} breaches WCAG 2.3.1 "
            "magnitude limb (0.10)"
        )

        # Frequency limb: count flash ONSETS per rolling one-second window over
        # a long run. A flash onset is the frame `_flash_age` resets to 0.
        width, height = 348, 250
        storm = fields.Storm(width, height)
        dt = 1.0 / 30.0
        onsets: list[float] = []
        prev_age = storm._flash_age
        t = 0.0
        for _ in range(1800):        # 60s simulated
            storm.update(dt)
            t += dt
            age = storm._flash_age
            if age is not None and (prev_age is None or age < prev_age):
                onsets.append(t)
            prev_age = age

        assert onsets, "no strike flash fired over a 60s run -- test proves nothing"
        # No one-second window may hold more than 3 onsets.
        for i, start in enumerate(onsets):
            in_window = [o for o in onsets[i:] if o - start < 1.0]
            assert len(in_window) <= 3, (
                f"{len(in_window)} strike flashes within 1s starting at "
                f"{start:.2f}s -- breaches WCAG 2.3.1 frequency limb (3/s)"
            )

    def test_storm_confined_to_usable_height(self):
        width, height = 348, 250
        fill_colour = (255, 0, 255)
        surface = pygame.Surface((width, height))
        surface.fill(fill_colour)

        storm = fields.Storm(width, height)
        dt = 1.0 / 30.0
        for _ in range(900):
            storm.update(dt)
        storm.draw(surface)

        usable_height = height - fields._HUD_MARGIN
        for x in range(width):
            for y in range(usable_height, height):
                rgb = surface.get_at((x, y))[:3]
                assert rgb == fill_colour, (
                    f"pixel ({x}, {y}) at y={y} is below the usable height "
                    f"{usable_height} (inside the HUD margin) but Storm drew "
                    f"a non-background colour {rgb} there."
                )
