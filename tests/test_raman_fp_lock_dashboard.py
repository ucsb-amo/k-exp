"""The Raman FP lock is wired into both dashboards: registry entries, layout,
COM label from ip.py, the panel builds (offscreen, against a stub client that
never connects), and the launcher module imports without starting anything.
"""
from __future__ import annotations

import importlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_registry_and_layout_entries():
    from kexp.config.ip import RAMAN_FP_LOCK_COM
    from kexp.util.dashboard import client_registry, dashboard_layout, dashboard_hosts, server_registry
    from kexp.util.guis.lasers.raman_fp_lock import SERVER_ID

    spec = server_registry.get_spec("raman_fp_lock")
    assert spec.server_id == SERVER_ID and spec.com_label == RAMAN_FP_LOCK_COM == "COM35"
    assert spec.server_cmd[1:] == ["-m", "kexp.util.guis.lasers.raman_fp_lock.raman_fp_lock_server"]
    assert client_registry.get_spec("raman_fp_lock") is not None
    for table in (dashboard_layout.SERVER_PLACEMENT, dashboard_layout.CLIENT_PLACEMENT,
                  dashboard_layout.AUTO_LAYOUT_HINTS):
        assert "raman_fp_lock" in table
    # not autostarted anywhere: starting it takes the port from a person's terminal
    assert all("raman_fp_lock" not in ids for ids in dashboard_hosts.HOST_AUTOSTART_SERVERS.values())
    # the TPI server is told about the port (it waits only for TPI-like ports)
    tpi = server_registry.get_spec("tpi")
    assert f"{RAMAN_FP_LOCK_COM}=raman_fp_lock" in tpi.server_cmd


def test_launcher_imports_without_side_effects():
    mod = importlib.import_module("kexp.util.guis.lasers.raman_fp_lock.raman_fp_lock_server")
    assert callable(mod.main)


def test_panel_builds_without_a_server():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from kexp.util.guis.lasers.raman_fp_lock import raman_fp_lock_panel as rp

    class _NoServer:
        timeout = 1.0

        def get_snapshot(self):
            raise OSError("no server (stub)")

    panel = rp.FPLockPanel("raman_fp_lock", title="Raman FP lock", client=_NoServer())
    panel._poller.stop()
    assert panel._pill.text().startswith("connecting")
    assert not panel._lock_btn.isEnabled()
    panel.cleanup()
    panel.deleteLater()
    assert issubclass(rp.RamanFPLockPanel, rp.FPLockPanel)
