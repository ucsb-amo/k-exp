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
def _run_queue_dir_is_temporary(monkeypatch, tmp_path):
    """The development machine is the lab PC (kong), whose live run queue
    keeps its files in ~/.waxx/run_queue: every test points the queue's
    default folder -- and the folders it runs files from (the defaults are
    the live code tree and the agents' log folder) -- at its own temporary
    folder (as wax/waxx-src/tests/conftest.py does)."""
    monkeypatch.setenv("WAXX_RUN_QUEUE_DIR", str(tmp_path / "run_queue_default"))
    monkeypatch.setenv("WAXX_RUN_QUEUE_ROOTS", str(tmp_path))


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


class _OfflineCameraDirectory:
    """No camera server on the network: what a test gets in place of the
    process's shared beacon CameraDirectory, so nothing asks kong's real
    camera servers (BaslerParams.prepare_for_run reads the exposure delay)."""
    def find(self, query, *, refresh=False):
        from beacon.camera.directory import CameraNotFound
        raise CameraNotFound(f"offline test: the camera servers are not asked ({query!r})")

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _no_shared_camera_directory(monkeypatch):
    import waxx.control.cameras.camera_stream_client as csc
    monkeypatch.setattr(csc, "shared_camera_directory", _OfflineCameraDirectory)


@pytest.fixture(autouse=True)
def _no_beacon_is_ever_broadcast(monkeypatch):
    """kong runs the real servers: a test server that beaconed its id
    (interlock, ...) could take requests meant for the real one."""
    from beacon.discovery import server as dserver
    monkeypatch.setattr(dserver.NetServer, "_start_beacon", lambda self: None)
