"""renderer/fields.py — the background particle-field cosmetics.

Field-specific coverage that doesn't belong in test_shop_panel.py's
catalogue-vs-renderer drift guards: the legendary substance gate (a
FIELD-kind equivalent of skins.py's rarity_locked enforcement, which had no
counterpart until this kind existed) and a smoke test that every field
actually runs its update/draw cycle against a real surface.
"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((1, 1))

from tokengotchi.renderer import fields  # noqa: E402


class TestLegendarySubstanceGate:
    def test_legendary_field_motion_is_structurally_unique(self):
        """A legendary field must move differently from every lower tier, or
        'legendary' means nothing (mirrors ScreenSkin/ShellSkin's
        rarity_locked gate in skins.py, which has no field-level equivalent
        otherwise)."""
        legendary_models = {f.motion_model for f in fields.FIELDS if f.rarity_locked}
        other_models = {f.motion_model for f in fields.FIELDS if not f.rarity_locked}
        assert legendary_models, "expected at least one rarity_locked field"
        assert not (legendary_models & other_models)


class TestFieldsRender:
    def test_every_field_updates_and_draws_without_error(self):
        """Every field.FIELDS entry must actually instantiate and run
        update()/draw() against a real (dummy-driver) pygame surface — the
        renderer-side counterpart to test_hats_have_a_drawing_function."""
        surface = pygame.Surface((200, 300))
        for spec in fields.FIELDS:
            instance = spec.cls(200, 300)
            instance.update(0.1)
            instance.draw(surface)
