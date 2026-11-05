"""The fast feedback path plays the same RTIO events as the standard path.

FeedbackExptFast overlaps the ADC read with the posterior and pre-issues the next read, so it
writes its events in a different order; its claim is that the machine sees the same thing
(alias_grid/base_expt_feedback_fast.py). Here both classes' real feedback_loop, real waxx
wrappers and real ARTIQ drivers run on the host down to rtio_output (fastpath_rtio_harness.py),
on the narrow grid of the 2026-10-29/30 overnight runs, and the two event streams are compared
event by event: timestamp, channel + address, data word.

The comparison needs the same slack in both: slack sets the gap, so a smaller slack is a
different experiment, not a different path. The gap is shared code
(Feedback.compute_t_between_pulses_mu). test_stream_diff_sees_8_ns is the control that a
difference would be seen, and test_the_fast_arm_really_overlaps that the fast arm is not
quietly the standard loop.

Out of reach here: CPU time (underflows) and the compiled kernel's float rounding. Those are
the on-hardware steps. Skipped when %db% / %code% are not set.
"""
import os

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

import fastpath_rtio_harness as h  # noqa: E402

SLACKS_MU = (39696, 20000, 16000)   # the overnight value; the fast path's usual range
OFFSETS = (0.0, 9. / 9.5, -9. / 9.5, 3. / 9.5)  # the ends and an interior point of fbna_FB_c7s0


def _reads(seed, n=h.NARROW_GRID["N_pulses"]):
    # the APD range of a real run (#90202: -141 / -179 mV) plus a little either side
    return list(np.random.default_rng(seed).uniform(-0.190, -0.130, n))


def _key(e):
    return (e.t, e.target, e.data)


