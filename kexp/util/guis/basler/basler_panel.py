"""Basler cameras panel - now the Camera Viewer panel from waxx.

Kept under its old path and names because the dashboard registries (id
``basler``) and saved dashboard layouts refer to them.  The panels embed
beacon's ``CameraViewerMainWindow``; each dashboard side keeps its own saved
camera layout.
"""

from __future__ import annotations

from waxx.util.guis.camera_viewer.camera_viewer_panel import (
    CameraViewerClientPanel as BaslerClientPanel,
    CameraViewerServerPanel as BaslerServerPanel,
)

__all__ = ["BaslerServerPanel", "BaslerClientPanel"]
