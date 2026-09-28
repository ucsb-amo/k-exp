"""The "Regenerate state file" defaults (kexp...state_defaults): built from the
K machine's frames, returned and never written, and handed to the monitor
server by its launchers.
"""
import os
import sys

from kexp.util.guis.device_state_gui import state_defaults

SCRIPT = "kexp.util.guis.device_state_gui.generate_state_file"   # writes when imported


def test_defaults_cover_every_frame_channel_and_write_nothing(monkeypatch):
    from waxx.util.device_state import generate_state_file as gsf
    from waxx.util.device_state import state_file_io
    writes = []
    monkeypatch.setattr(state_file_io, "atomic_write", lambda *a, **k: writes.append(a))
    monkeypatch.setattr(gsf.Generator, "save_config_file",
                        lambda self: writes.append("save") or None)
    sys.modules.pop(SCRIPT, None)

    data = state_defaults.default_device_state()

    assert writes == [] and SCRIPT not in sys.modules
    for dtype, fields in (("dds", ("frequency", "amplitude", "v_pd", "sw_state")),
                          ("ttl", ("ttl_state",)), ("dac", ("voltage",))):
        assert data[dtype], f"no {dtype} channels"
        for name, entry in data[dtype].items():
            assert all(f in entry for f in fields), (dtype, name)
    from kexp.config.dac_id import dac_frame
    from kexp.config.dds_id import dds_frame
    dac = dac_frame()
    assert set(data["dds"]) == {d.key for d in dds_frame(dac_frame_obj=dac).dds_list}


def test_the_launchers_hand_it_to_the_server():
    from kexp.util.guis.device_state_gui import monitor_server_headless as mh
    assert mh.monitor_state_generator() is state_defaults.default_device_state
