"""Client dashboard application entry point.

Run::

    python -m kexp.util.dashboard.client_dashboard_app
        [--host-ip 192.168.1.76]
        [--include id1,id2] [--exclude id1,id2]

The client dashboard does NOT start any subprocesses; it only embeds client
widgets that talk to remote servers (which are managed by the server
dashboard on the lab control PC).  Panels whose body_factory fails to
import or instantiate appear as ErrorBodyWidgets so the rest of the
dashboard remains usable.
"""

from __future__ import annotations

import argparse
import logging
import sys

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from kexp.util.dashboard.client_registry import CLIENT_SPECS
from waxx.util.dashboard.dashboard_window import DashboardMainWindow
from waxx.util.dashboard import host_config, logging_setup
from waxx.util.dashboard.host_config import (
    hostname,
    load_layout_overrides,
    resolve_host_ip,
)
from waxx.util.dashboard.logging_setup import configure_client_logging
from waxx.util.dashboard.panel_container import ClientPanel
from waxx.util.dashboard.panel_spec import ClientSpec
from waxx.util.dashboard.server_supervisor import install_console_signal_guard

# Lab-specific wiring.
try:
    from kexp.config import ip as _kexp_ip
    _kexp_log_root = getattr(_kexp_ip, "LOG_DIR", None)
except Exception:
    _kexp_log_root = None
logging_setup.configure(app_name="kexp", log_root=_kexp_log_root, logger_namespace="kexp")
host_config.configure(
    hosts_module="kexp.util.dashboard.dashboard_hosts",
    layout_module="kexp.util.dashboard.dashboard_layout",
    subnet_prefix="192.168.1.",
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="kexp Client Dashboard")
    p.add_argument("--host-ip", default=None, help="Override the resolved lab IP (for testing)")
    p.add_argument("--include", default="", help="Comma-separated client ids to include")
    p.add_argument("--exclude", default="", help="Comma-separated client ids to exclude")
    return p.parse_args(argv)


def _filter_specs(specs: list[ClientSpec], include: str, exclude: str) -> list[ClientSpec]:
    inc = {s.strip() for s in include.split(",") if s.strip()}
    exc = {s.strip() for s in exclude.split(",") if s.strip()}
    out = []
    for s in specs:
        if inc and s.id not in inc:
            continue
        if s.id in exc:
            continue
        out.append(s)
    return out


def _resolve_placement(spec: ClientSpec, overrides: dict) -> tuple[str, str]:
    o = overrides.get(spec.id, {})
    return (
        o.get("dock_area", spec.default_dock_area),
        o.get("placement", spec.default_placement),
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    log_path = configure_client_logging()
    log = logging.getLogger("kexp.dashboard.client_app")
    log.info("Client dashboard starting; logs -> %s", log_path)

    # Stay immune to CTRL_C / CTRL_BREAK leaking from any console-attached
    # child processes so the GUI cannot be killed by a stray console signal.
    install_console_signal_guard()

    host_ip = resolve_host_ip(args.host_ip)
    log.info("Host IP resolved: %s (hostname=%s)", host_ip, hostname())

    overrides = load_layout_overrides(host_ip)
    specs = _filter_specs(CLIENT_SPECS, args.include, args.exclude)
    log.info("Building %d client panel(s): %s", len(specs), [s.id for s in specs])

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("kexp Client Dashboard")

    panels: list[tuple[ClientPanel, str]] = []
    panel_by_id: dict[str, ClientPanel] = {}
    for spec in specs:
        dock_area, _placement = _resolve_placement(spec, overrides)
        panel = ClientPanel(spec.id, spec.label, body_factory=spec.body_factory, icon=spec.icon)
        panels.append((panel, dock_area))
        panel_by_id[spec.id] = panel

    win = DashboardMainWindow(
        kind="client",
        title=f"kexp Client Dashboard - {hostname()}",
        panels=panels,
        host_ip=host_ip,
        settings_org="kexp",
    )
    win.resize(1400, 900)
    win.show()

    # First-run only: honor each spec's ``default_visible`` flag.  Once the
    # user has saved a layout (geometry/state present in QSettings), respect
    # whatever they last had visible instead.
    _settings = QSettings("kexp", "dashboard")
    _first_run = _settings.value(f"dashboard/client/{host_ip}/state") is None
    if _first_run:
        for spec in specs:
            if not spec.default_visible:
                pnl = panel_by_id.get(spec.id)
                if pnl is not None:
                    pnl.hide()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
