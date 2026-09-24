"""Server dashboard application entry point.

Run::

    python -m kexp.util.dashboard.server_dashboard_app
        [--host-ip 192.168.1.76]
        [--include id1,id2] [--exclude id1,id2]
        [--no-autostart]

What it does
------------
1. Calls :func:`configure_server_logging` early so all subsequent logs go to
   ``DATA_DIR/_logs/server/dashboard__<hostname>.log`` (or fallback path).
2. Resolves the lab-subnet IP of this PC.
3. Loads :data:`SERVER_SPECS`, builds a :class:`ServerPanel` + supervisor
   per spec, a :class:`ServerLink` for every spec with a ``client_factory``
   (header conn/COM badges + graceful shutdown), the Running Servers and
   Log panels, and the extra client panels (Device Control, Remote Control,
   Ethernet Relay) for one-stop control on the lab PC.
4. Shows the :class:`DashboardMainWindow` *before* starting any subprocess
   (transparency-first) and then autostarts the servers listed for this
   host in ``dashboard_hosts.HOST_AUTOSTART_SERVERS`` after a short delay
   that lets the discovery beacon registry spot instances already running.
"""

from __future__ import annotations

import argparse
import logging
import sys

from PyQt6.QtWidgets import QApplication

from waxx.util.dashboard import host_config, logging_setup
from waxx.util.dashboard.dashboard_window import DashboardMainWindow, PanelPlacement
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
from waxx.util.dashboard.panel_spec import PanelSpec, ServerSpec
from waxx.util.dashboard.server_link import ServerLink
from waxx.util.dashboard.server_supervisor import ServerSupervisor, install_console_signal_guard
from kexp.util.dashboard.server_registry import SERVER_SPECS
from kexp.util.dashboard.client_registry import get_spec as _get_client_spec

# Extra client-side panels (no subprocess) to also show in the server
# dashboard for one-stop control on the lab PC.
EXTRA_CLIENT_IDS_ON_SERVER_DASHBOARD: list[str] = [
    "device_control",
    "remote_control",
    "ethernet_relay",
]

# Lab-specific wiring: tell the generic waxx framework where kexp keeps its
# log dir, host autostart table, and layout defaults.
try:
    from kexp.config import ip as _kexp_ip
    _kexp_log_root = getattr(_kexp_ip, "LOG_DIR", None)
    _kexp_data_dir = getattr(_kexp_ip, "DATA_DIR", None)
    _kexp_map_bat = getattr(_kexp_ip, "MAP_BAT_PATH", None)
except Exception:
    _kexp_log_root = None
    _kexp_data_dir = None
    _kexp_map_bat = None
logging_setup.configure(app_name="kexp", log_root=_kexp_log_root, logger_namespace="kexp")
host_config.configure(
    hosts_module="kexp.util.dashboard.dashboard_hosts",
    layout_module="kexp.util.dashboard.dashboard_layout",
    subnet_prefix="192.168.1.",
)
try:
    from waxx.util.dashboard import data_dir_guard  # noqa: PLC0415
    data_dir_guard.configure(_kexp_data_dir, _kexp_map_bat)
except Exception:
    pass


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="kexp Server Dashboard")
    p.add_argument("--host-ip", default=None, help="Override the resolved lab IP (for testing)")
    p.add_argument("--include", default="", help="Comma-separated list of server ids to include (overrides default)")
    p.add_argument("--exclude", default="", help="Comma-separated list of server ids to exclude")
    p.add_argument("--no-autostart", action="store_true", help="Do not autostart any server (testing)")
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


