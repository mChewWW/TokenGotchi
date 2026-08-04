"""Legibility gate, measured on a rendered frame instead of asserted at import.

This lives here rather than in `ShellSkin.__post_init__` deliberately, and the
reason is the whole point of the gate.

A constructor check can only see declared colours, not composited pixels. The
only way to satisfy one is to drop the read-out onto an opaque plate — which
ruins the illusion of a moulded screen, letting a convenience for the test
select the design.

A render-time harness has no such gravity. It samples what the player actually
sees, which means translucent cases and Joy-Con's two-tone seam are ordinary
inputs rather than arguments for covering the text up. It also catches the
class of bug a constructor check certifies as GREEN: text drawn on `lo`
while the assertion measures `body`.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pygame

pygame.init()
pygame.display.set_mode((1, 1), pygame.HIDDEN)

from tokengotchi.renderer import device, ink, theme  # noqa: E402
from tokengotchi.renderer.skins import SHELLS  # noqa: E402

W, H = 400, 450
NUMERAL_FLOOR = 45.0     # relief carries the rest; see ink.py
CAPTION_FLOOR = 45.0
SWATCH_FLOOR = 25.0      # a shape, not a glyph -- far more tolerant
SEP_FLOOR = ink.MIN_SEPARATION

fails: list[str] = []
print(f"{'case':16}{'BITS':>9}{'Lc':>7}{'ECHOES':>9}{'Lc':>7}{'sep':>7}")
for s in SHELLS:
    surf = pygame.Surface((W, H))
    device.draw_shell(surf, s)
    cy = H - 74
    row = []
    for x, val, label, anchor in ((34, 1284, "BITS", theme.BITS),
                                  (162, 90, "ECHOES", theme.ECHOES)):
        probe = pygame.Rect(x + 18, cy + 2, 60, 20)
        bgs = device.sample_bg(surf, probe)
        col = device.ink_for(tuple(anchor), bgs)
        lc = min(ink.legibility(col, b) for b in bgs)
        row.append((col, lc))
        device.draw_currency(surf, x, cy, val, label, anchor, shell=s)
        # The swatch is deliberately NEVER adapted -- it is the one element
        # that keeps gold meaning BITS on every case, which is what licenses
        # the numeral to move. That exemption still needs a gate: on a gold
        # case the swatch measures 0.0 Lc unless the ramp puts a flat mid-tone
        # under the read-out. It is a solid 12px shape rather than a glyph, so
        # it tolerates far less contrast than lettering -- but not none.
        # Scored edge-against-rim, not fill-against-case: the dot is seated
        # in a rim derived from ink.relief(), which is the same geometry the
        # lettering uses, so ink.legibility() measures the actual edge.
        sw = min(ink.legibility(anchor, b) for b in bgs)
        if sw < SWATCH_FLOOR:
            fails.append(f"{s.id}: {label} swatch Lc {sw:.1f} < {SWATCH_FLOOR}")
        if lc < NUMERAL_FLOOR:
            fails.append(f"{s.id}: {label} numeral Lc {lc:.1f} < {NUMERAL_FLOOR}")

    sep = ink.separation(row[0][0], row[1][0])
    if sep < SEP_FLOOR:
        fails.append(f"{s.id}: BITS and ECHOES are {sep:.3f} apart "
                     f"(< {SEP_FLOOR}) — the two currencies look the same")
    print(f"{s.name:16}#{row[0][0][0]:02x}{row[0][0][1]:02x}{row[0][0][2]:02x}"
          f"{row[0][1]:7.1f}  #{row[1][0][0]:02x}{row[1][0][1]:02x}"
          f"{row[1][0][2]:02x}{row[1][1]:7.1f}{sep:7.3f}")

# The relief must remain visible against the case, or the geometry that is
# doing the actual reading is not there.
for s in SHELLS:
    for bg in filter(None, (s.body, s.body_right, s.lo)):
        d, l = ink.relief(bg)
        for tap, which in ((d, "shadow"), (l, "highlight")):
            if abs(ink.apca(tap, bg)) < ink.MIN_RELIEF_LC - 0.5:
                fails.append(f"{s.id}: relief {which} invisible on {bg} "
                             f"({abs(ink.apca(tap, bg)):.1f} Lc)")

if fails:
    print("\nFAIL")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print(f"\nOK — {len(SHELLS)} cases legible, no opaque plate")
