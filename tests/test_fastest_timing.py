"""fastest_timing reproduces the values the 2026-11-01/02 benches actually ran with."""
from kexp.experiments.HF_experiments.feedback.fastest import fastest_timing as ft


def test_slack_matches_the_runs():
    # bench slacks and their measured median gaps: 90958 -896 ns 26.16 us, 90945 -3896 23.15, 90950 -7896 19.2, 90953 -8896 18.1
    # the median gap minus slack is 27.00-27.10 us across these five runs (the median drawn pulse time differs),
    # so the inverse is good to that spread, 64 ns at worst here, not to one 8 ns step
    for slack, t in ((-896, 26.16), (-3896, 23.15), (-7896, 19.2), (-8896, 18.1), (5104, 32.19)):
        assert abs(ft.slack_mu_for(t) - slack) <= 64
        assert (ft.slack_mu_for(t) + 24216) % 8 == 0


def test_push_and_padding_match_the_runs():
    assert ft.push_doubles(21) == 720
    assert ft.push_doubles(21, margin_records=True) == 746
    assert ft.pad_doubles(21, margin_records=True) == 175      # bench_cg* files, 921 doubles, 7368 B
    assert ft.pad_doubles(21) == 201
    assert 8 * (ft.push_doubles(11) + ft.pad_doubles(11)) == 7368


def test_floors_reproduce_the_measured_rungs():
    for m, t in ft.FLOOR_US.items():
        assert abs(ft.t_floor_us(m) - t) <= 0.5
    assert abs(ft.t_reliable_us(21, deadline_guard=False) - 26.15) <= 0.05


def test_larger_grids_grow_and_flag_untested_padding():
    assert ft.t_floor_us(41) > ft.t_floor_us(21) + 13
    assert ft.pad_doubles(41) is None


def _params(m=21, **kw):
    from types import SimpleNamespace
    d = dict(feedback_grid_size=m, t_integrator_settle=2.e-6, t_integrator_gate_delay=0.7e-6,
             t_integrator_gate_extra=1.e-6, t_fifo_mu=18416, t_raman_set_pretrigger_mu=800, t_img_pulse=5.e-6)
    d.update(kw)
    return SimpleNamespace(**d)


def test_the_measured_table_entries_are_used():
    # 2026-11-05 slack ladders (lean): L + 3.0 us, on the 8 ns grid; the basis line names the ladder
    for m, L in ((21, -4.0), (31, 1.0), (51, 14.0)):
        assert ft.MEASURED_SLACK_FLOOR_US[(m, "lean")][0] == L
        s = ft.required_slack_mu(_params(m))
        assert (L + 3.0) * 1e3 <= s < (L + 3.0) * 1e3 + 8 and (s + 800 + 5000 + 18416) % 8 == 0
        assert "slack ladder" in ft.required_slack_basis(m, _params(m))
    # the lean entries never stand for the library posterior
    import pytest
    for m in (31, 51):
        with pytest.raises(ft.SlackUntested, match="library"):
            ft.required_slack_mu(_params(m, fastest_posterior=0))


def test_required_slack_is_the_rule_pass_plus_the_stated_terms(monkeypatch):
    # the bench path (no ladder entry for m 21 lean; the 2026-11-05 entry is removed here to test it)
    monkeypatch.delitem(ft.MEASURED_SLACK_FLOOR_US, (21, "lean"), raising=False)
    # m 21, the defaults (lean posterior, first gap +5 us: the bench's configuration): 90958's slack (-896 ns,
    # T 26.16) + deadline guard .5 us, nothing else (to the 64 ns the median-gap inverse is good to)
    s = ft.required_slack_mu(_params())
    assert abs(s - (-896 + 500)) <= 64
    assert s >= ft.slack_mu_for(ft.t_reliable_us(21))                  # rounded up, never down
    assert (s + 800 + 5000 + 18416) % 8 == 0                           # the fixed gap on the 8 ns grid
    # each setting off the bench's configuration costs its stated slack
    lib = ft.required_slack_mu(_params(fastest_posterior=0))
    assert 6100 <= lib - s < 6100 + 8                                  # the library posterior bound
    no_gap = ft.required_slack_mu(_params(fastest_first_gap_extra_mu=0))
    assert 5000 <= no_gap - s < 5000 + 8                               # the first-gap shortfall, on every gap
    part = ft.required_slack_mu(_params(fastest_first_gap_extra_mu=2000))
    assert 3000 <= part - s < 3000 + 8
    more = ft.required_slack_mu(_params(fastest_first_gap_extra_mu=8000))
    assert more == s                                                   # a longer stretch never lowers it
    assert "bench's configuration" in ft.required_slack_basis(21, _params())
    assert "library posterior bound" in ft.required_slack_basis(21, _params(fastest_posterior=0))


def test_required_slack_grows_with_the_grid_and_a_slower_read():
    assert ft.required_slack_mu(_params(5)) < ft.required_slack_mu(_params(11)) < ft.required_slack_mu(_params(21))
    base = ft.required_slack_mu(_params())
    assert ft.required_slack_mu(_params(t_integrator_settle=4.e-6)) - base >= 2000
    assert ft.required_slack_mu(_params(t_fifo_mu=16416)) - base >= 2000
    # a faster read keeps the measured slack (nothing measured below the bench read)
    assert abs(ft.required_slack_mu(_params(t_integrator_settle=1.e-6)) - base) <= 8


def test_a_grid_above_21_needs_a_slack_test_first(monkeypatch):
    import pytest
    with pytest.raises(ft.SlackUntested, match="Slack test"):
        ft.required_slack_mu(_params(41))                   # no ladder at m 41 (m 31/51 have 2026-11-05 entries)
    monkeypatch.delitem(ft.MEASURED_SLACK_FLOOR_US, (31, "lean"), raising=False)
    # ladder start: the bench estimate for the run's configuration, rounded up to a whole us
    assert ft.ladder_start_us(_params(31), 31) == 7.0                          # lean, first gap +5 us
    assert ft.ladder_start_us(_params(31, fastest_posterior=0), 31) == 16.0    # + 6.1 x 31 / 21 us
    # a ladder entry is used as floor + 3.0 us, for its grid size and posterior only
    monkeypatch.setitem(ft.MEASURED_SLACK_FLOOR_US, (31, "lean"), (15.0, "test", 5000))
    s = ft.required_slack_mu(_params(31))
    assert 18000 <= s < 18008 and (s + 800 + 5000 + 18416) % 8 == 0
    assert "slack ladder" in ft.required_slack_basis(31, _params(31))
    # less first-gap stretch than the ladder ran with: the shortfall on every gap
    s0 = ft.required_slack_mu(_params(31, fastest_first_gap_extra_mu=0))
    assert 23000 <= s0 < 23008
    # a floor measured lean does not stand for the library posterior
    with pytest.raises(ft.SlackUntested, match="library"):
        ft.required_slack_mu(_params(31, fastest_posterior=0))
    monkeypatch.setitem(ft.MEASURED_SLACK_FLOOR_US, (21, "lean"), (4.0, "test", 5000))
    assert 7000 <= ft.required_slack_mu(_params(21)) < 7008
