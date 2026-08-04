"""The eating animation — three sprite stages played next to the creature.

Clicking a food already mutates wallet + hunger instantly and atomically
(`actions.py::feed_item`) the moment the panel closes; that must stay true
even if this animation is interrupted or the window closes mid-play. This
object owns only the DISPLAY: which of the food's 3 consumption stages is
showing, and a "shown hunger" value eased from the pre-feed number toward the
already-final post-feed number, so the meter visibly climbs instead of
snapping. `creature.hunger` itself is never touched here — only what the
player sees while it plays.
"""
from __future__ import annotations

import pygame

from . import easing, fooditems, theme

STAGE_DUR = 0.53     # seconds each of the 3 sprite stages holds on screen
N_STAGES = 3


class EatAnimation:
    def __init__(self) -> None:
        self.food_id: str | None = None
        self._t = 0.0
        self._tweens = easing.Tweens()

    @property
    def playing(self) -> bool:
        return self.food_id is not None

    def start(self, food_id: str, hunger_before: float,
             hunger_after: float) -> None:
        """Begin playing. `hunger_after` is already the FINAL, committed
        value — this only animates what the player sees, never engine state.
        """
        self.food_id = food_id
        self._t = 0.0
        span = STAGE_DUR * N_STAGES * max(theme.ANIM_SCALE, 1e-6)
        self._tweens.clear()
        self._tweens.to("hunger", hunger_before, hunger_after, span,
                        easing.ease_out_cubic)

    def update(self, dt: float) -> None:
        if not self.playing:
            return
        self._t += dt
        self._tweens.update(dt)
        span = STAGE_DUR * N_STAGES * max(theme.ANIM_SCALE, 1e-6)
        if self._t >= span:
            self.food_id = None
            self._tweens.clear()

    def displayed_hunger(self, live_hunger: float) -> float:
        """The hunger value to SHOW — the live value once nothing is playing."""
        if not self.playing:
            return live_hunger
        return self._tweens.value("hunger", live_hunger)

    def stage(self) -> int:
        """Which of the 3 sprite stages (0, 1, 2) is currently showing."""
        span = STAGE_DUR * max(theme.ANIM_SCALE, 1e-6)
        return max(0, min(N_STAGES - 1, int(self._t / span)))

    def draw(self, inner: pygame.Surface, anchor: tuple[int, int],
            scale: int = 4) -> None:
        if not self.playing:
            return
        icon_px = fooditems.GRID * scale
        x, y = anchor
        fooditems.draw(inner, self.food_id, x - icon_px // 2, y - icon_px // 2,
                       scale, stage=self.stage())
