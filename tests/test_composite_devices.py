"""K-machine composite devices (kexp.config.composite_devices) checked against
the lab's own classes, offline: frames on DummyCore, no hardware, no network.

The op bodies are compiled for real by the offline compile check of the
monitor experiment; these tests cover what compiling cannot: that the GUI's
conversions agree with the classes the kernel runs, that limits match the
DAC channels they protect, and that every channel named exists.
"""
import re
from types import SimpleNamespace

import numpy as np
import pytest

from waxx.util.device_state import composite as cmp
from waxx.util.device_state.composite import Context, OpTable
from waxx.util.device_state.generate_state_file import Generator

import kexp.config.composite_devices as kc
from kexp.config.dac_id import dac_frame
from kexp.config.dds_id import dds_frame
from kexp.config.expt_params import ExptParams
from kexp.config.ttl_id import ttl_frame


@pytest.fixture(scope="module")
def frames():
    dac = dac_frame()
    dds = dds_frame(dac_frame_obj=dac)
    return SimpleNamespace(dds=dds, dac=dac, ttl=ttl_frame())


@pytest.fixture(scope="module")
def params():
    return ExptParams()


@pytest.fixture
def config(frames):
    """A device-state config with every channel, as the monitor writes it."""
    gen = Generator(frames.dds, frames.ttl, frames.dac, state_file_path=None, verbose=False)
    gen.generate_device_config()
    return gen.config_data


def _ctx(config, params, frames, **fields):
    return Context(config, params, SimpleNamespace(dds=frames.dds, dac=frames.dac),
                   fields=fields)


def _device(key):
    return next(d for d in kc.COMPOSITE_DEVICES if d.key == key)


# --- definitions ---------------------------------------------------------------------

def test_definitions_build():
    table = OpTable(kc.COMPOSITE_DEVICES)
    assert [d.key for d in table.devices] == ["imaging", "raman", "ry_405", "ry_980",
                                              "lightsheet", "tweezer", "outer_coil",
                                              "inner_coil", "shims", "mot", "d1_gm"]
    assert all(e.body.startswith(cmp.SLACK_PREFIX) for e in table)


def test_every_channel_and_attribute_named_in_op_code_exists(frames):
    """A typo in op code would otherwise only show up when the monitor compiles."""
    from kexp.base.cooling import Cooling
    known = {"dds": frames.dds, "ttl": frames.ttl, "dac": frames.dac}
    expt_attrs = {"dds", "ttl", "dac", "p", "monitor", "imaging", "raman", "lightsheet",
                  "tweezer", "outer_coil", "inner_coil", "ry_405", "ry_980"}
    params = ExptParams()
    for entry in OpTable(kc.COMPOSITE_DEVICES):
        for first, rest in re.findall(r"\bexpt\.(\w+)((?:\.\w+)?)", entry.body):
            # an attribute of Base's devices, or a Cooling sequence method
            assert first in expt_attrs or callable(getattr(Cooling, first, None)), \
                f"{entry.name}: expt.{first}"
            if first == "p" and rest:
                assert hasattr(params, rest[1:]), f"{entry.name}: expt.p{rest}"
            if first in known and rest:
                assert hasattr(known[first], rest[1:]), f"{entry.name}: expt.{first}{rest}"
    for device in kc.COMPOSITE_DEVICES:
        for lamp in device.lamps:
            assert hasattr(known[lamp.dtype], lamp.name), f"{device.key} lamp {lamp.name}"
        for row in device.layout:
            if isinstance(row, cmp.ChannelToggle):
                assert hasattr(known[row.dtype], row.name), f"{device.key} toggle {row.name}"


def test_every_readback_resolves_on_a_full_config(config, params, frames):
    # the MOT current reads back only while the inner coil is on
    config["ttl"]["inner_coil_igbt"]["ttl_state"] = 1
    ctx = _ctx(config, params, frames)
    for device in kc.COMPOSITE_DEVICES:
        for arg in device.fields:
            if arg.readback is None or arg.kind == cmp.KIND_CHOICE:
                continue
            assert arg.readback_value(ctx) is not None, f"{device.key}.{arg.name}"
        assert device.status(ctx).level != "unknown", device.key
        for readout in device.readouts:
            assert readout.value(ctx) is not None, f"{device.key} readout {readout.label}"


