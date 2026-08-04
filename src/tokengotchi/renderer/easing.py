"""Easing curves and a minimal tween, for time-based UI motion.

Pure functions over a normalised t in [0, 1]. Penner-derived. No dependency —
a tween library would be more machinery than this needs.

Everything is driven by elapsed *seconds*, never by frame count, so a dropped
frame does not slow an animation down.
"""
from __future__ import annotations

import math
from typing import Callable

# Overshoot constant. 1.70158 is the value that puts the peak at exactly 1.10,
# i.e. a 10% overshoot. Larger = bouncier; 0 degenerates to plain cubic.
_BACK_S = 1.70158


def linear(t: float) -> float:
    return t


def ease_out_cubic(t: float) -> float:
    """The default for anything appearing, moving or fading."""
    return 1.0 - (1.0 - t) ** 3


def ease_in_cubic(t: float) -> float:
    """Exits. Motion accelerating away reads as dismissal."""
    return t * t * t


def ease_in_out_cubic(t: float) -> float:
    return 4 * t * t * t if t < 0.5 else 1.0 - ((-2 * t + 2) ** 3) / 2


def ease_out_back(t: float) -> float:
    """Overshoots then settles. Panel entrances and button release."""
    return 1.0 + (_BACK_S + 1) * (t - 1) ** 3 + _BACK_S * (t - 1) ** 2


def ease_out_quad(t: float) -> float:
    return 1.0 - (1.0 - t) * (1.0 - t)


def shake_offset(elapsed: float, duration: float,
                 amplitude: float = 4.0, freq: float = 26.0) -> float:
    """Decaying horizontal shake. Not an easing curve — a displacement.

    Used to reject an unaffordable purchase. Applied to the *card only*:
    full-window shake on an always-on-top desktop pet would be unpleasant and
    is a motion-sickness trigger.
    """
    if elapsed >= duration or duration <= 0:
        return 0.0
    decay = 1.0 - (elapsed / duration)
    return math.sin(elapsed * freq) * amplitude * decay


class Tween:
    """One scalar animating from a to b over dur seconds."""

    __slots__ = ("a", "b", "dur", "ease", "delay", "t", "_done_cb", "fired")

    def __init__(self, a: float, b: float, dur: float,
                 ease: Callable[[float], float] = ease_out_cubic,
                 delay: float = 0.0, on_done: Callable[[], None] | None = None):
        self.a = a
        self.b = b
        self.dur = max(1e-6, dur)
        self.ease = ease
        self.delay = delay
        self.t = 0.0
        self._done_cb = on_done
        self.fired = False

    def update(self, dt: float) -> None:
        self.t += dt
        if not self.fired and self.t >= self.delay + self.dur:
            self.fired = True
            if self._done_cb:
                self._done_cb()

    @property
    def done(self) -> bool:
        return self.t >= self.delay + self.dur

    @property
    def value(self) -> float:
        u = (self.t - self.delay) / self.dur
        u = max(0.0, min(1.0, u))
        return self.a + (self.b - self.a) * self.ease(u)


class Tweens:
    """A tiny keyed tween group.

    Starting a tween on a key that already has one REPLACES it. Without that,
    rapid clicking stacks conflicting tweens on the same property and the
    value jitters.
    """

    def __init__(self) -> None:
        self._items: dict[str, Tween] = {}

    def set(self, key: str, tween: Tween) -> None:
        self._items[key] = tween

    def to(self, key: str, a: float, b: float, dur: float,
           ease: Callable[[float], float] = ease_out_cubic,
           delay: float = 0.0) -> None:
        self._items[key] = Tween(a, b, dur, ease, delay)

    def value(self, key: str, default: float = 0.0) -> float:
        tw = self._items.get(key)
        return default if tw is None else tw.value

    def has(self, key: str) -> bool:
        return key in self._items

    def update(self, dt: float) -> None:
        for tw in list(self._items.values()):
            tw.update(dt)

    def clear(self) -> None:
        self._items.clear()

    def drop_finished(self) -> None:
        for k in [k for k, v in self._items.items() if v.done]:
            del self._items[k]
