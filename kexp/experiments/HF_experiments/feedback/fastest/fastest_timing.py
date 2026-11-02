"""Spacing, slack and push padding for the fastest feedback kernel (see README.md in this folder).

Host-side only. Every number is a no-atom bench measurement from 2026-11-01/02 (night folder
2026-10-30_17-54_night_summary, TIMING_LOG.md); nothing here has been run with atoms.

T is the median gap between pulse starts. The kernel's gap is dT = (slack + 24.216 us + t_pulse) & ~7,
so T moves with the drawn pulse time (1.9-3.8 us); the gap after the pulse is fixed.
"""

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
