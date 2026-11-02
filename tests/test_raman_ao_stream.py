"""RamanBeamPair AO modes on the real feedback_loop, down to rtio_output (fastpath_rtio_harness.py).

RAMAN_AO_BOTH must write the same events as the committed raman_beams.py: every method of the
class is swapped for the one at git HEAD and the two streams are compared event by event.
RAMAN_AO_SINGLE must leave the static DDS's bus and io_update alone during the train, and drive
the same frequencies. CPU time and the compiled kernel are out of reach here. Skipped when
%db% / %code% are not set, or when the file at HEAD predates the modes' removal of a method.
"""
import os
import subprocess
import types

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

import fastpath_rtio_harness as h  # noqa: E402
from waxx.control import raman_beams as rb  # noqa: E402

OFFSETS = (0.0, 9. / 9.5, -9. / 9.5, 3. / 9.5)
SLACKS_MU = (39696, 21000)


def _reads(seed):
    return list(np.random.default_rng(seed).uniform(-0.190, -0.130, h.NARROW_GRID["N_pulses"]))


def _key(e):
    return (e.seq, e.t, e.target, e.data)


def _head_class():
    wax = os.path.join(os.environ["code"], "wax")
    src = subprocess.check_output(["git", "-C", wax, "show", "HEAD:waxx-src/waxx/control/raman_beams.py"], text=True)
    assert "set_ao_mode" not in src, "HEAD already has the AO modes: compare against the commit before them"
    mod = types.ModuleType("raman_beams_head")
    mod.__dict__["__file__"] = "raman_beams_head.py"
    exec(compile(src, "raman_beams_head.py", "exec"), mod.__dict__)
    return mod.RamanBeamPair


def _reset(exp):
    """The state a train carries over: the phase accumulators and the words the chips hold."""
    r = exp.raman
    r._phi0_mu = np.int64(0)
    r._phi1_mu = np.int64(0)
    for dds in (r.dds0, r.dds1):
        dds._ftw = np.int32(0)
        dds._last_ftw = np.int32(0)


