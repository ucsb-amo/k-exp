"""Monitor & device-state panels.

* :class:`MonitorPanel`        - the Server Dashboard's monitor panel: the run
  queue, the monitor state and the monitor experiment's status button, from
  the headless monitor server over the network
  (``waxx.util.guis.monitor_panel.MonitorServerPanel``; no server in this
  process).
* :class:`MonitorClientPanel`  - client-side panel embedding ``DeviceStateGUI``
  (the wide device-control window the lab actually interacts with).

Names follow the dashboard registries: server registry imports
``MonitorPanel``; client registry imports ``MonitorClientPanel``.
"""

from __future__ import annotations

from waxx.util.dashboard.embed_helpers import WidgetPanelBase, embed_main_window


def _slm_kwargs() -> dict:
    """The SLM pill's "Launch spot finder" (kexp...slm_tools); a failure
    costs that menu item only."""
    import logging  # noqa: PLC0415
    try:
        from kexp.util.guis.device_state_gui.slm_tools import launch_spot_finder  # noqa: PLC0415
    except Exception:
        logging.getLogger(__name__).exception(
            "SLM tools failed to load; the SLM pill has no spot finder launcher.")
        return {}
    return {"spot_finder_launcher": launch_spot_finder}


def _composite_kwargs(dds, dac) -> dict:
    """The Composite tab's definitions (kexp.config.composite_devices), its
    scenes, the monitor's connections (the tab's connection bar), what their
    readbacks need, and the read-only telemetry (kexp...telemetry_providers);
    and the SLM pill's spot finder launcher (_slm_kwargs).  A failure here
    costs the tab (or only the measured values, or the launcher), not the
    whole GUI."""
    import logging  # noqa: PLC0415
    log = logging.getLogger(__name__)
    try:
        from types import SimpleNamespace  # noqa: PLC0415
        from kexp.config.composite_devices import COMPOSITE_DEVICES, COMPOSITE_SCENES  # noqa: PLC0415
        from kexp.config.monitor_connections import MONITOR_CONNECTIONS  # noqa: PLC0415
        from kexp.config.expt_params import ExptParams  # noqa: PLC0415
        kwargs = {"composite_devices": COMPOSITE_DEVICES,
                  "composite_scenes": COMPOSITE_SCENES,
                  "composite_connections": MONITOR_CONNECTIONS,
                  "composite_params": ExptParams(),
                  "composite_frames": SimpleNamespace(dds=dds, dac=dac)}
    except Exception:
        log.exception("Composite device definitions failed to load; the Composite tab is off.")
        return _slm_kwargs()
    try:
        from waxx.util.device_state.telemetry import TelemetryHub  # noqa: PLC0415
        from kexp.util.guis.device_state_gui.telemetry_providers import default_providers  # noqa: PLC0415
        kwargs["composite_telemetry"] = TelemetryHub(default_providers())
    except Exception:
        log.exception("Telemetry providers failed to load; the cards show no measured values.")
    kwargs.update(_slm_kwargs())
    return kwargs


#: liveOD belongs on kong (the run cameras are there; experiments connect to
#: whichever liveOD beacons): Start liveOD refuses on any other PC.
LIVE_OD_HOST_IP = "192.168.1.76"


def live_od_bat() -> str:
    """kexp's liveOD launcher, ``kexp/_bat/live_od.bat``."""
    from pathlib import Path  # noqa: PLC0415
    import kexp  # noqa: PLC0415
    return str(Path(kexp.__file__).resolve().parent / "_bat" / "live_od.bat")


