"""The fastest loop (FeedbackExpt's default) puts the same light and the same reads on the machine
as the standard loop, and gets the same posterior from them.

Both loops of FeedbackExpt (p.fast_path 2 and 0) run on the host down to rtio_output
(fastpath_rtio_harness.py, with DMA record/playback emulated), on the narrow grid of the 2026-10-29/30
overnight runs, with the same APD reads. What must agree:

  * the Raman pulses: every switch on and off at the same timestamp;
  * the read: integrator gate and reset, imaging switch, ADC conversion and SPI write, each shifted by
    one constant per read of 0-15 ns (the fastest read starts on the 8 ns grid after the pulse end;
    the standard read at it), never earlier;
  * the IO_UPDATE of the moving AO: at a timestamp the standard loop also pulses it;
  * the decoded reads and t exactly; the phase each loop hands the posterior to within the 1-LSB
    frequency difference (the single-AO word can differ from the both-AO split by 1 LSB, .23 Hz, per
    AO: its drift over the train <= 2 pi x 1 Hz x t + one phase-word step, and exactly 0 at a fixed
    drive on the anchor); the drives to 1 Hz;
    the posterior to 2e-4 and s_z to 2e-3 absolute (a few 1e-3 rad of phase moves them about 1e-5).

What it does not show: the event streams differ on purpose in the DDS SPI words (one AO moves, not
two) and in write order (DMA playback, pre-issued pulse-on); CPU time and the compiled kernel's
rounding are the on-hardware steps. Skipped without %db% / %code%.
"""
import os

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

import fastpath_rtio_harness as h  # noqa: E402

SLACKS_MU = (39696, 20000, 3896)
OFFSETS = (0.0, 9. / 9.5, -9. / 9.5, 3. / 9.5)


def _reads(seed, n=h.NARROW_GRID["N_pulses"]):
    return list(np.random.default_rng(seed).uniform(-0.190, -0.130, n))


