"""Diagnostic viewer as a client-dashboard panel."""

from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout

from waxx.util.dashboard.embed_helpers import WidgetPanelBase


class DiagnosticViewerPanel(WidgetPanelBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        from kexp.util.guis.diagnostic_viewer.window import DiagnosticViewer  # noqa: PLC0415

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._viewer = DiagnosticViewer(parent=self)
        lay.addWidget(self._viewer)

    def cleanup(self) -> None:
        self._viewer.shutdown()
        super().cleanup()


__all__ = ["DiagnosticViewerPanel"]
