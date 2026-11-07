"""The fastest loop's first-gap stretch (p.fastest_first_gap_extra_mu, default 5 us; user 2026-11-05:
"lengthen only the first gap if it gets rid of the 5us").

The same train with the stretch at 0 and at E: step 0 is the same event for event (its read still starts
right after its pulse); every later event is exactly E later; step 0 does not chain (step 1's IO_UPDATE and
pulse-on are the CPU's, as every bench rung ran); the phase each later step hands the posterior is the
unstretched one plus the drive's phase over E; t is E later; no sequence error. On the host down to
rtio_output (fastpath_rtio_harness.py). Skipped without %db% / %code%.
"""
import os

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

import fastpath_rtio_harness as h  # noqa: E402

E = 5000
SLACKS_MU = (39696, -416)      # the standard loop's, and the fastest default at m 21 (T ~ 26.6 us)


def _reads(seed, n=h.NARROW_GRID["N_pulses"]):
    return list(np.random.default_rng(seed).uniform(-0.190, -0.130, n))


@pytest.fixture(scope="module")
def fst(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("first_gap")
    with pytest.MonkeyPatch.context() as mp:
        exp, dm = h.build(mp, tmp, fast=False)
        assert exp.fast_loop == 1 and int(exp.p.fast_path) == 2
        # what the run records: the lean posterior; the stretch auto, so E only with the table's slack
        # (this harness experiment sets its own slack: then none)
        auto_slack = int(exp.p.fastest_slack_auto) == 1
        assert int(exp.p.fastest_first_gap_extra_mu) == (E if auto_slack else 0)
        assert int(exp.p.fastest_posterior) == 1
        yield mp, exp
        dm.close_devices()


def _train(fst, reads, extra, slack_mu, update):
    mp, exp = fst
    phases = []
    with pytest.MonkeyPatch.context() as m2:
        lp = type(exp).lean_propagate
        m2.setattr(exp, "lean_propagate", lambda t, phase=0.: (phases.append((t, phase)), lp(exp, t, phase))[1])
        ev, r = h.run_train(mp, exp, reads, slack_mu=slack_mu, offset=0.0, update=update,
                            fastest={"fastest_first_gap_extra_mu": extra})
    r.phases = np.array(phases)
    return ev, r


@pytest.mark.parametrize("slack_mu", SLACKS_MU)
@pytest.mark.parametrize("update", (0, 1))
def test_the_first_gap_alone_is_longer(fst, slack_mu, update):
    mp, exp = fst
    reads = _reads(int(slack_mu % 1000 + update))
    ev0, r0 = _train(fst, reads, 0, slack_mu, update)
    ev1, r1 = _train(fst, reads, E, slack_mu, update)
    n = h.NARROW_GRID["N_pulses"]
    sw = exp.raman.dds_sw.dds_device.sw.target_o
    on0 = sorted(e.t for e in ev0 if e.target == sw and e.data == 1)
    on1 = sorted(e.t for e in ev1 if e.target == sw and e.data == 1)
    assert len(on0) == len(on1) == n
    # the pulses: the first at the same time, every later one E later
    assert on1[0] == on0[0]
    assert np.array_equal(np.diff(on1) - np.diff(on0), np.r_[E, np.zeros(n - 2, dtype=int)])

    # every event: before step 1's frequency word (within its 3 us pretrigger) the same, after it E later.
    # Timestamps and channels always; data words too with a fixed drive (an adaptive drive sees a
    # different t from step 1 on, so its words differ, not their times)
    cut = on0[1] - 3000
    key = (lambda e: (e.t, e.target, e.data)) if update == 0 else (lambda e: (e.t, e.target))
    moved0 = sorted(key(e._replace(t=e.t + (E if e.t >= cut else 0))) for e in ev0)
    assert moved0 == sorted(key(e) for e in ev1)

    # step 0 does not chain: step 1's pulse-on is written after step 1's frequency word (the CPU's), while
    # without the stretch the step-0 read trace carries it, before; later steps chain in both
    data_target = exp.raman._fw_data_target
    for ev, step1_chained in ((ev0, True), (ev1, False)):
        on = [e for e in ev if e.target == sw and e.data == 1]
        for i, e in enumerate(on[1:], start=1):
            words = [w for w in ev if w.target == data_target and w.t < e.t]
            chained = e.seq < words[-1].seq
            assert chained == (step1_chained if i == 1 else True), (i, step1_chained)

    # the posterior's inputs: the same reads; t and phase from step 1 on moved by E and the drive's phase over E
    assert np.array_equal(r0.apd, r1.apd)
    np.testing.assert_allclose(r1.phases[1:, 0] - r0.phases[1:, 0], E * 1e-9, rtol=0, atol=1e-15)
    assert r1.phases[0, 0] == r0.phases[0, 0]
    # the tracker is never reset between trains (on the machine neither): the two trains' phases differ by a
    # common offset, the same at every step, which turns every hypothesis alike. Compare to step 0's.
    offset = r1.phases[0, 1] - r0.phases[0, 1]
    if update == 0:
        q = 2 * np.pi / 32768
        # the drive phase over E: the DDS phase advance the tracker integrates, two-photon
        expect = r0.omega_drives[0] * E * 1e-9
        d = (r1.phases[1:, 1] - r0.phases[1:, 1] - offset - expect + np.pi) % (2 * np.pi) - np.pi
        # the tracker integrates the chip's words: the FTW's LSB (|df| < .5 Hz) over E plus 4 phase-word steps
        assert np.all(np.abs(d) <= 2 * np.pi * 0.5 * E * 1e-9 + 4 * q), d
    m = h.lane_model(ev1)
    assert m["n_sequence_errors"] == 0, m


def test_the_standard_loop_records_no_stretch_and_the_library_posterior(tmp_path, monkeypatch):
    exp, dm = h.build(monkeypatch, tmp_path, fast=False, fast_path=0)
    try:
        assert int(exp.p.fast_path) == 0
        assert int(exp.p.fastest_first_gap_extra_mu) == 0 and int(exp.p.fastest_posterior) == 0
    finally:
        dm.close_devices()


@pytest.mark.parametrize("extra", (0, E))
def test_replay_rebuilds_the_stretched_timeline(fst, extra):
    """kexp.analysis.feedback replays a run from its params: the per-step gaps from the kernel's formula
    (_compute_dT_rr_mu), plus the recorded first-gap stretch since 2026-11-05. The rebuilt data.t must be
    the kernel's to the ns, with and without the stretch."""
    from types import SimpleNamespace
    from kexp.analysis.feedback import FeedbackReplayCore
    mp, exp = fst
    ev, r = _train(fst, _reads(11), extra, -416, 1)
    p = exp.p
    rec = SimpleNamespace(fast_path=2, fastest_first_gap_extra_mu=np.int64(extra))
    fr = FeedbackReplayCore.__new__(FeedbackReplayCore)
    fr._default_timing = {"first_gap_extra_mu": FeedbackReplayCore._recorded_first_gap_extra_mu(rec)}
    fr._t_between_base_mu = int(p.t_calculation_slack_compensation_mu + p.t_raman_set_pretrigger_mu
                                + np.int64(float(p.t_img_pulse) * 1e9) + p.t_fifo_mu)
    fr._t_between_base_valid = True
    dT = fr._compute_dT_rr_mu(r.t_pulses[None, :])[0]
    t_in = np.concatenate(([0], np.cumsum(dT[:-1]))) * 1e-9
    np.testing.assert_allclose(t_in + r.t_pulses + float(p.t_img_pulse), r.t, rtol=0, atol=1e-15)
    # a standard-loop run, or one from before the stretch, replays with none
    assert FeedbackReplayCore._recorded_first_gap_extra_mu(SimpleNamespace(fast_path=0, fastest_first_gap_extra_mu=E)) == 0
    assert FeedbackReplayCore._recorded_first_gap_extra_mu(SimpleNamespace(fast_path=2)) == 0