@pytest.fixture(scope="module")
def arms(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("fastest")
    with pytest.MonkeyPatch.context() as mp:
        std, dm_std = h.build(mp, tmp, fast=False, fast_path=0)
        fst, dm_fst = h.build(mp, tmp, fast=False)
        assert std.fast_loop == 0 and int(std.p.fast_path) == 0
        assert fst.fast_loop == 1 and int(fst.p.fast_path) == 2
        yield mp, std, fst
        dm_std.close_devices()
        dm_fst.close_devices()


# The comparison runs the fastest loop with no first-gap stretch: the standard loop's gaps are uniform, and
# the stretch is tested on its own (test_fastest_first_gap.py). The posterior is the fastest loop's default,
# the lean one, so this also holds it against the library's through the whole RTIO stream.
FASTEST_UNIFORM = {"fastest_first_gap_extra_mu": 0}


def _pair(arms, reads, slack_mu=h.NARROW_GRID["slack_mu"], offset=0.0, update=1, fastest=None):
    """Both trains; each result also carries .phases, the (t, phase) each posterior update got."""
    mp, std, fst = arms
    kw = dict(slack_mu=slack_mu, offset=offset, update=update)
    fastest = dict(FASTEST_UNIFORM, **(fastest or {}))
    ph_s, ph_f = [], []
    with pytest.MonkeyPatch.context() as m2:
        gp = type(std).generate_posterior
        m2.setattr(std, "generate_posterior",
                   lambda k, t, phase_raman_pulse_start=0., **k2:
                   (ph_s.append((t, phase_raman_pulse_start)),
                    gp(std, k, t, phase_raman_pulse_start=phase_raman_pulse_start, **k2))[1])
        # whichever posterior the fastest loop runs: record the (t, phase) each half gets
        pr = type(fst).propagate_hypotheses
        m2.setattr(fst, "propagate_hypotheses",
                   lambda t, phase=0.: (ph_f.append((t, phase)), pr(fst, t, phase))[1])
        lp = type(fst).lean_propagate
        m2.setattr(fst, "lean_propagate",
                   lambda t, phase=0.: (ph_f.append((t, phase)), lp(fst, t, phase))[1])
        ev_s, r_s = h.run_train(mp, std, reads, **kw)
        ev_f, r_f = h.run_train(mp, fst, reads, fastest=fastest, **kw)
    r_s.phases, r_f.phases = np.array(ph_s), np.array(ph_f)
    return ev_s, r_s, ev_f, r_f


def _on_channel(events, target):
    return sorted((e.t, e.data) for e in events if e.target == target)


def _targets(exp):
    integ = exp.integrator
    sampler = integ.sampler_ch.sampler_device
    return dict(
        raman_sw=exp.raman.dds_sw.dds_device.sw.target_o,
        imaging_sw=exp.imaging.dds_sw.dds_device.sw.target_o,
        integrate=integ.ttl_integrate.ttl_device.target_o,
        reset=integ.ttl_reset.ttl_device.target_o,
        cnv=sampler.cnv.target_o,
        adc_data=(sampler.bus_adc.channel << 8) | 0,   # SPI_DATA_ADDR
    )


@pytest.mark.parametrize("posterior", (1, 0))
@pytest.mark.parametrize("slack_mu", SLACKS_MU)
@pytest.mark.parametrize("offset", OFFSETS)
@pytest.mark.parametrize("update", (1, 0))
def test_same_light_same_reads_same_posterior(arms, slack_mu, offset, update, posterior):
    mp, std, fst = arms
    ev_s, r_s, ev_f, r_f = _pair(arms, _reads(int(slack_mu + 100 * offset + update)),
                                 slack_mu=slack_mu, offset=offset, update=update,
                                 fastest={"fastest_posterior": posterior})
    n = h.NARROW_GRID["N_pulses"]
    tg = _targets(std)
    assert tg == _targets(fst)

    # the Raman pulses, exactly
    raman_s, raman_f = _on_channel(ev_s, tg["raman_sw"]), _on_channel(ev_f, tg["raman_sw"])
    assert len(raman_s) == 2 * n and raman_s == raman_f

    # the read: one shift per read, 0-15 ns, the same on every read channel
    pulse_end = [t for t, d in raman_s if d == 0]
    shifts = None
    for name in ("imaging_sw", "integrate", "reset", "cnv", "adc_data"):
        s, f = _on_channel(ev_s, tg[name]), _on_channel(ev_f, tg[name])
        assert len(s) == len(f) > 0, name
        assert [d for _, d in s] == [d for _, d in f], name
        per = len(s) // n
        assert per * n == len(s), name
        d = np.array([tf - ts for (ts, _), (tf, _) in zip(s, f)]).reshape(n, per)
        assert np.all(d == d[:, :1]), (name, d)
        if shifts is None:
            shifts = d[:, 0]
        assert np.array_equal(d[:, 0], shifts), name
    assert np.all((shifts >= 0) & (shifts <= 15)), shifts
    img_on = [t for t, dd in _on_channel(ev_f, tg["imaging_sw"]) if dd == 1]
    assert all(t >= te for t, te in zip(img_on, pulse_end))

    # the moving AO's IO_UPDATE lands where the standard loop pulses it
    io = fst.raman._fw_io_target
    t_last = raman_s[-1][0]     # before the host harness's clean_up_fast_frequency_update
    io_f = [t for t, dd in _on_channel(ev_f, io) if dd == 1 and t < t_last]
    io_s = {t for t, dd in _on_channel(ev_s, io) if dd == 1 and t < t_last}
    assert set(io_f) <= io_s
    # exactly one before each pulse, within the pretrigger
    for t_on in [t for t, dd in raman_s if dd == 1]:
        assert sum(1 for t in io_f if t_on - 3000 < t < t_on) == 1, t_on

    # the same reads; the phase to the frequency word's LSB; then drives and posterior
    assert r_s.n_reads == r_f.n_reads == n
    assert np.array_equal(r_s.apd, r_f.apd)
    assert np.array_equal(r_s.t, r_f.t)
    assert np.array_equal(r_s.phases[:, 0], r_f.phases[:, 0])
    # the tracker is never reset (on the machine neither): earlier trains' differences are a
    # common offset at t = 0, which turns every hypothesis alike about z and no read sees. What
    # must stay small is the drift within the train: the frequency words' LSB (|df| <= 1 Hz two-photon)
    # plus the tracker's own quantisation (each >> 16 drops a fraction, up to 4 phase-word steps
    # of 2 pi / 32768 a pulse, residues that differ between the two AO splits).
    q = 2 * np.pi / 32768
    dphi = (r_f.phases[:, 1] - r_s.phases[:, 1] + np.pi) % (2 * np.pi) - np.pi
    drift = dphi - dphi[0]
    bound = 2 * np.pi * 1.0 * r_s.phases[:, 0] + 4 * q * np.arange(n) + 1e-9
    # with an adaptive drive, a posterior near-tie can break differently on a 1e-4 difference: the
    # drives then part by grid steps and so do the phases after. Compare up to the first parting.
    part = np.flatnonzero(np.abs(r_f.omega_drives - r_s.omega_drives) > 2 * np.pi * 1.0)
    k = int(part[0]) if part.size else n
    if update == 0:
        assert k == n                 # a fixed drive cannot part
    assert np.all(np.abs(drift[:k]) <= bound[:k]), drift
    if offset == 0.0 and update == 0:
        assert np.all(np.abs(drift) <= 1e-10), drift      # on the anchor the words are the same
    if k == n:
        np.testing.assert_allclose(r_f.P0, r_s.P0, rtol=0., atol=2e-4)
        np.testing.assert_allclose(r_f.s_z, r_s.s_z, rtol=0., atol=2e-3)
    else:
        print(f"drives part at step {k} (slack {slack_mu}, offset {offset:.3f}): a posterior tie-break")
    assert r_s.t_end <= r_f.t_end   # the fastest loop ends after its 32-bit ADC restore


def test_the_adc_is_back_on_32_bits_after_the_loop(arms):
    mp, std, fst = arms
    ev_f, _ = h.run_train(mp, fst, _reads(9), slack_mu=39696, offset=0.0, update=1, fastest=FASTEST_UNIFORM)
    sampler = fst.integrator.sampler_ch.sampler_device
    cfg = [e for e in ev_f if e.target == ((sampler.bus_adc.channel << 8) | 1)]
    assert [((e.data >> 8) & 0xff) + 1 for e in cfg] == [16, 32]


def test_the_fastest_loop_really_chains(arms):
    """Every pulse after the first is switched on by the previous read's trace: written before
    that step's frequency word. The standard loop writes it after."""
    mp, std, fst = arms
    ev_s, r_s, ev_f, r_f = _pair(arms, _reads(4))
    tg = _targets(std)
    data_target = fst.raman._fw_data_target
    for ev, chained in ((ev_s, False), (ev_f, True)):
        on = [e for e in ev if e.target == tg["raman_sw"] and e.data == 1]
        assert len(on) == h.NARROW_GRID["N_pulses"]
        for e in on[1:]:
            # the last frequency-word write before this pulse in time
            words = [w for w in ev if w.target == data_target and w.t < e.t]
            if chained:
                assert e.seq < words[-1].seq
            else:
                assert e.seq > words[-1].seq


@pytest.mark.parametrize("slack_mu", SLACKS_MU)
def test_no_sequence_error_is_predicted(arms, slack_mu):
    ev_s, _, ev_f, _ = _pair(arms, _reads(7), slack_mu=slack_mu)
    m_s, m_f = h.lane_model(ev_s), h.lane_model(ev_f)
    assert m_s["n_sequence_errors"] == 0, m_s
    assert m_f["n_sequence_errors"] == 0, m_f
