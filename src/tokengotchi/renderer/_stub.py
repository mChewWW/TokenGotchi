"""Stub game state for testing the renderer independently.

Provides a StubGameState with duck-typed attributes matching what GameWindow
expects. Use this to validate rendering without depending on the engine
implementation.

Usage:
    from tokengotchi.renderer._stub import StubGameState
    from tokengotchi.renderer import GameWindow

    state = StubGameState()
    window = GameWindow()
    while not window.should_quit():
        actions = window.render_frame(state, show_privacy=False)
        window.tick()
    window.close()
"""
from __future__ import annotations

import math
import time


class _StubCreature:
    """Minimal creature object with all attributes the renderer reads."""

    def __init__(self) -> None:
        self.stage: str = "adult"         # "egg" | "baby" | "adult"
        self.hunger: float = 0.75         # 0.0–1.0
        self.hat_slot: str | None = None  # None | "hat_a" | "hat_b"
        self.dormancy_start: float | None = None  # Unix timestamp or None


class _StubWallet:
    """Minimal wallet with BITS and ECHOES balances."""

    def __init__(self) -> None:
        self.bits: int = 42
        self.echoes: int = 7


class StubGameState:
    """Duck-typed game state stub for renderer testing.

    Cycle through all stages and hats automatically for visual QA.
    Set StubGameState.auto_cycle = False to freeze at initial values.

    Attributes:
        creature: Stub creature (stage, hunger, hat_slot, dormancy_start).
        wallet:   Stub wallet (bits, echoes).
        auto_cycle: If True, animates hunger and cycles hats over time.
    """

    def __init__(self, auto_cycle: bool = True) -> None:
        self.creature = _StubCreature()
        self.wallet = _StubWallet()
        self.auto_cycle = auto_cycle
        self._start_time = time.monotonic()

    def update(self) -> None:
        """Call each frame to animate the stub state (optional convenience)."""
        if not self.auto_cycle:
            return

        elapsed = time.monotonic() - self._start_time

        # Oscillate hunger between 0.05 and 0.95 over 20 seconds
        self.creature.hunger = 0.5 + 0.45 * math.sin(elapsed * 2 * math.pi / 20)

        # Cycle through stages every 8 seconds
        stage_idx = int(elapsed // 8) % 3
        self.creature.stage = ["egg", "baby", "adult"][stage_idx]

        # Cycle through hats every 4 seconds
        hat_idx = int(elapsed // 4) % 3
        self.creature.hat_slot = [None, "hat_a", "hat_b"][hat_idx]

        # Toggle dormancy briefly (last 2s of every 12s cycle)
        phase = elapsed % 12
        self.creature.dormancy_start = time.time() if phase > 10 else None
