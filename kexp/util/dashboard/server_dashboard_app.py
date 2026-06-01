"""Server dashboard application entry point.

Run::

    python -m kexp.util.dashboard.server_dashboard_app
        [--host-ip 192.168.1.76]
        [--include id1,id2] [--exclude id1,id2]

What it does
------------
1. Calls :func:`configure_server_logging` early so all subsequent logs go to
   ``DATA_DIR/_logs/server/dashboard__<hostname>.log`` (or fallback path).
2. Resolves the lab-subnet IP of this PC.
3. Loads :data:`SERVER_SPECS` and builds a :class:`ServerPanel` per spec.
4. Builds the :class:`DashboardMainWindow` and shows it *before* starting
   any subprocess (transparency-first: the user sees the dashboard
   immediately even if a server is slow to start).
5. After the window is shown, auto-starts the servers listed for this host
   in ``dashboard_hosts.HOST_AUTOSTART_SERVERS``.

Subprocess supervision, snapshot polling, and log tailing are wired here.
"""

from __future__ import annotations

import argparse
import logging
import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from waxx.util.dashboard.dashboard_window import DashboardMainWindow
from waxx.util.dashboard import host_config, logging_setup
from waxx.util.dashboard.host_config import (
    hostname,
    load_autostart_set,
    load_layout_overrides,
    resolve_host_ip,
)
from waxx.util.dashboard.logging_setup import (
    configure_server_logging,
    server_child_logger,
)
from waxx.util.dashboard.panel_container import ClientPanel, ServerPanel
from waxx.util.dashboard.panel_spec import ServerSpec
from kexp.util.dashboard.server_registry import SERVER_SPECS
from kexp.util.dashboard.client_registry import get_spec as _get_client_spec
from waxx.util.dashboard.server_supervisor import ServerSupervisor

# Extra client-side panels (no subprocess) to also show in the server
# dashboard for one-stop control on the lab PC.
EXTRA_CLIENT_IDS_ON_SERVER_DASHBOARD: list[str] = [
    "remote_control",
    "ethernet_relay",
    "device_control",
]

# Lab-specific wiring: tell the generic waxx framework where kexp keeps its
# log dir, host autostart table, and layout overrides.
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
    p = argparse.ArgumentParser(description="kexp Server Dashboard")
    p.add_argument("--host-ip", default=None, help="Override the resolved lab IP (for testing)")
    p.add_argument("--include", default="", help="Comma-separated list of server ids to include (overrides default)")
    p.add_argument("--exclude", default="", help="Comma-separated list of server ids to exclude")
    return p.parse_args(argv)


def _filter_specs(specs: list[ServerSpec], include: str, exclude: str) -> list[ServerSpec]:
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


