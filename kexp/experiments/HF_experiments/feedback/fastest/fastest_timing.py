"""Spacing, slack and push padding for the fastest feedback kernel (see README.md in this folder).

Host-side only. Every number is a no-atom bench measurement from 2026-11-01/02 (night folder
2026-10-30_17-54_night_summary, TIMING_LOG.md); nothing here has been run with atoms.

T is the median gap between pulse starts. The kernel's gap is dT = (slack + 24.216 us + t_pulse) & ~7,
so T moves with the drawn pulse time (1.9-3.8 us); the gap after the pulse is fixed.

required_slack_mu(p) is the slack FeedbackExpt's default loop picks (p.fastest_slack_auto = 1, the default),
for the run's posterior (p.fastest_posterior) and first-gap stretch (p.fastest_first_gap_extra_mu).
"""
import numpy as np

# compute_t_between_pulses_mu terms besides slack and the pulse: pretrigger .8 + imaging 5 + t_fifo 18.416 us
T_FIXED_US = 24.216
# measured: median gap = slack + 27.06 us, 27.00-27.10 across 90906, 90945, 90950, 90953, 90958 (median drawn pulse)
T_MEDIAN_OFFSET_US = 27.06

# Lowest clean spacing, every cut, no stamps, 63 shots per rung, first gap + 5 us:
# m 21: 23.15 us clean (90945), 22 us underflow (90946); m 11: 19.2 clean (90950), 18 underflow;
# m 5: 18.1 clean (90953), 17 underflow at shot 6.
FLOOR_US = {21: 23.15, 11: 19.2, 5: 18.1}
# Below about m 11 the read return, not the CPU, sets the floor.
READ_LIMIT_US = 18.1
# Between m 11 and 21 the floor moves .40 us a point (bracketed at 1 us steps: +/- about .1).
SLOPE_US_PER_POINT = 0.40
# Above m 21: untested. The stamped benches put the CPU at .68 us a point (make_c1w, 90801-90823); use that,
# the larger of the two, so the estimate errs long.
SLOPE_ABOVE_21_US_PER_POINT = 0.68
# Reliable = the bench rule (H0: no underflow, both core logs clean, min margin >= 5 us, >= 10,000 steps):
# passed at 26.16 us, m 21 (90958, min margin 5.1 us, 10,710 steps), i.e. floor + 3.0 us.
RELIABLE_OVER_FLOOR_US = 3.0
# The deadline check costs about .5 us a step (90987 vs 90989); the stage/write counters cost nothing measurable.
DEADLINE_GUARD_US = 0.5


def t_floor_us(m):
    """Lowest spacing expected to run clean, in us, for a grid of m points (no stamps)."""
    if m > 21:
        return FLOOR_US[21] + SLOPE_ABOVE_21_US_PER_POINT * (m - 21)
    return max(READ_LIMIT_US, FLOOR_US[21] - SLOPE_US_PER_POINT * (21 - m))


def t_reliable_us(m, deadline_guard=True):
    """Spacing that passed (m 21) or is expected to pass (other m) the bench rule, in us."""
    return t_floor_us(m) + RELIABLE_OVER_FLOOR_US + (DEADLINE_GUARD_US if deadline_guard else 0.)


def slack_mu_for(t_us):
    """t_calculation_slack_compensation_mu (ns) for a median gap t_us, aligned so the chained trace's
    fixed gap S = slack + 24216 ns is a multiple of 8 ns (the kernel asserts it)."""
    ns = int(round((t_us - T_MEDIAN_OFFSET_US) * 1e3))
    return ns - (ns + int(round(T_FIXED_US * 1e3))) % 8


