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
