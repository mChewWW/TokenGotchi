"""Animated starfield background drawn procedurally with pygame."""
from __future__ import annotations
import math
import random

import pygame

# Colour palette for stars
STAR_COLOURS = [
    (220, 225, 255),  # blue-white (most common, ~60%)
    (255, 255, 240),  # warm white (~20%)
    (180, 200, 255),  # cool blue (~10%)
    (255, 230, 180),  # warm yellow (~10%)
]

# Cumulative weights for colour selection
_COLOUR_WEIGHTS = [0.60, 0.80, 0.90, 1.00]


def _pick_colour(rng: random.Random) -> tuple[int, int, int]:
    """Pick a star colour using the weighted palette."""
    r = rng.random()
    for i, threshold in enumerate(_COLOUR_WEIGHTS):
        if r <= threshold:
            return STAR_COLOURS[i]
    return STAR_COLOURS[-1]


class Starfield:
    """Manages and draws an animated field of twinkling stars."""

    def __init__(self, width: int, height: int, seed: int = 42) -> None:
        self._width = width
        self._height = height
        self._time: float = 0.0

        rng = random.Random(seed)

        # Stars avoid the bottom 140px (HUD + shop area)
        usable_height = height - 140

        self._stars: list[dict] = []
        for _ in range(120):
            base_radius = rng.uniform(0.5, 2.5)
            is_glint = rng.random() < 0.08
            star = {
                "x": rng.uniform(0.0, float(width)),
                "y": rng.uniform(0.0, float(usable_height)),
                "base_radius": base_radius,
                "brightness": 1.0,  # updated each frame
                "base_brightness": rng.uniform(0.4, 1.0),
                "twinkle_speed": rng.uniform(0.3, 2.0),
                "twinkle_phase": rng.uniform(0.0, math.tau),
                "is_glint": is_glint,
                "colour_tint": _pick_colour(rng),
            }
            self._stars.append(star)

    def update(self, dt: float) -> None:
        """Advance twinkle animations. dt = seconds since last update."""
        self._time += dt
        t = self._time
        for star in self._stars:
            phase = star["twinkle_phase"] + t * star["twinkle_speed"] * math.tau
            star["brightness"] = star["base_brightness"] * (0.5 + 0.5 * math.sin(phase))

    def draw(self, surface: pygame.Surface) -> None:
        """Draw all stars onto surface."""
        for star in self._stars:
            b = star["brightness"]
            r_base, g_base, b_base = star["colour_tint"]
            colour = (
                int(r_base * b),
                int(g_base * b),
                int(b_base * b),
            )
            ix = int(star["x"])
            iy = int(star["y"])
            radius = star["base_radius"]

            if radius <= 1.0:
                # Single pixel
                surface.set_at((ix, iy), colour)
            else:
                # Medium circle
                draw_radius = max(1, int(round(radius)))
                pygame.draw.circle(surface, colour, (ix, iy), draw_radius)

            if star["is_glint"]:
                self._draw_glint(surface, ix, iy, colour, b)

    def _draw_glint(
        self,
        surface: pygame.Surface,
        cx: int,
        cy: int,
        colour: tuple[int, int, int],
        brightness: float,
    ) -> None:
        """Draw a cross-glint (horizontal + vertical lines) through a star."""
        arm_len = 3  # pixels each side (total span 6-7px)
        glint_surf = pygame.Surface((arm_len * 2 + 1, arm_len * 2 + 1), pygame.SRCALPHA)
        glint_surf.fill((0, 0, 0, 0))

        centre = arm_len  # centre pixel offset within glint_surf

        r, g, b_val = colour
        # Draw horizontal arm with fade from centre outward
        for dx in range(-arm_len, arm_len + 1):
            fade = 1.0 - abs(dx) / (arm_len + 1)
            alpha = int(255 * brightness * fade)
            glint_surf.set_at((centre + dx, centre), (r, g, b_val, alpha))

        # Draw vertical arm with fade from centre outward
        for dy in range(-arm_len, arm_len + 1):
            fade = 1.0 - abs(dy) / (arm_len + 1)
            alpha = int(255 * brightness * fade)
            glint_surf.set_at((centre, centre + dy), (r, g, b_val, alpha))

        surface.blit(glint_surf, (cx - arm_len, cy - arm_len))