# ---- the slack FeedbackExpt's default loop (fastest_loop.py) picks: required_slack_mu ------------------
#
# The rungs above ran the bench kernel. The default loop runs as the bench did when two settings are at their
# defaults (2026-11-05); each one moved off its default costs slack:
#
# 1. The first-gap stretch, p.fastest_first_gap_extra_mu (default 5000 ns). Every rung ran with the first gap
#    (i = 0 -> 1) 5 us longer than the rest and step 0 not chained (README). The default loop does the same.
#    A run with less stretch needs the shortfall on every gap (the loop's gaps are otherwise uniform).
FIRST_GAP_EXTRA_US = 5.0
# 2. The posterior numerics, p.fastest_posterior (default 1, lean: LeanPosterior, the bench's numerics).
#    With 0, the library posterior (OverlapPosterior): near the floor the step waits on the read, so the floor
#    is the read return plus the work after it (TIMING_LOG 11-01 19:49); the work after the read is
#    weigh_hypotheses. Its whole cost, stamped at m 21 on the overlap loop with the library halves, is 6.1 us
#    (90809, stamps included). The bench's post-read work is >= 0, so adding the whole 6.1 us bounds the
#    library posterior's floor from above. For m > 21 the 6.1 us is scaled by m / 21.
#    Still not measured on the default loop itself, with either posterior: its first runs are the check
#    (deadline guard on), and the slack ladder (README.md "Slack test") replaces the estimate.
LIBRARY_WEIGH_US_M21 = 6.1
POSTERIOR_NAMES = {0: "library", 1: "lean"}
# The read settings the floors were measured with (ExptParamsFeedback defaults since 2026-11-04). The slack
# absorbs a longer read: a longer settle or gate, or a shorter FIFO term, adds its difference. The imaging
# pulse and the Raman pretrigger cancel (both sit inside the gap the slack sets).
BENCH_READ_S = {"t_integrator_settle": 2.0e-6, "t_integrator_gate_delay": 0.7e-6,
                "t_integrator_gate_extra": 1.0e-6}
BENCH_T_FIFO_MU = 18416


def library_weigh_us(m):
    """Upper bound on the library posterior's post-read time over the bench's, in us (see above)."""
    return LIBRARY_WEIGH_US_M21 * max(1.0, m / 21.)


def read_extra_mu(p):
    """ns the run's read takes beyond the bench's (never negative: a faster read keeps the measured slack)."""
    extra = 0.
    for key, bench in BENCH_READ_S.items():
        extra += max(0., float(getattr(p, key)) - bench) * 1.e9
    extra += max(0, BENCH_T_FIFO_MU - int(p.t_fifo_mu))
    return int(np.ceil(extra))


def loop_config(p):
    """(posterior, first-gap stretch in ns) the run's fastest loop uses with the measured required slack:
    p.fastest_posterior (1 lean, 0 library; default 1) and p.fastest_first_gap_extra_mu (default -1, auto:
    the bench's 5000 ns whenever the loop takes this slack)."""
    posterior = int(np.ravel(getattr(p, "fastest_posterior", 1))[0])
    extra = int(np.ravel(getattr(p, "fastest_first_gap_extra_mu", -1))[0])
    if extra < 0:
        extra = int(FIRST_GAP_EXTRA_US * 1.e3)
    return posterior, extra


def config_pad_mu(m, posterior, extra_mu, reference_extra_mu=int(FIRST_GAP_EXTRA_US * 1.e3),
                  reference_posterior=1):
    """ns of slack a run needs beyond a floor measured at (reference_posterior, reference_extra_mu): the
    first-gap shortfall, and the library posterior bound when the floor was measured lean."""
    pad = max(0, int(reference_extra_mu) - int(extra_mu))
    if posterior == 0 and reference_posterior == 1:
        pad += int(round(library_weigh_us(m) * 1.e3))
    return pad