def test_every_default_resolves(config, params, frames):
    ctx = _ctx(config, params, frames)
    for device in kc.COMPOSITE_DEVICES:
        for arg in device.fields:
            if arg.default is None:
                continue
            value = arg.default_value(ctx)
            assert value is not None, f"{device.key}.{arg.name}"
            assert not arg.hard_problems(value), f"{device.key}.{arg.name} default {value}"


# --- raman -------------------------------------------------------------------------

def test_raman_readback_inverts_the_classes_split(config, params, frames):
    ctx = _ctx(config, params, frames)
    pair = kc._raman_pair(ctx)
    for f in (119.4639e6, 147.2593e6, params.frequency_raman_transition):
        f0, f1 = pair.ao_frequencies(f)
        pair.state_splitting_to_ao_frequency(f)          # the kernel's own function
        assert (f0, f1) == pytest.approx(tuple(pair._dummy[:2]))
        config["dds"]["raman_150_plus"]["frequency"] = float(f0)
        assert kc._raman_f_readback(ctx) == pytest.approx(f, abs=1e-3)


def test_raman_power_readback(config, params, frames):
    ctx = _ctx(config, params, frames)
    a0 = frames.dds.raman_150_plus.amplitude
    config["dds"]["raman_150_plus"]["amplitude"] = np.sqrt(0.3) * a0   # RamanBeamPair.set
    assert kc._raman_p_readback(ctx) == pytest.approx(0.3)


def test_raman_window_warns_but_used_transitions_pass(config, params, frames):
    arg = _device("raman").get_field("f")
    ctx = _ctx(config, params, frames)
    assert arg.checks(119.4639e6, ctx) == []
    assert arg.checks(147.2593e6, ctx) == []
    assert [c.level for c in arg.checks(200.e6, ctx)] == ["warn"]


# --- imaging -----------------------------------------------------------------------

def _host_imaging(frames, params):
    from waxx.control.beat_lock import BeatLockImagingPID
    return BeatLockImagingPID(dds_sw=frames.dds.imaging_x_switch, dds_pid=frames.dds.imaging,
                              dds_beatref=frames.dds.beatlock_ref, expt_params=params)


def test_imaging_beat_matches_the_class(config, params, frames, capsys):
    imaging = _host_imaging(frames, params)
    ctx = _ctx(config, params, frames)
    for f in (24.e6, 0., -150.e6, params.frequency_detuned_imaging):
        f_ref, _ = kc.imaging_beat(ctx, f)
        assert f_ref == pytest.approx(imaging.imaging_detuning_to_beat_ref(f))


def test_imaging_detuning_readback_round_trip(config, params, frames):
    ctx = _ctx(config, params, frames)
    f_ref, _ = kc.imaging_beat(ctx, 24.e6)
    config["dds"]["beatlock_ref"]["frequency"] = f_ref
    assert kc._imaging_detuning_readback(ctx) == pytest.approx(24.e6)


def test_imaging_detuning_check_refuses_what_the_kernel_would_raise_on(config, params, frames):
    ctx = _ctx(config, params, frames)
    arg = _device("imaging").get_field("detuning")
    assert arg.checks(params.frequency_detuned_imaging, ctx) == []
    # an offset below frequency_minimum_offset_beatlock: set_imaging_detuning raises
    ao = kc._imaging_ao_shift(ctx)
    too_close = ao + kc.FREQUENCY_GS_HFS / 2 - params.beatlock_sign * 0.9 * \
        params.frequency_minimum_offset_beatlock
    found = arg.checks(too_close, ctx)
    assert found and found[0].is_error and "minimum" in found[0].message


def test_imaging_power_default_follows_axis_and_type(config, params, frames):
    from kexp.config.camera_id import cameras
    arg = _device("imaging").get_field("power")
    x = _ctx(config, params, frames, axis=kc.AXIS_X, img_type=kc.IMG_ABS)
    xy = _ctx(config, params, frames, axis=kc.AXIS_XY, img_type=kc.IMG_FLUOR)
    assert arg.default_value(x) == pytest.approx(cameras.andor.__amp_absorption__)
    assert arg.default_value(xy) == pytest.approx(cameras.xy_basler.__amp_fluorescence__)


# --- coils -------------------------------------------------------------------------

