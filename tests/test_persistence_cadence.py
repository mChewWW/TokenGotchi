"""Persistence cadence.

Saving on EVERY frame is untenable: ~30 JSON serialisations plus temp-file
write-and-rename per second, roughly 2.6M temp files a day for a 648-byte
file. Measured at 3.92ms against 0.92ms for the whole render — four times the
cost of drawing the game — and it multiplies exposure to the Windows rename
race by ~100x. So writes are debounced and heartbeated instead.
"""
from __future__ import annotations

import threading

from tokengotchi.engine.state_manager import GameState, StateManager
from tokengotchi.main import SAVE_DEBOUNCE, SAVE_HEARTBEAT, _AppState

FPS = 30


def _simulate(seconds: float, dirty_every: float | None = None) -> int:
    """Run the save decision over N seconds of frames; return the write count."""
    app = _AppState(GameState())
    saves = 0
    for frame in range(int(seconds * FPS)):
        t = frame / FPS
        if dirty_every and frame and frame % int(dirty_every * FPS) == 0:
            app.mark_dirty()
        if app.should_save(t):
            saves += 1
            app.mark_saved(t)
    return saves


class TestCadence:
    def test_idle_is_not_a_write_storm(self):
        """60s idle: one heartbeat, not 1800 writes."""
        assert _simulate(60.0) <= 2, "idle session is still writing per-frame"

    def test_idle_still_checkpoints(self):
        """Lazy must not mean never — an idle session still persists."""
        assert _simulate(130.0) >= 2

    def test_active_session_is_bounded(self):
        """A click every 10s must not produce 300 writes."""
        assert _simulate(60.0, dirty_every=10.0) <= 12

    def test_first_frame_persists(self):
        """Startup state must reach disk without waiting for the heartbeat."""
        app = _AppState(GameState())
        assert app.should_save(SAVE_DEBOUNCE + 0.01)

    def test_change_is_flushed_promptly(self):
        app = _AppState(GameState())
        app.mark_saved(100.0)
        assert not app.should_save(100.1), "must debounce, not write instantly"
        app.mark_dirty()
        assert not app.should_save(100.1)
        assert app.should_save(100.0 + SAVE_DEBOUNCE + 0.01)

    def test_clean_state_waits_for_the_heartbeat(self):
        app = _AppState(GameState())
        app.mark_saved(100.0)
        assert not app.should_save(100.0 + SAVE_HEARTBEAT - 1.0)
        assert app.should_save(100.0 + SAVE_HEARTBEAT + 0.1)

    def test_mark_saved_clears_dirty(self):
        app = _AppState(GameState())
        app.mark_dirty()
        app.mark_saved(50.0)
        assert not app.should_save(50.0 + SAVE_DEBOUNCE + 0.01), \
            "a saved state must not immediately want saving again"


class TestConcurrentWrites:
    """The Windows rename race under same-process contention.

    Contention is serialised by a module lock rather than retried through:
    retry-only fails ~1 run in 6 under load.
    """

    def test_many_threads_no_errors(self, tmp_path):
        state_file = tmp_path / "state.json"
        StateManager(state_path=state_file).load()
        errors: list[Exception] = []

        def loop():
            mgr = StateManager(state_path=state_file)
            st = mgr.load()
            for _ in range(60):
                try:
                    mgr.save(st)
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

        threads = [threading.Thread(target=loop) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == [], f"concurrent write errors: {errors[:3]}"

    def test_file_valid_after_contention(self, tmp_path):
        import json

        state_file = tmp_path / "state.json"
        StateManager(state_path=state_file).load()

        def loop():
            mgr = StateManager(state_path=state_file)
            st = mgr.load()
            for _ in range(40):
                mgr.save(st)

        threads = [threading.Thread(target=loop) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        parsed = json.loads(state_file.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)
        assert "wallet" in parsed

    def test_no_temp_files_left_behind(self, tmp_path):
        state_file = tmp_path / "state.json"
        mgr = StateManager(state_path=state_file)
        st = mgr.load()
        for _ in range(30):
            mgr.save(st)
        leftovers = list(tmp_path.glob(".state_*.tmp"))
        assert leftovers == [], f"temp files leaked: {leftovers}"
