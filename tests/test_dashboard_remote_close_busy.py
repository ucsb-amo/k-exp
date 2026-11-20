"""The server dashboard's remote-close rule (machine_busy_reason): a run_gate
verdict other than free / held refuses.  A fake assess: nothing on the network
is asked."""
import pytest

from waxx.util.device_state.run_gate import STATES, GateState


def _reason(state):
    from kexp.util.dashboard.server_dashboard_app import machine_busy_reason
    return machine_busy_reason(
        assess=lambda timeout: GateState(state, 123, f"why {state}"))


@pytest.mark.parametrize("state", STATES)
def test_only_free_and_held_let_a_close_through(state):
    reason = _reason(state)
    if state in ("free", "held"):
        assert reason is None
    else:
        assert reason is not None and state in reason and f"why {state}" in reason


def test_a_failing_assess_raises_so_the_control_server_counts_it_busy():
    from kexp.util.dashboard.server_dashboard_app import machine_busy_reason

    def boom(timeout):
        raise RuntimeError("no monitor")
    with pytest.raises(RuntimeError):
        machine_busy_reason(assess=boom)
