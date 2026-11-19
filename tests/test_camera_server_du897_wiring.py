"""kexp's wiring of the Andor camera server (kexp.control.cameras.andor_server):
the camera table's serial is the one id liveOD's camera host, the Andor
server and the SLM spot finder all use, the launcher takes the table's serial,
readout and the lab's constraints, and the dashboard entry starts it (never
autostarted).  No server is started, no camera is touched."""
import argparse
import sys
from pathlib import Path

SERIAL = "13445"
CID = f"andor_emccd:{SERIAL}"


def test_du897_one_id_for_liveod_the_server_and_the_spot_finder():
    from kexp.config.camera_id import cameras
    from kexp.config.live_od import CAMERA_BAR_KEYS
    from waxx.util.live_od.camera_host.host import camera_specs
    assert cameras.andor.serial_no == SERIAL
    (spec,) = [s for s in camera_specs([getattr(cameras, k) for k in CAMERA_BAR_KEYS])
               if s.camera_type == "andor"]
    assert spec.camera_id == CID
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kexp" / "calibrations"
                           / "SLM_spot_finder"))
    from served_source import liveod_camera_id
    assert liveod_camera_id(cameras.andor) == CID
    # the APD entry shares the class, not the camera
    assert cameras.apd.serial_no == ""


def test_du897_launcher_takes_the_table_and_the_lab_constraints():
    from kexp.config.camera_id import cameras
    from kexp.config.live_od import andor_constraints
    from kexp.control.cameras.andor_server import KexpAndorProvider
    from beacon.drivers.andor.backend import refuse_combos_from
    ap = argparse.ArgumentParser()
    KexpAndorProvider.add_arguments(ap)
    p = KexpAndorProvider.from_args(ap.parse_args([]))
    assert p.serials == (SERIAL,) and p.probe() == [{"serial": SERIAL, "model": "iXon"}]
    assert p.readout == {k: getattr(cameras.andor, k)
                         for k in ("hs_speed", "vs_speed", "vs_amp", "preamp", "baseline_clamp")}
    assert refuse_combos_from(p.constraints) == refuse_combos_from(andor_constraints())
    ((conds, why),) = refuse_combos_from(p.constraints)
    assert dict(conds) == {"vs_speed": 0, "vs_amp": 0} and "80707" in why
    # a serial on the command line wins
    assert KexpAndorProvider.from_args(ap.parse_args(["--serial", "1"])).serials == ("1",)
    # liveOD's config carries the same constraints
    live = p.live_defaults({})
    assert (live["vs_speed"], live["vs_amp"]) == (cameras.andor.vs_speed, cameras.andor.vs_amp)


def test_du897_dashboard_entry():
    from kexp.util.dashboard.server_registry import SERVER_SPECS
    from kexp.util.dashboard.dashboard_hosts import HOST_AUTOSTART_SERVERS
    (spec,) = [s for s in SERVER_SPECS if s.id == "andor"]
    assert spec.server_cmd[1:] == ["-m", "kexp.control.cameras.andor_server"]
    assert spec.graceful_stop_timeout_s >= 15.0     # the camera's verified close
    assert all("andor" not in ids for ids in HOST_AUTOSTART_SERVERS.values())
