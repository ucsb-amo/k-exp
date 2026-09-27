"""Dashboard registry entries for the Camera Viewer: ids stay ``basler`` (saved
dashboard layouts refer to them), labels are the new ones, and kexp's panel
module is a shim of the waxx panels.  The MOT viewer keeps its own layout."""
from __future__ import annotations


def _spec(specs, spec_id):
    hits = [s for s in specs if s.id == spec_id]
    assert len(hits) == 1, [s.id for s in specs]
    return hits[0]


def test_registry_ids_and_labels():
    from kexp.util.dashboard.client_registry import CLIENT_SPECS
    from kexp.util.dashboard.server_registry import SERVER_SPECS
    server = _spec(SERVER_SPECS, "basler")
    client = _spec(CLIENT_SPECS, "basler")
    assert server.label == "Basler server · Camera Viewer"
    assert client.label == "Camera Viewer"
    assert not any(s.label == "Basler Cameras" for s in list(SERVER_SPECS) + list(CLIENT_SPECS))


def test_the_kexp_panel_is_the_waxx_panel():
    from kexp.util.guis.basler import basler_panel
    from waxx.util.guis.camera_viewer import camera_viewer_panel as p
    assert basler_panel.BaslerServerPanel is p.CameraViewerServerPanel
    assert basler_panel.BaslerClientPanel is p.CameraViewerClientPanel


def test_mot_viewer_uses_its_own_layout():
    from kexp.util.guis.mot_viewer import mot_viewer

    made = {}

    class Recorder:
        def __init__(self, **kw):
            made.update(kw)

        def setWindowTitle(self, title):
            made["title"] = title

    mot_viewer.make_viewer(Recorder)
    assert made == {"serial_filter": ["40277706"], "auto_open": True,
                    "layout_key": "mot_viewer", "title": "MOT Viewer"}
