"""Remote Control client panel - embeds RemoteControlGUI with a RemoteControl controller."""

from __future__ import annotations

from waxx.util.dashboard.embed_helpers import WidgetPanelBase, embed_main_window


class RemoteControlPanel(WidgetPanelBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        from kexp.util.remote_control.remote_control import RemoteControl  # noqa: PLC0415
        from kexp.util.remote_control.remote_control_gui import RemoteControlGUI  # noqa: PLC0415

        self._controller = RemoteControl()
        self._gui = RemoteControlGUI(self._controller)
        embed_main_window(self, self._gui)


__all__ = ["RemoteControlPanel"]
