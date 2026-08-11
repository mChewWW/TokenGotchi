"""Field performance gate — MEASURE `fields.py` draw cost, don't estimate it.

`.bureau/contracts/direction_v14_field_polish.md` calls this out explicitly:
30 FPS is capped by `clock.tick`, not proven to have headroom, and Skulls'
enlarged glyph (5x5 -> 9x9) plus Aurora's rebuild from 5 horizontal bands to
~12-14 independently-swaying vertical curtains are exactly the kind of
change that can quietly blow the per-frame budget without a human noticing
in a live 30 FPS run.

For every `FieldSpec` in `fields.FIELDS`, this instantiates the class at the
same size `window.py` actually uses (`WINDOW_W`/`WINDOW_H`), then runs
`update(dt)` + `draw(surface)` for `FRAMES` frames (300 = a simulated 10s at
30 FPS) against a surface sized like the real on-screen device recess
(`device.SCREEN_W`/`SCREEN_H`), and prints the measured average per-frame
draw+update cost against a generous per-field budget.

This is a standalone script, not a pytest test: wall-clock timing assertions
are flaky in CI (machine load, thermal throttling, etc.), so this is meant
to be run on demand by a human or the verify team, not gated automatically.

    python scripts/verify_field_perf.py

Exits non-zero if any field's average exceeds the budget.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

pygame.init()
pygame.display.set_mode((1, 1))

from tokengotchi.renderer import device as devicemod  # noqa: E402
from tokengotchi.renderer import fields  # noqa: E402
from tokengotchi.renderer import window as windowmod  # noqa: E402

FRAMES = 300          # a simulated 10s run at 30 FPS
DT = 1.0 / 30.0
BUDGET_MS = 5.0        # generous: total frame budget at 30 FPS is ~33ms, and
                       # several fields plus the pet plus UI all share it


def _measure(spec) -> float:
    """Average per-frame update()+draw() cost in milliseconds."""
    surface = pygame.Surface((devicemod.SCREEN_W, devicemod.SCREEN_H))
    instance = spec.cls(windowmod.WINDOW_W, windowmod.WINDOW_H)

    start = time.perf_counter()
    for _ in range(FRAMES):
        instance.update(DT)
        instance.draw(surface)
    elapsed = time.perf_counter() - start

    return (elapsed / FRAMES) * 1000.0


def main() -> int:
    print(
        f"Measuring {len(fields.FIELDS)} field(s) over {FRAMES} frames "
        f"(simulated {FRAMES * DT:.0f}s @ 30 FPS), "
        f"instance size {windowmod.WINDOW_W}x{windowmod.WINDOW_H}, "
        f"draw surface {devicemod.SCREEN_W}x{devicemod.SCREEN_H}.\n"
    )

    any_over_budget = False
    rows: list[tuple[str, str, float, str]] = []
    for spec in fields.FIELDS:
        avg_ms = _measure(spec)
        status = "PASS" if avg_ms <= BUDGET_MS else "WARN"
        if status == "WARN":
            any_over_budget = True
        rows.append((spec.id, spec.name, avg_ms, status))

    id_w = max(len(r[0]) for r in rows)
    name_w = max(len(r[1]) for r in rows)
    for field_id, name, avg_ms, status in rows:
        print(
            f"{status:4s}  {field_id:<{id_w}s}  {name:<{name_w}s}  "
            f"{avg_ms:7.4f} ms/frame  (budget {BUDGET_MS:.1f} ms)"
        )

    print()
    worst = max(rows, key=lambda r: r[2])
    print(f"Worst field: {worst[1]} ({worst[0]}) at {worst[2]:.4f} ms/frame.")
    print(
        f"For context, the total frame budget at 30 FPS is "
        f"~{1000.0 / 30.0:.2f} ms, shared with the pet sprite, UI, and shell "
        "chrome."
    )

    if any_over_budget:
        print(
            "\nRESULT: WARN -- one or more fields exceeded the "
            f"{BUDGET_MS:.1f}ms per-field budget. Investigate before "
            "shipping the larger glyphs/curtain count."
        )
        return 1

    print(f"\nRESULT: PASS -- every field stays comfortably under {BUDGET_MS:.1f}ms/frame.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