def test_coil_current_limits_stay_below_the_supply_dac_max(frames):
    from kexp.control.big_coil import igbt_magnet
    outer = igbt_magnet(slope_current_per_vdac_supply=kc.slope_i_transducer_per_v_setpoint_supply_outer,
                        offset_current_per_vdac_supply=kc.offset_i_transducer_per_v_setpoint_supply_outer)
    inner = igbt_magnet(slope_current_per_vdac_supply=kc.slope_i_per_v_setpoint_supply_inner)
    assert kc.I_OUTER_MAX <= outer.supply_vdac_to_current(frames.dac.outer_coil_supply_current.max_v)
    assert kc.I_INNER_MAX <= inner.supply_vdac_to_current(frames.dac.inner_coil_supply_current.max_v)
    # set_voltage maps V/80 onto 10 V of DAC; the field's limit must stay below max_v
    for attr in ("outer_coil_supply_voltage", "inner_coil_supply_voltage"):
        assert kc.V_COIL_SUPPLY_MAX / 80. * 10. < getattr(frames.dac, attr).max_v


def test_coil_readbacks_use_the_coils_calibration(config, params, frames):
    from kexp.control.big_coil import igbt_magnet
    outer = igbt_magnet(slope_current_per_vdac_supply=kc.slope_i_transducer_per_v_setpoint_supply_outer,
                        offset_current_per_vdac_supply=kc.offset_i_transducer_per_v_setpoint_supply_outer)
    config["dac"]["outer_coil_supply_current"]["voltage"] = 3.7
    config["ttl"]["outer_coil_igbt"]["ttl_state"] = 1
    ctx = _ctx(config, params, frames)
    arg = _device("outer_coil").get_field("i")
    assert arg.readback_value(ctx) == pytest.approx(outer.supply_vdac_to_current(3.7))
    assert _device("outer_coil").status(ctx).text.startswith("ON 18")


def test_inner_coil_calibration_unchanged():
    assert kc.slope_i_per_v_setpoint_supply_inner == 17.


def test_coil_op_checks(config, params, frames):
    outer = _device("outer_coil")
    ctx = _ctx(config, params, frames)
    config["ttl"]["outer_coil_igbt"]["ttl_state"] = 0
    assert outer.get_op("pid_on").check({}, ctx).is_error            # coil off
    config["ttl"]["outer_coil_igbt"]["ttl_state"] = 1
    config["dac"]["outer_coil_supply_current"]["voltage"] = 3.
    config["ttl"]["outer_coil_pid_ttl"]["ttl_state"] = 1
    assert cmp.worst(cmp._as_checks(outer.get_op("ramp_to").check({}, ctx))) == "error"
    inner = _device("inner_coil")
    config["ttl"]["inner_coil_igbt"]["ttl_state"] = 1
    assert inner.get_op("helmholtz").check({}, ctx).is_error         # coil on


def test_coil_pid_guards(config, params, frames):
    """PID off with the PID off would set the supply to a stale PID setpoint;
    PID on twice adds the overhead twice; PID on too high asks the supply DAC
    for more than max_v, which writes 0 V instead."""
    outer = _device("outer_coil")
    ctx = _ctx(config, params, frames)
    config["ttl"]["outer_coil_igbt"]["ttl_state"] = 1
    config["ttl"]["outer_coil_pid_ttl"]["ttl_state"] = 0
    assert outer.get_op("pid_off").check({}, ctx).is_error
    config["dac"]["outer_coil_supply_current"]["voltage"] = 3.7           # ~189 A
    assert outer.get_op("pid_on").check({}, ctx) is None
    config["dac"]["outer_coil_supply_current"]["voltage"] = 5.5           # ~280 A -> 392 A
    found = outer.get_op("pid_on").check({}, ctx)
    assert found.is_error and "overhead" in found.message
    config["dac"]["outer_coil_supply_current"]["voltage"] = 3.7
    config["ttl"]["outer_coil_pid_ttl"]["ttl_state"] = 1
    assert outer.get_op("pid_on").check({}, ctx).is_error                 # already on
    assert outer.get_op("pid_off").check({}, ctx) is None
    table = OpTable(kc.COMPOSITE_DEVICES)
    body = table.get("outer_coil.pid_on").body
    assert "coil PID is already on" in body
    assert (f"expt.outer_coil.i_supply * {kc.slope_overhead_per_i_transducer!r}" in body
            and "expt.outer_coil.i_control_dac.max_v" in body)
    assert body.index("max_v") < body.index("start_pid()")
    body = table.get("outer_coil.pid_off").body
    assert body.index("coil PID is off") < body.index("stop_pid()")