def live_od_host_refusal(resolve=None):
    """A ``refusal()`` for Start liveOD: "" on kong, why not elsewhere.  The
    PC's lab IP is looked up once (``resolve() -> ip | None``; default the
    dashboard's ``host_config.resolve_host_ip``)."""
    cache: dict = {}

    def refusal() -> str:
        if "ip" not in cache:
            try:
                if resolve is None:
                    from waxx.util.dashboard.host_config import resolve_host_ip  # noqa: PLC0415
                    cache["ip"] = resolve_host_ip()
                else:
                    cache["ip"] = resolve()
            except Exception:                         # noqa: BLE001
                cache["ip"] = None
        ip = cache["ip"]
        if ip == LIVE_OD_HOST_IP:
            return ""
        return (f"liveOD runs on kong ({LIVE_OD_HOST_IP}); this PC is "
                f"{ip or 'not on the lab subnet'}. Start it there.")
    return refusal


def _live_od_kwargs() -> dict:
    """Start liveOD for the Monitor panel: the launcher and the kong-only
    refusal.  A missing launcher costs the button only."""
    import logging  # noqa: PLC0415
    import os  # noqa: PLC0415
    try:
        bat = live_od_bat()
    except Exception:
        logging.getLogger(__name__).exception("No liveOD launcher: the Monitor panel has no "
                                              "Start liveOD button.")
        return {}
    if not os.path.isfile(bat):
        logging.getLogger(__name__).warning("No liveOD launcher at %s: the Monitor panel has "
                                            "no Start liveOD button.", bat)
        return {}
    return {"live_od_bat": bat, "live_od_refusal": live_od_host_refusal()}


class MonitorPanel(WidgetPanelBase):
    """The Server Dashboard's monitor panel (registry id ``monitor``): the
    headless monitor server's run queue, state and monitor-experiment button,
    over the network (waxx ``MonitorServerPanel``), with Start liveOD running
    ``kexp/_bat/live_od.bat`` (:func:`_live_od_kwargs`; on kong only).  It used
    to embed a whole ``MonitorServerGUI`` -- a second monitor server in the
    dashboard's own process; nothing used that, and the dashboard runs the
    server headless.  ``panel_factory`` builds the body (tests pass one over a
    fake client)."""

    def __init__(self, parent=None, panel_factory=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QVBoxLayout  # noqa: PLC0415
        if panel_factory is None:
            from waxx.util.guis.monitor_panel import MonitorServerPanel  # noqa: PLC0415
            from waxx.util.guis.run_queue_panel import panel_settings  # noqa: PLC0415
            # the queue table's columns and filter are remembered on this PC
            panel_factory = lambda: MonitorServerPanel(  # noqa: E731
                settings=panel_settings(), **_live_od_kwargs())
        self._panel = panel_factory()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._panel)

    def cleanup(self) -> None:
        """The dashboard's teardown: the panel's poll, listener and worker."""
        self._panel.cleanup()
        super().cleanup()


class MonitorClientPanel(WidgetPanelBase):
    """Client-side device-state control panel (wide)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from waxx.util.guis.device_control_gui import DeviceStateGUI  # noqa: PLC0415
        # Avoid heavy ARTIQ hardware imports at module load time by deferring.
        # Instantiate the frames (both default to DummyCore — no hardware needed)
        # so that DDSWidget/DACWidget can look up default values via hasattr().
        try:
            from kexp.config.dac_id import dac_frame as _dac_frame_cls  # noqa: PLC0415
            from kexp.config.dds_id import dds_frame as _dds_frame_cls  # noqa: PLC0415
            dac = _dac_frame_cls()
            dds = _dds_frame_cls(dac_frame_obj=dac)
        except Exception:
            dds = None
            dac = None

        self._gui = DeviceStateGUI(
            dds_frame=dds,
            dac_frame=dac,
            **_composite_kwargs(dds, dac),
        )
        # Embedded directly (no scroll area), so the panel's minimum size is
        # the size that fits every channel card: the dock cannot be shrunk
        # to where cards would be clipped or squeezed.  The Composite tab
        # scrolls on its own inside the GUI.
        embed_main_window(self, self._gui)


__all__ = ["MonitorPanel", "MonitorClientPanel"]