def placement_for(spec: PanelSpec, panel, layout: dict, *, realize_eagerly: bool = False) -> PanelPlacement:
    """Merge the spec's fallback placement with the layout table entry."""
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

    log_path = configure_server_logging("dashboard")
    log = logging.getLogger("kexp.dashboard.server_app")
    log.info("Server dashboard starting; logs -> %s", log_path)

    # Make the dashboard immune to CTRL_C / CTRL_BREAK so a console signal
    # aimed at a child can never take down the whole GUI.
    install_console_signal_guard()

    host_ip = resolve_host_ip(args.host_ip)
    log.info("Host IP resolved: %s (hostname=%s)", host_ip, hostname())

    autostart = set() if args.no_autostart else load_autostart_set(host_ip)
    layout = load_layout_overrides(host_ip, kind="server")
    log.info("Autostart set: %s", sorted(autostart))

    specs = _filter_specs(SERVER_SPECS, args.include, args.exclude)
    log.info("Building %d panel(s): %s", len(specs), [s.id for s in specs])

    app_id = "kexp.ServerDashboard"
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("kexp Server Dashboard")

    placements: list[PanelPlacement] = []
    supervisors: dict[str, ServerSupervisor] = {}
    labels: dict[str, str] = {}
    links: list[ServerLink] = []
    panels_by_id: dict[str, ServerPanel] = {}

    def _make_supervisor(spec: ServerSpec) -> ServerSupervisor:
        sup = ServerSupervisor(
            spec.id, spec.server_cmd,
            cwd=spec.cwd,
            env_extra=spec.env_extra,
            graceful_stop_timeout_s=spec.graceful_stop_timeout_s,
            restart_on_crash=spec.restart_on_crash,
            snapshot_host=spec.snapshot_host,
            snapshot_port=spec.snapshot_port,
            requires_data_dir=spec.requires_data_dir,
            beacon_id=spec.server_id,
            label=spec.label,
        )
        sup.log_line.connect(server_child_logger(spec.id).info)
        supervisors[spec.id] = sup
        labels[spec.id] = spec.label
        return sup

    for spec in specs:
        # Hidden-panel specs: only create the supervisor, no dock tile.
        if spec.hidden_panel:
            if not spec.server_cmd:
                log.warning("spec '%s' is hidden_panel but has no server_cmd; skipping", spec.id)
                continue
            _make_supervisor(spec)
            log.info("registered hidden-panel supervisor '%s'", spec.id)
            continue

        panel = ServerPanel(
            spec.id, spec.label,
            body_factory=spec.body_factory,
            com_label=spec.com_label,
            icon=spec.icon,
        )
        panels_by_id[spec.id] = panel

        # Specs with empty server_cmd are *in-process* panels: the embedded
        # widget itself owns the server, so there is no supervisor and the
        # body must be built at startup for the server to exist.
        if not spec.server_cmd:
            panel.header().set_server_controls_visible(False)
            placements.append(placement_for(spec, panel, layout, realize_eagerly=(spec.id in autostart)))
            log.info("registered in-process server panel '%s' (no subprocess)", spec.id)
            continue

        sup = _make_supervisor(spec)
        sup.state_changed.connect(panel.header().set_state)
        panel.header().start_clicked.connect(
            lambda _c=False, s=sup: s.reset_and_start() if s.state.name in ("CRASHED", "FAILED") else s.start())
        panel.header().stop_clicked.connect(lambda _c=False, s=sup: s.stop())
        panel.header().restart_clicked.connect(lambda _c=False, s=sup: s.restart())

        if spec.client_factory is not None:
            links.append(ServerLink(spec.id, spec.client_factory, header=panel.header(), supervisor=sup))

        placements.append(placement_for(spec, panel, layout))

    # Extra client panels (Device Control etc.) for one-stop control.
    for cid in EXTRA_CLIENT_IDS_ON_SERVER_DASHBOARD:
        cspec = _get_client_spec(cid)
        if cspec is None:
            log.warning("server-dashboard extra client id=%s not in CLIENT_SPECS", cid)
            continue
        cpanel = ClientPanel(cspec.id, cspec.label, body_factory=cspec.body_factory, icon=cspec.icon)
        placements.append(placement_for(cspec, cpanel, layout))
        log.info("added client panel '%s' to server dashboard", cspec.id)

    # Framework panels: Running Servers overview + Log dock.
    from waxx.util.dashboard.running_servers_panel import RunningServersPanel  # noqa: PLC0415
    from waxx.util.dashboard.log_panel import LogPanel  # noqa: PLC0415

    entries = [(sid, labels.get(sid, sid), supervisors[sid]) for sid in supervisors]
    overview_panel = ClientPanel(
        "_running_servers", "Running Servers",
        body_factory=lambda _e=entries: RunningServersPanel(_e),
    )
    overview_spec = PanelSpec(id="_running_servers", label="Running Servers", default_dock_area="right")
    placements.append(placement_for(overview_spec, overview_panel, layout, realize_eagerly=True))

    log_panel = LogPanel(sources=sorted(supervisors))
    log_panel.attach_root_logging(logging.WARNING)
    log_dock = ClientPanel("_log", "Log", body_factory=lambda _lp=log_panel: _lp, icon="📜")
    log_spec = PanelSpec(id="_log", label="Log", default_dock_area="bottom")
    placements.append(placement_for(log_spec, log_dock, layout, realize_eagerly=True))

    win = DashboardMainWindow(
        kind="server",
        title=f"kexp Server Dashboard - {hostname()}",
        panels=placements,
        host_ip=host_ip,
        settings_org="kexp",
        app_id=app_id,
    )
    win.attach_log_panel(log_panel)
    com_ids = {spec.id for spec in specs if spec.com_label}
    win.register_supervisors(supervisors, com_ids=com_ids, labels=labels)
    win.register_links(links)
    win.set_autostart(sorted(autostart))

    if win.saveGeometry().isEmpty() or win.width() < 400:
        win.resize(1400, 900)
    win.show()

    # Autostart only after the window has shown and the beacon registry has
    # had one round to hear servers that are already running.
    if autostart:
        win.schedule_autostart(delay_ms=1200)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
