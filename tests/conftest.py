"""k-exp test session set-up.

Import the three packages before any test module imports waxx.util.device_state: before the
2026-10-10 fix, that package put the LIVE %code%\\k-exp at sys.path[0] on import, so a top-level
``kexp`` resolved after it was the live tree even with PYTHONPATH on a worktree -- tests then
silently exercised the wrong code. Resolving them first pins them to whatever PYTHONPATH says.
"""
import kexp  # noqa: F401
import waxa  # noqa: F401
import waxx  # noqa: F401
import pytest


@pytest.fixture(autouse=True)
def _queue_gate_never_reaches_the_real_queue(monkeypatch):
    """A warm-launched process's queue_gate asks the monitor server for GO by
    discovery -- on kong that is the live server.  A test that gets that far
    without its own stand-in (``queue_gate.set_transport``) fails at once
    instead of polling the live server."""
    from waxx.util.device_state import queue_gate

    def no_real_transport():
        transport = queue_gate._state["transport"]
        if transport is None:
            pytest.fail("a test reached for the real run queue through queue_gate; "
                        "give it a stand-in with queue_gate.set_transport(...)")
        return transport
    monkeypatch.setattr(queue_gate, "_transport", no_real_transport)
