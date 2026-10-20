"""k-exp test session set-up.

Import the three packages before any test module imports waxx.util.device_state: before the
2026-10-10 fix, that package put the LIVE %code%\\k-exp at sys.path[0] on import, so a top-level
``kexp`` resolved after it was the live tree even with PYTHONPATH on a worktree -- tests then
silently exercised the wrong code. Resolving them first pins them to whatever PYTHONPATH says.
"""
import kexp  # noqa: F401
import waxa  # noqa: F401
import waxx  # noqa: F401