def test_pid_overhead_check_matches_the_calibration():
    """The kernel formats the overhead in as literals; they must be the
    numbers compute_pid_overhead uses."""
    from kexp.calibrations.magnets import compute_pid_overhead
    for i in (20., 100., 182.):
        assert i + i * kc.slope_overhead_per_i_transducer + kc.offset_overhead_per_i_transducer \
            == pytest.approx(i + compute_pid_overhead(i))


def test_coil_off_is_a_ramp_not_off():
    """Off must not call igbt_magnet.off(), which ramps to i_pid first."""
    for key in ("outer_coil", "inner_coil"):
        body = OpTable(kc.COMPOSITE_DEVICES).get(f"{key}.off").body
        assert f"expt.{key}.ramp_supply(t=a0, i_start=i0, i_end=0." in body
        assert "i0 = a1" in body                    # the measured current, when given
        assert f"expt.{key}.off()" not in body
        assert body.index("ramp_supply") < body.index("igbt_ttl.off()") < body.index("discharge")
        assert _device(key).get_op("snap_off").danger
    # MOT Off ramps the inner coil the same way
    body = OpTable(kc.COMPOSITE_DEVICES).get("mot.off").body
    assert "expt.inner_coil.ramp_supply(t=a0, i_start=i0, i_end=0." in body


def _telemetry(**values):
    return {k: cmp.Sample(v) for k, v in values.items()}


def test_untrusted_state_ramps_start_from_the_measured_current(config, params, frames):
    outer = _device("outer_coil")
    i_meas = outer.get_field("i_meas")
    untrusted = {"trusted": False, "reason": "run 1 never reported"}
    ctx = _ctx(config, params, frames)
    assert i_meas.default_value(ctx) == -1.                       # trusted: the DAC value
    ctx = Context(config, params, frames, trust=untrusted)
    assert i_meas.default_value(ctx) == -1.                       # nothing measured
    found = cmp._as_checks(outer.get_op("ramp_to").check({}, ctx))
    assert any(c.is_error and "untrusted" in c.message for c in found)
    assert outer.get_op("off").check({}, ctx).is_error
    ctx = Context(config, params, frames, trust=untrusted,
                  telemetry=_telemetry(**{"keysight/outer.current_a": 42.5}))
    assert i_meas.default_value(ctx) == 42.5
    assert outer.get_op("off").check({}, ctx) is None
    # stale measurements do not count
    ctx = Context(config, params, frames, trust=untrusted, telemetry={
        "keysight/outer.current_a": cmp.Sample(42.5, age_s=kc.T_MEASURED_FRESH_S + 1)})
    assert i_meas.default_value(ctx) == -1.
    # a watchdog sends the safe op much later: never a stale measurement
    ctx = Context(config, params, frames, trust=untrusted,
                  telemetry=_telemetry(**{"keysight/outer.current_a": 42.5}))
    assert outer.safe_request(ctx) == ("off", {"t_ramp": 50.e-3, "i_meas": 42.5})
    assert outer.safe_request(ctx, deferred=True) == ("off", {"t_ramp": 50.e-3, "i_meas": -1.})


def test_coil_hazards(config, params, frames):
    outer = _device("outer_coil")
    config["ttl"]["outer_coil_igbt"]["ttl_state"] = 0
    ctx = _ctx(config, params, frames)
    assert outer.hazard_text(ctx) is None
    config["ttl"]["outer_coil_igbt"]["ttl_state"] = 1
    config["dac"]["outer_coil_supply_current"]["voltage"] = 3.7
    assert outer.hazard_text(ctx).startswith("ON 18")
    config["dac"]["outer_coil_supply_current"]["voltage"] = 0.
    assert outer.hazard_text(ctx) is None                         # closed, no current
    # the file says off but the supply measures current
    config["ttl"]["outer_coil_igbt"]["ttl_state"] = 0
    ctx = Context(config, params, frames,
                  telemetry=_telemetry(**{"keysight/outer.current_a": 30.}))
    assert "measured 30.0 A" in outer.hazard_text(ctx)
    assert [d.key for d, _ in cmp.hazards(kc.COMPOSITE_DEVICES, ctx)] == ["outer_coil"]
    assert outer.max_on_s == kc.COIL_MAX_ON_S and outer.safe_op == "off"


