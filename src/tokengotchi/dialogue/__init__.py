"""Dialogue content and scheduling — the creature's hunger-driven speech.

Layered per direction contract v17, in dependency order:

  * `lines.py`         — the general pool, keyed by hunger band. Asserts only
                         hunger, mood and the need to be fed, so it is true
                         whenever its band is true and needs no gate.
  * `context_lines.py` — pools that may say sharper things, paired with
                         `context.py`, which proves the claim before one is
                         allowed to speak.
  * `event_lines.py` /
    `moment_lines.py`  — reactions to something that just happened. True by
                         construction; fired by the call site, not the timer.
  * `scheduler.py`     — cadence and repeat avoidance across all of the above.
                         Owns no opinion about what is true.

Re-exported here so callers outside the package import the gate and the
scheduler from one place rather than reaching into individual modules.
"""
from .context import (
    DIALOGUE_ABANDONED_HOURS,
    DIALOGUE_DEEP_DROUGHT_HOURS,
    DIALOGUE_DROUGHT_HOURS,
    DIALOGUE_LULL_MINUTES,
    context_pool,
    resolve_context,
    tone_group,
)
from .scheduler import DialogueScheduler

__all__ = [
    "DIALOGUE_ABANDONED_HOURS",
    "DIALOGUE_DEEP_DROUGHT_HOURS",
    "DIALOGUE_DROUGHT_HOURS",
    "DIALOGUE_LULL_MINUTES",
    "DialogueScheduler",
    "context_pool",
    "resolve_context",
    "tone_group",
]