# Slack floors measured on the default loop itself with the slack ladder (README.md "Slack test"), keyed by
# (grid size m, posterior name): (lowest clean slack in us, "ladder runs, confirmation run, date",
# fastest_first_gap_extra_mu the ladder ran with, ns). An entry replaces the bench-derived estimate for that
# m and posterior: required slack = floor + RELIABLE_OVER_FLOOR_US + any first-gap shortfall against the
# ladder's + any longer read. A floor measured with one posterior does not stand for the other.
# Grids above 21 have no bench measurement at all, so the default loop refuses them until they have an entry.
# Entries of 2026-11-05/06 (organizer night; physicist-approved; both core logs read 00:11, no warning or error in
# the ladder windows: master from 20:30, satellite from 21:37 -- B0 and the m 21 ladder rungs predate the satellite's
# ring, its 100-shot confirmation does not). Common to all three: LEAN posterior only (the library posterior needs
# more: library m 51 is clean only down to 17 us in 20 shots, so this table's m 51 entry + 3.0 us would leave it no
# margin; library m 21 clean only to -2 us), 11 pulses, adaptive drive, first-gap stretch 5000 ns, APD contrast about
# 10-16 mV. The value is L, the lowest rung clean in a 100-shot confirmation, not the floor (floor = L - 0.5 +/- 0.29
# us). The +3.0 us margin (RELIABLE_OVER_FLOOR_US) was measured only at m 21 (bench 23.15 -> 26.16 us); it is
# untested at m 31 and m 51. Lean = library numerics (replay check R4) verified at m 21/31/51, N 11, adaptive only.
# m 51: 13 us failed at shot 12 of 100 (92672, about 1 in 12 shots); 14 us clean in 100 bounds the failure rate at
# about 3 % (95 %), not zero; the default T there (about 44.1 us) rests on the +3.0 us margin alone.
MEASURED_SLACK_FLOOR_US = {
    (21, "lean"): (-4.0, "92620-92626 ladder, 92630 confirmation, 2026-11-05", 5000),
    (31, "lean"): (1.0, "92644-92653 ladder, 92655 confirmation, 2026-11-05", 5000),
    (51, "lean"): (14.0, "92656-92669 ladder, 92672 failed at 13 us, 92674 confirmation at 14 us, 2026-11-05", 5000),
}
# Largest grid the bench measured (floors at m 5, 11, 21); above it the slack must be measured first.
LARGEST_BENCH_GRID = 21


class SlackUntested(ValueError):
    """The fastest loop has no measured slack for this grid size."""


def ladder_start_us(p, m):
    """First rung of a slack ladder for grid size m, in us: the bench-derived estimate for the run's posterior
    and first-gap stretch (for m > 21 the bench floor extrapolated at .68 us a point), + 3.5 us, rounded up to
    a whole us. A starting point only: the ladder decides."""
    posterior, extra = loop_config(p)
    ns = slack_mu_for(t_reliable_us(m, deadline_guard=True))
    ns += config_pad_mu(m, posterior, extra) + read_extra_mu(p)
    return float(np.ceil(ns / 1.e3)) + 0.0     # + 0.0: no "-0.0" in a rung file


def required_slack_mu(p, m=None):
    """t_calculation_slack_compensation_mu (ns) for the default loop.

    (m, posterior) with a slack-ladder entry (MEASURED_SLACK_FLOOR_US): the measured floor + 3.0 us + any
    first-gap shortfall against the ladder's + any longer read.
    m <= 21 without one: the slack that passed the bench rule (t_reliable_us, deadline guard on) + what the
    run's configuration lacks against the bench's (config_pad_mu: nothing at the defaults, lean posterior and
    5 us first-gap stretch) + any longer read.
    m > 21 without one: SlackUntested (run the slack ladder first, README.md "Slack test").
    Rounded up so the loop's fixed gap (slack + pretrigger + imaging pulse + FIFO) lands on the 8 ns grid."""
    if m is None:
        m = int(p.feedback_grid_size)
    posterior, extra = loop_config(p)
    key = (m, POSTERIOR_NAMES.get(posterior, str(posterior)))
    if key in MEASURED_SLACK_FLOOR_US:
        floor, _, ladder_extra = MEASURED_SLACK_FLOOR_US[key]
        ns = int(round((floor + RELIABLE_OVER_FLOOR_US) * 1.e3))
        ns += max(0, int(ladder_extra) - extra)
    elif m > LARGEST_BENCH_GRID:
        have = sorted(MEASURED_SLACK_FLOOR_US)
        raise SlackUntested(
            f"fastest loop: grid size {m} with the {key[1]} posterior has no measured slack (measured: "
            f"m <= {LARGEST_BENCH_GRID} on the bench" + (f", ladders {have}" if have else "")
            + "). Run the slack ladder first (kexp/experiments/HF_experiments/feedback/fastest/README.md, "
              "'Slack test') and enter the floor in fastest_timing.MEASURED_SLACK_FLOOR_US; or set "
              "t_calculation_slack_compensation_mu in the experiment (a ladder rung does).")
    else:
        ns = slack_mu_for(t_reliable_us(m, deadline_guard=True))
        ns += config_pad_mu(m, posterior, extra)
    ns += read_extra_mu(p)
    fixed = (int(p.t_raman_set_pretrigger_mu) + int(np.int64(float(p.t_img_pulse) * 1.e9))
             + int(p.t_fifo_mu))
    return ns + (-(ns + fixed)) % 8