def _resolve_placement(spec: ServerSpec, overrides: dict) -> tuple[str, str]:
    o = overrides.get(spec.id, {})
    return (
        o.get("dock_area", spec.default_dock_area),
        o.get("placement", spec.default_placement),
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    log_path = configure_server_logging("dashboard")
    log = logging.getLogger("kexp.dashboard.server_app")
    log.info("Server dashboard starting; logs -> %s", log_path)

    host_ip = resolve_host_ip(args.host_ip)
    log.info("Host IP resolved: %s (hostname=%s)", host_ip, hostname())

    autostart = load_autostart_set(host_ip)
    overrides = load_layout_overrides(host_ip)
    log.info("Autostart set: %s", sorted(autostart))

    specs = _filter_specs(SERVER_SPECS, args.include, args.exclude)
    log.info("Building %d panel(s): %s", len(specs), [s.id for s in specs])

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("kexp Server Dashboard")

    panels: list[tuple] = []
    supervisors: dict[str, ServerSupervisor] = {}
    for spec in specs:
        dock_area, _placement = _resolve_placement(spec, overrides)

        # Hidden-panel specs: only create the supervisor, no dock tile.
        # Useful for headless background servers whose state is already
        # surfaced by another panel.
        if getattr(spec, "hidden_panel", False):
            if not spec.server_cmd:
                log.warning(
                    "spec '%s' is hidden_panel but has no server_cmd; skipping",
                    spec.id,
                )
                continue
            sup = ServerSupervisor(
                spec.id, spec.server_cmd,
                cwd=spec.cwd,
                env_extra=spec.env_extra,
                graceful_stop_timeout_s=spec.graceful_stop_timeout_s,
                restart_on_crash=spec.restart_on_crash,
                snapshot_host=spec.snapshot_host,
                snapshot_port=spec.snapshot_port,
            )
            child_log = server_child_logger(spec.id)
            sup.log_line.connect(child_log.info)
            supervisors[spec.id] = sup
            log.info("registered hidden-panel supervisor '%s'", spec.id)
            continue

        panel = ServerPanel(
            spec.id, spec.label,
            body_factory=spec.body_factory,
            com_label=spec.com_label,
            icon=spec.icon,
        )

        # Specs with empty server_cmd are *in-process* panels: the embedded
        # widget itself owns the server (UDP/ZMQ thread inside the widget).
        # Skip supervisor wiring and disable the Start/Stop/Restart buttons
        # so the header still looks consistent but doesn't try to spawn a
        # subprocess.
        if not spec.server_cmd:
            try:
                hdr = panel.header()
                for btn_name in ("_start_btn", "_stop_btn", "_restart_btn"):
                    btn = getattr(hdr, btn_name, None)
                    if btn is not None:
                        btn.setVisible(False)
            except Exception:
                log.exception("could not hide header buttons for in-process spec '%s'", spec.id)
            panels.append((panel, dock_area, "servers"))
            # In-process specs own their server inside the embedded widget,
            # so the panel body must be realized for the server to start.
            # Schedule realization after the window is shown.
            if spec.id in autostart:
                _ip = panel  # closure binding
                QTimer.singleShot(300, lambda p=_ip: p.realize_body())
            log.info("registered in-process server panel '%s' (no subprocess)", spec.id)
            continue

        sup = ServerSupervisor(
            spec.id, spec.server_cmd,
            cwd=spec.cwd,
            env_extra=spec.env_extra,
            graceful_stop_timeout_s=spec.graceful_stop_timeout_s,
            restart_on_crash=spec.restart_on_crash,
            snapshot_host=spec.snapshot_host,
            snapshot_port=spec.snapshot_port,
        )
        # Wire supervisor -> header.
        sup.state_changed.connect(panel.header().set_state)
        # Wire header -> supervisor.
        panel.header().start_clicked.connect(sup.start)
        panel.header().stop_clicked.connect(sup.stop)
        panel.header().restart_clicked.connect(sup.restart)
        # Route log lines to a per-server child logger.
        child_log = server_child_logger(spec.id)
        sup.log_line.connect(child_log.info)

        panels.append((panel, dock_area, "servers"))
        supervisors[spec.id] = sup

    # Append extra client panels (e.g. remote_control) requested for the
    # server dashboard.  These have no supervisor / Start-Stop buttons -
    # they're just embedded GUIs.
    for cid in EXTRA_CLIENT_IDS_ON_SERVER_DASHBOARD:
        cspec = _get_client_spec(cid)
        if cspec is None:
            log.warning("server-dashboard extra client id=%s not in CLIENT_SPECS", cid)
            continue
        c_dock_area = overrides.get(cspec.id, {}).get("dock_area", cspec.default_dock_area)
        cpanel = ClientPanel(cspec.id, cspec.label, body_factory=cspec.body_factory, icon=cspec.icon)
        panels.append((cpanel, c_dock_area, "servers"))
        log.info("added client panel '%s' to server dashboard", cspec.id)

    # Build the "Running Servers" overview tile-grid panel and include it
    # in the panels list so the window realizes its body and tracks it.
    try:
        from waxx.util.dashboard.running_servers_panel import RunningServersPanel  # noqa: PLC0415

        entries = [(sid, sid, supervisors[sid]) for sid in supervisors.keys()]
        overview_panel = ClientPanel(
            "_running_servers",
            "Running Servers",
            body_factory=lambda parent=None, _e=entries: RunningServersPanel(_e, columns=2, parent=parent),
        )
        panels.append((overview_panel, "right", "servers"))
    except Exception:
        log.exception("could not build Running Servers overview panel")

    win = DashboardMainWindow(
        kind="server",
        title=f"kexp Server Dashboard - {hostname()}",
        panels=panels,
        host_ip=host_ip,
        settings_org="kexp",
    )
    # Stop all supervisors gracefully on dashboard close (releases COM
    # ports, network sockets, etc. owned by the subprocesses).
    win.register_supervisors(supervisors)

    win.resize(1400, 900)
    win.show()

    # Autostart only after the window has shown, so any failure does not
    # block UI visibility.
    def _do_autostart():
        for sid in sorted(autostart):
            sup = supervisors.get(sid)
            if sup is None:
                log.warning("autostart: no supervisor for id=%s", sid)
                continue
            sup.start()

    QTimer.singleShot(200, _do_autostart)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