def test_measured_chips(config, params, frames):
    outer = _device("outer_coil")
    config["ttl"]["outer_coil_igbt"]["ttl_state"] = 1
    config["dac"]["outer_coil_supply_current"]["voltage"] = 3.7
    i = kc.slope_i_transducer_per_v_setpoint_supply_outer * 3.7 + \
        kc.offset_i_transducer_per_v_setpoint_supply_outer
    ctx = Context(config, params, frames, telemetry=_telemetry(**{
        "keysight/outer.current_a": i + 1., "keysight/outer.output_on": True,
        "interlock/state": "tripped"}))
    levels = {m.label: level for m, _, level in outer.measured_values(ctx)}
    assert levels == {"measured": "ok", "output": "ok", "interlock": "warn"}
    ctx.telemetry["keysight/outer.current_a"] = cmp.Sample(i - 20.)
    assert outer.measured_values(ctx)[0][2] == "warn"
    assert _device("inner_coil").measured[0].source == "keysight/inner.current_a"


def test_mot_on_refusals(config, params, frames):
    mot = _device("mot")
    ctx = _ctx(config, params, frames)
    ok_args = {"i": params.i_mot, "i_meas": -1.}
    assert mot.get_op("on").check(ok_args, ctx) == []
    config["ttl"]["hbridge_helmholtz"]["ttl_state"] = 1
    assert cmp.worst(mot.get_op("on").check(ok_args, ctx)) == "error"
    config["ttl"]["hbridge_helmholtz"]["ttl_state"] = 0
    config["ttl"]["inner_coil_igbt"]["ttl_state"] = 1
    config["dac"]["inner_coil_supply_current"]["voltage"] = 106.5 / 17.     # magtrap
    found = mot.get_op("on").check(ok_args, ctx)
    assert any("ramp it down" in c.message for c in found)
    body = OpTable(kc.COMPOSITE_DEVICES).get("mot.on").body
    for guard in ("inner coil PID is on", "H-bridge is in Helmholtz",
                  "inner coil above the MOT current"):
        assert body.index(guard) < body.index("expt.load_2D_mot(")
    # Cooling's "use the default" sentinel is 100.
    from kexp.base import cooling
    assert kc.I_MOT_MAX < cooling.dv


def test_shim_z_flip_needs_zero(config, params, frames):
    shims = _device("shims")
    ctx = _ctx(config, params, frames)
    config["dac"]["zshim_current_control"]["voltage"] = 0.8
    assert shims.get_op("z_flipped").check({}, ctx).is_error
    config["dac"]["zshim_current_control"]["voltage"] = 0.
    assert shims.get_op("z_flipped").check({}, ctx) is None


def test_every_ttl_pulse_is_followed_by_an_explicit_off():
    """TTL_OUT.pulse leaves the cached level as it was; the write-back after an
    op must describe the line as low."""
    pulsers = {"expt.lightsheet.off()": "expt.lightsheet.pid_int_zero_ttl.off()",
               "expt.lightsheet.zero_pid()": "expt.lightsheet.pid_int_zero_ttl.off()",
               "expt.ry_405.set_power(": "expt.ry_405.ttl_pid_clear.off()",
               "expt.ry_980.set_power(": "expt.ry_980.ttl_pid_clear.off()",
               "expt.tweezer.on(": "expt.tweezer.pid1_int_hold_zero.off()"}
    for entry in OpTable(kc.COMPOSITE_DEVICES):
        body = entry.body
        for m in re.finditer(r"(expt(?:\.\w+)+)\.pulse\(", body):
            assert body.find(f"{m.group(1)}.off()", m.end()) > 0, entry.name
        for call, off in pulsers.items():
            if call in body:
                assert body.find(off, body.index(call)) > 0, f"{entry.name}: {call}"


def test_tweezer_on_makes_the_pid_ao_setpoints_explicit():
    body = OpTable(kc.COMPOSITE_DEVICES).get("tweezer.on").body
    assert body.index("ao1_dds.update_dac_setpoint(0.)") < body.index("expt.tweezer.on(")
    assert body.index("ao2_dds.update_dac_setpoint(expt.tweezer.pid2_dac.v)") \
        < body.index("expt.tweezer.on(")