def required_slack_basis(m, p=None):
    """One line on where required_slack_mu's number comes from, for the run's terminal."""
    posterior, extra = loop_config(p) if p is not None else (1, int(FIRST_GAP_EXTRA_US * 1.e3))
    name = POSTERIOR_NAMES.get(posterior, str(posterior))
    key = (m, name)
    if key in MEASURED_SLACK_FLOOR_US:
        floor, runs, ladder_extra = MEASURED_SLACK_FLOOR_US[key]
        short = max(0, int(ladder_extra) - extra)
        return (f"slack ladder on the default loop at m {m}, {name} posterior: floor {floor:.1f} us ({runs}) "
                f"+ {RELIABLE_OVER_FLOOR_US:.1f} us"
                + (f" + {short / 1.e3:.3f} us first-gap shortfall" if short else "")
                + ", deadline guard on")
    if m == 21:
        where = "rule pass at m 21 (90958)"
    elif m in FLOOR_US:
        where = f"floor measured at m {m} (63 shots, no rule pass) + the m 21 margin"
    elif m < 21:
        where = "floor interpolated between the measured m 5/11/21 + the m 21 margin"
    else:
        where = f"m {m} extrapolated above m 21 (UNTESTED)"
    pads = []
    short = max(0, int(FIRST_GAP_EXTRA_US * 1.e3) - extra)
    if short:
        pads.append(f"+ {short / 1.e3:.3f} us first-gap shortfall "
                    f"(stretch {extra / 1.e3:.3f} of {FIRST_GAP_EXTRA_US:.1f} us)")
    if posterior == 0:
        pads.append(f"+ {library_weigh_us(m):.1f} us library posterior bound")
    cfg = f"{name} posterior, first gap +{extra / 1.e3:.3f} us"
    cfg += ("; " + ", ".join(pads)) if pads else " (the bench's configuration)"
    return f"{where}; {cfg}; deadline guard on"


def push_doubles(m, n_pulses=13, margin_records=False):
    """float64 values pushed per shot before padding (printed by the kernel's [batch] line).
    Measured 720 at m 21, N 13 (746 with the two margin records)."""
    return 2 * m * (n_pulses + 1) + 7 * n_pulses + 41 + (2 * n_pulses if margin_records else 0)


# Push sizes with no stalls in 105-210 shots (11-01 padding test); the stall lead is size % 1460 B under about 700 B.
CLEAN_PUSH_BYTES = (7368, 7576, 7896)


def pad_doubles(m, n_pulses=13, margin_records=False):
    """Padding container length that brings the push to the smallest tested clean size.
    None when the push is already larger than every tested size: then pick a size with
    (8 * doubles) % 1460 under about 700 B and test it before trusting it."""
    d = push_doubles(m, n_pulses, margin_records)
    for b in CLEAN_PUSH_BYTES:
        if 8 * d <= b:
            return b // 8 - d
    return None