@pytest.fixture(scope="module")
def arms(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("fastpath")
    with pytest.MonkeyPatch.context() as mp:
        # FeedbackExpt's default is the fastest loop since 2026-11-04: the standard arm asks for 0
        std, dm_std = h.build(mp, tmp, fast=False, fast_path=0)
        fast, dm_fast = h.build(mp, tmp, fast=True)
        yield mp, std, fast
        dm_std.close_devices()
        dm_fast.close_devices()


def _pair(arms, reads, slack_mu=h.NARROW_GRID["slack_mu"], offset=0.0, update=1):
    # always all three: the arms are shared by every test, so a setting left out would be the
    # previous test's
    mp, std, fast = arms
    kw = dict(slack_mu=slack_mu, offset=offset, update=update)
    ev_s, r_s = h.run_train(mp, std, reads, **kw)
    ev_f, r_f = h.run_train(mp, fast, reads, **kw)
    return ev_s, r_s, ev_f, r_f


@pytest.mark.parametrize("slack_mu", SLACKS_MU)
@pytest.mark.parametrize("offset", OFFSETS)
@pytest.mark.parametrize("update", (1, 0))
def test_same_events_same_outputs_at_the_same_slack(arms, slack_mu, offset, update):
    ev_s, r_s, ev_f, r_f = _pair(arms, _reads(int(slack_mu + 100 * offset + update)),
                                 slack_mu=slack_mu, offset=offset, update=update)
    assert len(ev_s) == len(ev_f)
    only_std = sorted(set(map(_key, ev_s)) - set(map(_key, ev_f)))
    only_fast = sorted(set(map(_key, ev_f)) - set(map(_key, ev_s)))
    assert not only_std and not only_fast, (only_std[:5], only_fast[:5])
    assert sorted(map(_key, ev_s)) == sorted(map(_key, ev_f))   # with multiplicity
    assert r_s.t_end == r_f.t_end
    assert r_s.n_reads == r_f.n_reads == h.NARROW_GRID["N_pulses"]
    for name in ("omega_drives", "apd", "t", "s_z", "P0"):
        assert np.array_equal(getattr(r_s, name), getattr(r_f, name)), name
    assert r_s.omega_raman == r_f.omega_raman


def test_the_decoded_read_is_the_requested_voltage(arms):
    """The fast path decodes the SPI word itself (a copy of Sampler_Last_CH.sample_single):
    the same word gives the same volts, one ADC LSB from the value asked for."""
    reads = _reads(5)
    _, r_s, _, r_f = _pair(arms, reads)
    lsb = 20. / 65536
    assert np.max(np.abs(r_f.apd - np.array(reads))) <= lsb
    assert np.array_equal(r_f.apd, r_s.apd)


def test_the_adaptive_drive_depends_on_the_reads(arms):
    """So the agreement above is not two loops ignoring their reads."""
    _, r_a, _, _ = _pair(arms, _reads(1))
    _, r_b, _, _ = _pair(arms, _reads(2))
    assert not np.array_equal(r_a.omega_drives[1:], r_b.omega_drives[1:])
    assert not np.array_equal(r_a.P0, r_b.P0)
    assert np.max(r_a.P0) > 1.15 / len(r_a.P0)      # a real posterior, not the flat fallback


def test_stream_diff_sees_8_ns(arms):
    """The sensitivity control: the smallest gap step (slack + 8 mu) changes the stream."""
    mp, std, fast = arms
    reads = _reads(3)
    ev_a, _ = h.run_train(mp, fast, reads, slack_mu=39696, offset=0.0, update=1)
    ev_b, _ = h.run_train(mp, fast, reads, slack_mu=39704, offset=0.0, update=1)
    assert sorted(map(_key, ev_a)) != sorted(map(_key, ev_b))


def _imaging_on_writes(exp, events):
    target = exp.imaging.dds_sw.dds_device.sw.target_o
    return [e for e in events if e.target == target and e.data == 1]


def test_the_fast_arm_really_overlaps(arms):
    """The fast arm writes read i+1's imaging pulse before it reaches pulse i+1's DDS events:
    timestamps go backwards at each pre-issue. The standard arm writes them in step order."""
    mp, std, fast = arms
    reads = _reads(4)
    ev_s, r_s, ev_f, r_f = _pair(arms, reads)
    train_s, train_f = ev_s[r_s.n_setup:], ev_f[r_f.n_setup:]
    raman_sw = std.raman.dds_sw.dds_device.sw.target_o
    for ev, exp, expect_preissue in ((train_s, std, False), (train_f, fast, True)):
        raman_on = [e for e in ev if e.target == raman_sw and e.data == 1]
        img_on = _imaging_on_writes(exp, ev)
        assert len(raman_on) == len(img_on) == h.NARROW_GRID["N_pulses"]
        for i in range(1, len(img_on)):
            # write order: the imaging pulse of step i against the raman pulse of step i
            preissued = img_on[i].seq < raman_on[i].seq
            assert preissued == expect_preissue, i
            assert img_on[i].t > raman_on[i].t        # the timeline does not change


def test_the_read_comes_after_the_propagate_half(arms, monkeypatch):
    """The order the fast path exists for: propagate_hypotheses runs between the ADC's SPI
    submit and its blocking read."""
    mp, std, fast = arms
    calls = []
    propagate = fast.propagate_hypotheses
    weigh = fast.weigh_hypotheses
    monkeypatch.setattr(fast, "propagate_hypotheses",
                        lambda *a, **k: (calls.append("propagate"), propagate(*a, **k))[1])
    monkeypatch.setattr(fast, "weigh_hypotheses",
                        lambda *a, **k: (calls.append("weigh"), weigh(*a, **k))[1])
    h.run_train(mp, fast, _reads(6), slack_mu=39696, offset=0.0, update=1)
    assert calls == ["propagate", "weigh"] * h.NARROW_GRID["N_pulses"]


@pytest.mark.parametrize("slack_mu", SLACKS_MU)
def test_no_sequence_error_is_predicted(arms, slack_mu):
    """An RTIO sequence error raises nothing and drops the event; it shows only in the core
    log. Screen for it with the SED's lane rule, in the write order of each path. The standard
    path is the model's own check: it has run for months with none in the core log."""
    ev_s, _, ev_f, _ = _pair(arms, _reads(7), slack_mu=slack_mu)
    m_s, m_f = h.lane_model(ev_s), h.lane_model(ev_f)
    assert m_s["n_sequence_errors"] == 0, m_s
    assert m_f["n_sequence_errors"] == 0, m_f
    # the pre-issue is the only new rewind: one per pulse after the first
    assert m_f["n_rewinds"] - m_s["n_rewinds"] == h.NARROW_GRID["N_pulses"] - 1
