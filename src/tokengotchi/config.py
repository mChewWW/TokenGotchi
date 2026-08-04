"""Centralised configuration constants for TokenGotchi.

All tuneable values live here so that tests and the main loop can import from
one place rather than hard-coding literals.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------

#: Path to the Claude Code stats cache written by the CLI.
STATS_CACHE_PATH: Path = Path.home() / ".claude" / "stats-cache.json"

#: Directory where TokenGotchi persists its own state.
STATE_DIR: Path = Path.home() / ".tokengotchi"

#: Full path to the JSON state file.
STATE_PATH: Path = STATE_DIR / "state.json"

# ---------------------------------------------------------------------------
# Window / display
# ---------------------------------------------------------------------------

WINDOW_WIDTH: int = 400
WINDOW_HEIGHT: int = 450
FPS: int = 30
ALWAYS_ON_TOP: bool = False

# ---------------------------------------------------------------------------
# Economy ratios
# ---------------------------------------------------------------------------

#: Number of output tokens required to earn 1 BITS.
BITS_RATIO: int = 500

#: Number of cache tokens (read + creation) required to earn 1 ECHO.
ECHOES_RATIO: int = 100000
