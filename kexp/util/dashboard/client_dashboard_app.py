"""Client dashboard application entry point.

Run::

    python -m kexp.util.dashboard.client_dashboard_app
        [--host-ip 192.168.1.76]
        [--include id1,id2] [--exclude id1,id2]

The client dashboard does NOT start any subprocesses; it only embeds client
widgets that talk to remote servers (which are managed by the server
dashboard on the lab control PC).  Panels whose body_factory fails to
import or instantiate appear as ErrorBodyWidgets so the rest of the
dashboard remains usable.  Panels hidden by default are not built until
they are first shown.
"""

from __future__ import annotations

import argparse
import logging
import sys

from PyQt6.QtWidgets import QApplication

from kexp.util.dashboard.client_registry import CLIENT_SPECS
from waxx.util.dashboard import host_config, logging_setup
from waxx.util.dashboard.dashboard_window import DashboardMainWindow, PanelPlacement
from waxx.util.dashboard.host_config import (
    hostname,
    load_layout_overrides,
    resolve_host_ip,
)
from waxx.util.dashboard.logging_setup import configure_client_logging
from waxx.util.dashboard.panel_container import ClientPanel
from waxx.util.dashboard.panel_spec import ClientSpec, PanelSpec
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


def _placement_for(spec: PanelSpec, panel, layout: dict, *, realize_eagerly: bool = False) -> PanelPlacement:
    o = layout.get(spec.id, {})
    return PanelPlacement(
        panel=panel,
        area=o.get("dock_area", spec.default_dock_area),
        placement=o.get("placement", spec.default_placement),
        tab_group=o.get("tab_group", spec.tab_group),
        default_visible=spec.default_visible,
        realize_eagerly=realize_eagerly or spec.realize_eagerly,
        warm_imports=tuple(spec.warm_imports),
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    log_path = configure_client_logging()
    log = logging.getLogger("kexp.dashboard.client_app")
    log.info("Client dashboard starting; logs -> %s", log_path)

    install_console_signal_guard()

    host_ip = resolve_host_ip(args.host_ip)
    log.info("Host IP resolved: %s (hostname=%s)", host_ip, hostname())

    layout = load_layout_overrides(host_ip, kind="client")
    specs = _filter_specs(CLIENT_SPECS, args.include, args.exclude)
    log.info("Building %d client panel(s): %s", len(specs), [s.id for s in specs])

    app_id = "kexp.ClientDashboard"
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("kexp Client Dashboard")

    placements: list[PanelPlacement] = []
    for spec in specs:
        panel = ClientPanel(spec.id, spec.label, body_factory=spec.body_factory, icon=spec.icon)
        placements.append(_placement_for(spec, panel, layout))

    from waxx.util.dashboard.log_panel import LogPanel  # noqa: PLC0415
    log_panel = LogPanel(sources=[])
    log_panel.attach_root_logging(logging.WARNING)
    log_dock = ClientPanel("_log", "Log", body_factory=lambda _lp=log_panel: _lp, icon="📜")
    placements.append(_placement_for(PanelSpec(id="_log", label="Log", default_dock_area="bottom"),
                                     log_dock, layout, realize_eagerly=True))

    win = DashboardMainWindow(
        kind="client",
        title=f"kexp Client Dashboard - {hostname()}",
        panels=placements,
        host_ip=host_ip,
        settings_org="kexp",
        app_id=app_id,
    )
    win.attach_log_panel(log_panel)
    if win.width() < 400:
        win.resize(1400, 900)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
