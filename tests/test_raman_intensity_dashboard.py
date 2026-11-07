"""The Raman intensity PID is wired into both dashboards: registry entries,
layout, COM label from ip.py, kong autostart, the panel builds (offscreen,
against a stub client that never connects), the launcher and the CLI import
without starting anything.
"""
from __future__ import annotations

import importlib
import io
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_registry_and_layout_entries():
    from kexp.config.ip import RAMAN_INTENSITY_COM
    from kexp.util.dashboard import client_registry, dashboard_hosts, dashboard_layout, server_registry
    from kexp.util.guis.lasers.raman_intensity import SERVER_ID

    spec = server_registry.get_spec("raman_intensity")
    assert spec.server_id == SERVER_ID and spec.com_label == RAMAN_INTENSITY_COM == "COM16"
    assert spec.server_cmd[1:] == ["-m", "kexp.util.guis.lasers.raman_intensity.raman_intensity_server"]
    assert client_registry.get_spec("raman_intensity") is not None
    for table in (dashboard_layout.SERVER_PLACEMENT, dashboard_layout.CLIENT_PLACEMENT,
                  dashboard_layout.AUTO_LAYOUT_HINTS):
        assert "raman_intensity" in table
    assert "raman_intensity" in dashboard_hosts.HOST_AUTOSTART_SERVERS["192.168.1.76"]
    assert "raman_intensity" not in dashboard_hosts.HOST_AUTOSTART_SERVERS["*"]
    # the TPI server is told the port belongs to this server
    tpi = server_registry.get_spec("tpi")
    assert f"{RAMAN_INTENSITY_COM}=raman_intensity" in tpi.server_cmd


def test_launcher_and_cli_import_without_side_effects():
    mod = importlib.import_module("kexp.util.guis.lasers.raman_intensity.raman_intensity_server")
    assert callable(mod.main)
    from kexp.util.guis.lasers.raman_intensity import cli
    from waxx.util.guis.intensity_pid import intensity_pid_cli

    def no_server():
        raise RuntimeError("no beacon (stub)")

    out = io.StringIO()
    assert intensity_pid_cli.main(["status"], server_id="raman_intensity",
                                  client_factory=no_server, out=out) == 3
    assert callable(cli.main)


def test_panel_builds_without_a_server():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from kexp.util.guis.lasers.raman_intensity import LOOP_NAMES
    from kexp.util.guis.lasers.raman_intensity import raman_intensity_panel as rp

    class _NoServer:
        timeout = 1.0

        def get_snapshot(self):
            raise OSError("no server (stub)")

    panel = rp.IntensityPIDPanel("raman_intensity", title="Raman intensity", loop_names=LOOP_NAMES,
                                 client=_NoServer())
    panel._poller.stop()
    assert panel._pill.text().startswith("connecting")
    assert not panel._hold_btn.isEnabled()
    panel.cleanup()
    panel.deleteLater()
    assert issubclass(rp.RamanIntensityPanel, rp.IntensityPIDPanel)