def test_kernel_range_checks_come_first():
    table = OpTable(kc.COMPOSITE_DEVICES)
    for name in ("imaging.on", "imaging.set_detuning"):
        body = table.get(name).body
        assert body.index("imaging_detuning_to_beat_ref") < body.index("set_imaging_detuning")
    for name, first_write in (("raman.on", "expt.ttl.quantum_machines"),
                              ("raman.set", "expt.raman.set(")):
        body = table.get(name).body
        assert body.index("outside the DDS range") < body.index(first_write)


def test_params_links_exist_and_d1_vpd_is_not_linked(params):
    for device in kc.COMPOSITE_DEVICES:
        for arg in device.fields:
            if arg.param:
                assert hasattr(params, arg.param), f"{device.key}.{arg.name} -> {arg.param}"
    assert not _device("d1_gm").get_field("v_c").param      # derived in compute_derived


def test_scenes_validate_and_resolve(config, params, frames):
    table = OpTable(kc.COMPOSITE_DEVICES)
    cmp.validate_scenes(kc.COMPOSITE_SCENES, table)
    scene = next(s for s in kc.COMPOSITE_SCENES if s.key == "outer_field_hold")
    ctx = _ctx(config, params, frames)
    req = scene.resolve(table, {"i": 25., "hold": 12.}, ctx)
    assert req["steps"][0]["args"]["i"] == 25. and req["steps"][1]["hold"] == 12.
    # the cleanup runs later: it must not replay a measurement
    assert req["finally"][0]["op"] == "outer_coil.off"
    assert req["finally"][0]["args"]["i_meas"] == -1.


# --- tweezer -----------------------------------------------------------------------

def test_trap_checks(config, params, frames):
    table = _device("tweezer").get_table("traps")
    ctx = _ctx(config, params, frames)
    assert table.checks([[72.e6, 0.3], [78.e6, 0.3]], ctx) == []
    found = table.checks([[72.e6, 0.6], [78.e6, 0.6]], ctx)
    assert found[0].is_error and "sum" in found[0].message
    found = table.checks([[75.e6, 0.2]], ctx)                        # the default trap
    assert [c.level for c in found] == ["warn"] and "mesh" in found[0].message
    assert table.default_rows(ctx) == [[float(f), float(a)] for f, a in
                                       zip(params.frequency_tweezer_list, params.amp_tweezer_list)]


class FakeCore:
    def __init__(self, log, idx):
        self.log, self.idx = log, idx

    def amp(self, a):
        self.log.append(("amp", self.idx, a))


class FakeDDS:
    def __init__(self):
        self.log = []

    def __getitem__(self, idx):
        return FakeCore(self.log, idx)

    def exec_at_trg(self):
        self.log.append(("exec",))

    def write(self):
        self.log.append(("write",))


class FakeTweezer:
    def __init__(self):
        self.dds = FakeDDS()
        self.static = []
        self.card = object()

    def set_static_tweezers(self, freqs, amps, phases=None):
        self.static.append((list(freqs), list(amps), phases))


def test_awg_write_zeroes_tones_that_were_removed():
    tw = FakeTweezer()
    kc._awg_write(tw, [[72.e6, 0.2], [73.e6, 0.2], [74.e6, 0.2]])
    assert tw._panel_n_tones == 3
    tw.dds.log.clear()
    kc._awg_write(tw, [[72.e6, 0.3]])
    assert tw.static[-1] == ([72.e6], [0.3], None)
    assert ("amp", 1, 0.) in tw.dds.log and ("amp", 2, 0.) in tw.dds.log
    assert tw.dds.log[-2:] == [("exec",), ("write",)]
    assert kc.tweezer_host_state(SimpleNamespace(tweezer=tw)) == {
        "awg_connected": True, "traps": [[72.e6, 0.3]]}


def test_awg_write_all_zero_amplitudes_passes_explicit_phases():
    tw = FakeTweezer()
    kc._awg_write(tw, [[72.e6, 0.0], [73.e6, 0.0]])
    assert tw.static[-1][2] == [0., 0.]       # compute_tweezer_phases would divide by 0


def test_awg_apply_needs_a_connection():
    tw = FakeTweezer()
    tw.card = None
    with pytest.raises(RuntimeError, match="not connected"):
        kc.awg_apply(SimpleNamespace(tweezer=tw), {}, {"traps": [[72.e6, 0.1]]})