@pytest.fixture(scope="module")
def arm(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ao_stream")
    with pytest.MonkeyPatch.context() as mp:
        exp, dm = h.build(mp, tmp, fast=True)
        yield mp, exp
        dm.close_devices()


@pytest.mark.parametrize("slack_mu", SLACKS_MU)
@pytest.mark.parametrize("offset", OFFSETS)
@pytest.mark.parametrize("update", (1, 0))
def test_both_writes_what_head_writes(arm, slack_mu, offset, update):
    mp, exp = arm
    reads = _reads(int(slack_mu + 100 * offset + update))
    kw = dict(slack_mu=slack_mu, offset=offset, update=update)
    _reset(exp)
    now, r_now = h.run_train(mp, exp, reads, **kw)
    head = _head_class()
    with pytest.MonkeyPatch.context() as sw:
        for name, fn in vars(head).items():
            if callable(fn) and not name.startswith('__'):
                sw.setattr(rb.RamanBeamPair, name, fn)
        _reset(exp)
        then, r_then = h.run_train(mp, exp, reads, **kw)
    assert len(now) == len(then)
    assert [_key(e) for e in now] == [_key(e) for e in then]
    assert np.array_equal(r_now.omega_drives, r_then.omega_drives)
    assert np.array_equal(r_now.P0, r_then.P0)


def _single(exp, ref):  # after _reset
    """As a run would: the mode set in prepare, the DDSes holding the reference pair."""
    exp.raman.set_ao_mode(rb.RAMAN_AO_SINGLE, ref)
    for dds, f in ((exp.raman.dds0, exp.raman._ao_ref_f0), (exp.raman.dds1, exp.raman._ao_ref_f1)):
        dds._ftw = int(np.int32(round(dds.dds_device.ftw_per_hz * f)))
        dds._last_ftw = dds._ftw


@pytest.mark.parametrize("offset", OFFSETS)
def test_single_leaves_the_static_dds_alone(arm, offset):
    mp, exp = arm
    ref = float(exp.p.frequency_raman_transition)
    both_uses = (exp.raman._ao_uses0, exp.raman._ao_uses1)
    reads = _reads(abs(int(1000 * offset)) + 7)
    _reset(exp)
    ev_both, r_both = h.run_train(mp, exp, reads, offset=offset, update=1, slack_mu=39696)
    _reset(exp)
    _single(exp, ref)
    try:
        assert exp.raman._ao_moving == rb.DDS0_IDX
        ev, r = h.run_train(mp, exp, reads, offset=offset, update=1, slack_mu=39696)
    finally:
        exp.raman.set_ao_mode(rb.RAMAN_AO_BOTH)
    assert (exp.raman._ao_uses0, exp.raman._ao_uses1) == both_uses
    static = exp.raman.dds1.dds_device
    bus = static.bus.channel
    io = static.cpld.io_update.channel
    train = ev[r.n_setup:]
    both_train = ev_both[r_both.n_setup:]
    if bus != exp.raman.dds0.dds_device.bus.channel:
        assert sum((e.target >> 8) == bus for e in both_train) > 0
        n = sum((e.target >> 8) == bus for e in train)
        assert n < sum((e.target >> 8) == bus for e in both_train)
    if io != exp.raman.dds0.dds_device.cpld.io_update.channel:
        assert sum((e.target >> 8) == io for e in train) < sum((e.target >> 8) == io for e in both_train)
    assert len(train) < len(both_train)
    assert np.allclose(r.omega_drives, r_both.omega_drives, atol=2 * np.pi * 1., rtol=0.)


@pytest.mark.parametrize("offset", OFFSETS)
@pytest.mark.parametrize("slack_mu", SLACKS_MU)
def test_direct_writes_the_single_events(arm, offset, slack_mu):
    """prepare_direct_fast_path: same events on the wire, FTW data within 1 LSB."""
    mp, exp = arm
    ref = float(exp.p.frequency_raman_transition)
    reads = _reads(abs(int(1000 * offset)) + slack_mu)
    kw = dict(offset=offset, update=1, slack_mu=slack_mu)
    _reset(exp)
    _single(exp, ref)
    try:
        ev_w, r_w = h.run_train(mp, exp, reads, **kw)
        _reset(exp)
        _single(exp, ref)
        exp.raman.prepare_direct_fast_path()
        ev_d, r_d = h.run_train(mp, exp, reads, **kw)
    finally:
        exp.raman.set_ao_mode(rb.RAMAN_AO_BOTH)
    assert exp.raman._fw_on == 0
    assert len(ev_w) == len(ev_d)
    data_target = exp.raman.dds0.dds_device.bus.channel << 8
    n_ftw = 0
    for w, d in zip(ev_w, ev_d):
        assert (w.t, w.target) == (d.t, d.target)
        if w.data != d.data:
            assert w.target == data_target and abs(int(w.data) - int(d.data)) <= 1
            n_ftw += 1
    assert n_ftw <= h.NARROW_GRID["N_pulses"]
    assert np.allclose(r_d.omega_drives, r_w.omega_drives, atol=1.e-3, rtol=0.)


def test_direct_survives_a_set_mid_train(arm):
    """raman.set() invalidates the stage, as a phase write does: the next update must take the
    wrapper fallback, then the direct path again, and leave the cached frequency right."""
    mp, exp = arm
    ref = float(exp.p.frequency_raman_transition)
    reads = _reads(11)
    _reset(exp)
    _single(exp, ref)
    exp.raman.prepare_direct_fast_path()
    calls = []

    def hook(idx=0):
        if idx == 3:
            exp.raman._invalidate_fast_frequency_update_state()
            calls.append(idx)

    orig = exp.per_feedback_loop_end
    exp.per_feedback_loop_end = hook
    try:
        ev, r = h.run_train(mp, exp, reads, offset=0.0, update=1, slack_mu=39696)
    finally:
        exp.per_feedback_loop_end = orig
    moving = exp.raman.dds0
    assert calls == [3]
    assert moving.frequency == pytest.approx(moving.dds_device.ftw_to_frequency(moving._ftw), abs=1.e-6, rel=0.)
    assert moving.frequency > 1.e6
    exp.raman.set_ao_mode(rb.RAMAN_AO_BOTH)
