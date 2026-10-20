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
