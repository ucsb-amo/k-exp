"""Bayesian posterior over Rabi-frequency hypotheses from a Raman/measurement
pulse train.

The live feedback stack (kexp.base.feedback.Feedback.generate_posterior) grids
over *transition frequency* hypotheses while holding the Rabi rate fixed. This
module does the inverse: it assumes the transition frequency is already correct
(drive on resonance) and grids over *Rabi frequency* hypotheses, running one
forward model per hypothesis and accumulating a measurement-noise-tolerant
posterior across the pulse train.

The physics per pulse cycle mirrors generate_posterior (kexp/base/feedback.py
lines 205-285) exactly:

  1. Raman rotation      -- Rodrigues rotation by -H*t_ideal about the axis
                            (Omega/H*cos(phi), Omega/H*sin(phi), delta/H)
  2. z rotation          -- from the imaging-pulse light shift,
                            alpha_z = delta*t_eff - omega_lightshift*t_img
  3. measurement         -- back-action attenuates s_x and s_y by
                            back_action_coherence; s_z is NEVER attenuated
  4. photon fraction     -- p1 = 0.5*(1+s_z) + (midpoint-0.5)*(1-s_z**2)
  5. likelihood          -- Gaussian in photon count with FIXED variance
                            std_n_photons_per_shot**2

Step 5 is the "measurement-noise-tolerant" part: the state-dependent binomial
shot-noise term n*p1*q is deliberately left out (it is commented out in
Feedback.generate_posterior, kexp/base/feedback.py), so a single fixed,
generously-sized sigma absorbs
unmodelled excess noise instead of the likelihood becoming razor-sharp wherever
the model happens to predict p1 near 0 or 1. A heavier-tailed Student-t option
is also available for outlier robustness.

Everything is vectorized over (shot, hypothesis); only the short pulse axis is a
Python loop.

RANDOMIZED PULSE TIMES
----------------------
The pulse train draws every pulse duration independently, per shot
(kexp.base.feedback.draw_t_raman_pulse_list), from the same window the live
feedback loop drives, so Omega is calibrated over the durations it will be used
at rather than at one fixed duration. It is close to statistically neutral --
simulated round trips show the posterior is unimodal and about equally wide
either way -- so treat it as matching operating conditions, not as a way to
sharpen the answer.

The consequence for this module is that t_ideal and t_eff are (n_shot, n_pulse)
throughout -- a shot axis, not just a pulse axis -- and that a cross-shot mean
at a fixed pulse index is meaningless, since shot 3's fourth pulse is not the
same rotation as shot 7's. RabiPosteriorResult.pulse_times_vary says which
regime a run is in; plot_traces switches on it and plot_parity is the
schedule-agnostic goodness-of-fit view. The posterior itself needs no special
case: it already runs the forward model per shot.

GOODNESS OF FIT -- READ THIS FIRST
----------------------------------
This estimator holds every APD and Bloch constant fixed and lets f_rabi be the
only free parameter. That makes it fast and sharp, and it makes it dangerous:
if the readout calibration does not describe the run, there is nothing else to
absorb the mismatch, so f_rabi absorbs it and the posterior reports a confident
wrong number rather than a bad fit.

That is not hypothetical. Run 76245 reported 65, 98 and 150 kHz for three
different grid windows against an independent Raman scan of 57.8-58.3 kHz.
Residuals sat at 7.8x the assumed sigma for EVERY hypothesis on the grid --
nothing on the f_rabi axis could fit, because the fault was not on that axis.

ROOT CAUSE, for the record: rabi_posterior_pulse_train declared
img_types.ABSORPTION. init_kernel(setup_slm=True) picks the SLM phase mask off
that flag (Base.setup_slm), so the run read the atoms out through a FLAT mask
instead of the phase-contrast dot that apd_voltage_vs_state_2 was calibrated
with. The weak APD readout is a dispersive measurement; taking it without the
dot inverts the state-dependent response. The stored v_apd_all_up/down were
then exactly backwards for that data, and f_rabi -- the only free parameter --
absorbed the mismatch. Fixed 2026-08-25 (both pulse-train experiments now
declare DISPERSIVE); runs before that need v_range_sign='data'.

Re-fitting run 76245 with RabiJointPosterior at v_range_sign='data' returns
57.4 +/- 2.1 kHz, agreeing with the Raman scan to under 1%, and is stable to
0.001 kHz across five different grid spans with no axis railing.

Two things conspire to make the failure silent:

  * sigma is taken as exact. expt_params_feedback.py has at times set
    std_n_photons_per_shot to the SMALLEST of the measured endpoint noises
    ("using down std"), which is the opposite of the generously-sized sigma the
    fixed-variance likelihood below assumes.
  * under randomized pulse durations, high-f hypotheses produce s_z that
    decorrelates pulse to pulse. A fine grid of them behaves like many
    independent guesses, so with under-stated sigma the MAP drifts to whichever
    grid boundary you picked. Simulations: at 2x excess noise the MAP moves
    57.6 -> 80 kHz, at 3x it reaches 191 kHz.

run() therefore compares the realized residual RMS at the MAP against the
assumed sigma and warns past GOF_EXCESS_NOISE_LIMIT. Read that line before you
quote a number. If it trips, do not widen the grid -- fix the calibration, or
use RabiJointPosterior.

SYSTEMATICS WARNING
-------------------
With the current calibration the answer is systematics-limited, not
statistics-limited. At N_repeats = 30 the posterior width is ~0.6 kHz, but a 5%
error in the light shift moves the MAP by ~1 kHz. The reason is that the
per-pulse azimuthal kick is large:

    alpha_z = -2*pi*frequency_lightshift*t_img_pulse
            = -2*pi*34.6 kHz*5 us = -1.09 rad = -62 deg

Each pulse's Raman rotation happens about a *fixed* equatorial axis, so the
azimuth the light shift leaves behind decides how much of the transverse vector
converts back into s_z on the next pulse. The light shift therefore propagates
into every subsequent measurement even though it never touches s_z directly.

Note that only the PRODUCT frequency_lightshift*t_img_pulse enters, so those two
constants are exactly degenerate -- a 5% error in either is the same systematic.
Use RabiPosterior.systematic_budget() to tabulate the whole budget against the
statistical width before quoting a number.
"""

import numpy as np
from dataclasses import dataclass, field

# The one place a pulse-time list is drawn, shared with the kernel so a
# simulated shot is drawn exactly the way a real one is.
from kexp.base.feedback import draw_t_raman_pulse_list

__all__ = [
    "RabiPosterior",
    "RabiPosteriorResult",
    "RabiJointPosterior",
    "RabiJointPosteriorResult",
    "RabiCalibration",
    "simulate_pulse_train_apd",
    "draw_t_raman_pulse_list",
    "DEFAULT_F_RABI_MIN",
    "DEFAULT_F_RABI_MAX",
    "DEFAULT_N_GRID",
    "DEFAULT_SYSTEMATIC_FRACTIONS",
    "DEFAULT_T_PULSE_MIN_FRAC_PI",
    "DEFAULT_T_PULSE_MAX_FRAC_PI",
    "GOF_EXCESS_NOISE_LIMIT",
    "JOINT_AXES",
    "MIDPOINT_HALF_RANGE",
]

# Hypothesis grid. Deliberately wide: a narrow window anchored to the current
# calibration hides exactly the failure this module is prone to (see
# GOODNESS OF FIT below), because a mis-calibrated run rails at whichever
# boundary you happen to pick and the answer then looks like a measurement.
DEFAULT_F_RABI_MIN = 10.e3
DEFAULT_F_RABI_MAX = 200.e3
DEFAULT_N_GRID = 381

# Programmed pulse time minus coherent rotation area (AOM/switch turn-on
# latency). Matches expt_params_feedback.py, where it is the parameter
# t_raman_pulse_offset and t_raman_pulse_ideal is derived from it.
DEFAULT_T_TURN_ON_DELAY = 127.e-9

# Randomized-pulse-time window, as a fraction of t_raman_pi_pulse. Tracks
# t_raman_pulse_min_frac_pi / t_raman_pulse_max_frac_pi in
# expt_params_feedback.py; used only by simulate_pulse_train_apd, since a real
# run carries its drawn times in data.t_raman_pulse.
#
# These drift. Run 76245 was taken at [1/3, 2/3] while the params file said
# [1/2, 1]; neither matched the [1/4, 3/4] that used to be hardcoded here. They
# are a fallback for synthetic data only -- never trust them to describe a real
# run, and prefer simulate_pulse_train_apd(..., t_raman_pulse=ad.data.t_raman_pulse).
DEFAULT_T_PULSE_MIN_FRAC_PI = 1.0 / 2.0
DEFAULT_T_PULSE_MAX_FRAC_PI = 1.0

# Realized-residual-RMS / assumed-sigma above which run() declares the fit
# untrustworthy. 1.0 is a perfect match; a well-calibrated run sits near it.
# Anything past this is a calibration failure being absorbed by f_rabi, not a
# noisy measurement -- see the goodness-of-fit block in RabiPosterior.run().
GOF_EXCESS_NOISE_LIMIT = 1.5

# Fractional 1-sigma uncertainties assumed for the systematic budget. These are
# NOT measured -- they are placeholders you should replace with the real
# uncertainty of each calibration before quoting an error bar. See
# RabiPosterior.systematic_budget.
DEFAULT_SYSTEMATIC_FRACTIONS = {
    "frequency_lightshift": 0.05,
    "t_img_pulse": 0.05,
    "back_action_coherence": 0.05,
    "t_turn_on_delay": 0.25,
    "feedback_measurement_midpoint_fraction": 0.05,
}


# ---------------------------------------------------------------------------
# calibration
# ---------------------------------------------------------------------------

@dataclass
class RabiCalibration:
    """The calibration constants the forward model needs.

    Field names deliberately match the ExptParams attribute names used by the
    kernel, so ad.p can be scraped directly and the analysis stays
    calibration-compatible with the live feedback stack.

    PROVENANCE
    ----------
    from_params() records where every constant came from in `sources`, one of:

        'params'    read straight off ad.p
        'implied'   derived from other params (only t_turn_on_delay)
        'override'  supplied by the caller as a keyword
        'fitted'    a RabiJointPosterior posterior mean, via fitted_calibration
        'default'   NOT in the run -- fell back to the class default below

    Check it whenever a number looks wrong. The defaults are deliberately close
    to current operating values, which makes a silent fallback look plausible;
    'default' in `sources` is the only way to tell one apart from a real
    calibration. provenance_summary() prints the whole table.
    """

    # Defaults track expt_params_feedback.py. They are a fallback for synthetic
    # data; a real run always overrides them via from_params(ad.p). Keep them in
    # sync anyway -- when they drift, the notebook's synthetic round trip
    # validates the code in a regime the experiment never operates in, which is
    # how the run-76245 failure stayed invisible (the old defaults assumed 20%
    # fractional photon noise where the real run assumed 4%).
    t_img_pulse: float = 5.e-6
    frequency_lightshift: float = 3.46e4
    back_action_coherence: float = 0.7563
    feedback_measurement_midpoint_fraction: float = 0.35368
    feedback_measurement_midpoint_remap_enabled: bool = True
    v_apd_all_up: float = -0.10896
    v_apd_all_down: float = -0.19398
    n_photons_per_shot: float = 789.25
    std_n_photons_per_shot: float = 65.196
    t_turn_on_delay: float = DEFAULT_T_TURN_ON_DELAY
    t_raman_pi_pulse: float = np.nan

    # {field name: 'params' | 'implied' | 'override' | 'default'}. Populated by
    # from_params; left empty by a direct constructor call, where every value is
    # by definition either a default or something the caller passed in.
    sources: dict = field(default_factory=dict, compare=False, repr=False)

    # Every numeric field, in the order provenance_summary reports them.
    CALIBRATION_FIELDS = (
        "t_img_pulse", "frequency_lightshift", "back_action_coherence",
        "feedback_measurement_midpoint_fraction",
        "feedback_measurement_midpoint_remap_enabled",
        "v_apd_all_up", "v_apd_all_down",
        "n_photons_per_shot", "std_n_photons_per_shot",
        "t_turn_on_delay", "t_raman_pi_pulse",
    )

    def defaulted_fields(self):
        """Fields that silently fell back to the class default, in field order."""
        return [f for f in self.CALIBRATION_FIELDS
                if self.sources.get(f) == "default"]

    def provenance_line(self):
        """One-line 'n/m from ad.p' summary, for result summaries."""
        if not self.sources:
            return "calibration src: constructed directly (no ad.p scrape)"
        n_total = len(self.CALIBRATION_FIELDS)
        n_params = sum(1 for f in self.CALIBRATION_FIELDS
                       if self.sources.get(f) in ("params", "implied"))
        line = f"calibration src: {n_params}/{n_total} from ad.p"
        n_over = sum(1 for f in self.CALIBRATION_FIELDS
                     if self.sources.get(f) == "override")
        if n_over:
            line += f", {n_over} overridden"
        missing = self.defaulted_fields()
        if missing:
            line += (f", {len(missing)} DEFAULTED "
                     f"({', '.join(missing)})")
        return line

    def provenance_summary(self):
        """Printable per-field table of value and origin."""
        rows = [self.provenance_line(), ""]
        width = max(len(f) for f in self.CALIBRATION_FIELDS)
        for f in self.CALIBRATION_FIELDS:
            src = self.sources.get(f, "default")
            flag = "  <-- not in run params" if src == "default" else ""
            rows.append(f"  {f:{width}s} = {getattr(self, f)!s:<12s} "
                        f"[{src}]{flag}")
        return "\n".join(rows)

    @property
    def v_range(self):
        # kexp/base/feedback.py:804
        return self.v_apd_all_up - self.v_apd_all_down

    @property
    def omega_z_lightshift(self):
        # kexp/base/feedback.py:435
        return 2.0 * np.pi * self.frequency_lightshift

    @property
    def f_rabi_calibration(self):
        """Rabi frequency implied by the stored pi-pulse time, Hz."""
        if not np.isfinite(self.t_raman_pi_pulse) or self.t_raman_pi_pulse <= 0:
            return np.nan
        return 1.0 / (2.0 * self.t_raman_pi_pulse)

    @classmethod
    def from_params(cls, p, **overrides):
        """Scrape an ExptParams (or ad.p) for whatever it has, defaults elsewhere.

        Records per-field provenance in the returned calibration's `sources`, and
        warns about any field the run did not carry -- a silent fallback to a
        default that happens to look like a plausible current value is exactly
        how a stale calibration goes unnoticed.
        """
        kwargs = {}
        sources = {}

        for f in ("t_img_pulse", "frequency_lightshift", "back_action_coherence",
                  "feedback_measurement_midpoint_fraction",
                  "feedback_measurement_midpoint_remap_enabled",
                  "v_apd_all_up", "v_apd_all_down",
                  "std_n_photons_per_shot", "t_raman_pi_pulse"):
            v = getattr(p, f, None)
            if v is not None:
                kwargs[f] = v
                sources[f] = "params"
            else:
                sources[f] = "default"

        # The kernel stores this as N_photons_per_shot after
        # _initialize_measurement_calibrations; the params file declares it
        # lowercase. Accept either.
        sources["n_photons_per_shot"] = "default"
        for name in ("n_photons_per_shot", "N_photons_per_shot"):
            v = getattr(p, name, None)
            if v is not None:
                kwargs["n_photons_per_shot"] = v
                sources["n_photons_per_shot"] = "params"
                break

        # Turn-on delay. An experiment may declare it outright; otherwise it is
        # implied, as the gap between the programmed and ideal pulse times.
        sources["t_turn_on_delay"] = "default"
        explicit = getattr(p, "t_raman_pulse_offset", None)
        if explicit is None:
            explicit = getattr(p, "t_raman_turn_on_delay", None)
        t_prog = getattr(p, "t_raman_pulse", None)
        t_ideal = getattr(p, "t_raman_pulse_ideal", None)
        if explicit is not None:
            kwargs["t_turn_on_delay"] = float(np.ravel(explicit)[0])
            sources["t_turn_on_delay"] = "params"
        elif t_prog is not None and t_ideal is not None:
            # The implied route reads element 0 of each, so it is only right
            # when the two line up. An experiment that SCANS t_raman_pulse
            # leaves the scalar t_raman_pulse_ideal behind and the difference
            # becomes meaningless -- such an experiment must declare
            # t_raman_pulse_offset (or t_raman_turn_on_delay) instead.
            prog_arr = np.ravel(np.asarray(t_prog, dtype=float))
            ideal_arr = np.ravel(np.asarray(t_ideal, dtype=float))
            if prog_arr.size > 1 and ideal_arr.size != prog_arr.size:
                print("[RabiCalibration] warning: t_raman_pulse looks scanned "
                      f"({prog_arr.size} values) but t_raman_pulse_ideal has "
                      f"{ideal_arr.size}; the implied turn-on delay would be "
                      f"wrong, so falling back to "
                      f"{DEFAULT_T_TURN_ON_DELAY*1e9:.0f} ns. Declare "
                      "t_raman_pulse_offset in the params to silence this.")
            elif np.isfinite(prog_arr[0]) and np.isfinite(ideal_arr[0]):
                kwargs["t_turn_on_delay"] = float(prog_arr[0] - ideal_arr[0])
                sources["t_turn_on_delay"] = "implied"

        kwargs.update(overrides)
        for k in overrides:
            sources[k] = "override"

        # Coerce so a stray numpy scalar or 0-d array cannot poison broadcasting.
        # A field scanned with xvar arrives as an array; float() would raise, so
        # take element 0 and say so rather than dying deep in the forward model.
        scanned = []
        for k, v in list(kwargs.items()):
            if k == "feedback_measurement_midpoint_remap_enabled":
                kwargs[k] = bool(np.ravel(np.asarray(v))[0])
                continue
            arr = np.ravel(np.asarray(v, dtype=float))
            if arr.size > 1:
                scanned.append(f"{k} ({arr.size} values)")
            kwargs[k] = float(arr[0])

        if scanned:
            print("[RabiCalibration] warning: these params are scanned, not "
                  f"scalar -- using element 0 of each: {', '.join(scanned)}. "
                  "The forward model holds the calibration fixed across the "
                  "whole run, so a scanned calibration constant is not "
                  "modelled.")

        missing = [f for f in cls.CALIBRATION_FIELDS
                   if sources.get(f) == "default"]
        if missing:
            print("[RabiCalibration] warning: not in the run's params, so "
                  f"falling back to module defaults: {', '.join(missing)}. "
                  "The defaults track the CURRENT expt_params_feedback.py, so "
                  "they may silently disagree with what this run was actually "
                  "taken at -- check RabiCalibration.provenance_summary().")

        cal = cls(**kwargs)
        cal.sources = sources
        return cal


# ---------------------------------------------------------------------------
# forward model
# ---------------------------------------------------------------------------

def expected_photon_fraction(s_z, midpoint_fraction, remap_enabled=True):
    """p1 as a function of the Bloch z component.

    Vectorized port of Feedback.expected_photon_fraction
    (kexp/base/feedback.py:74-86), including the nonlinear midpoint remap and
    the [0, 1] clip.
    """
    p1 = 0.5 * (1.0 + s_z)
    if remap_enabled:
        p1 = p1 + (midpoint_fraction - 0.5) * (1.0 - s_z * s_z)
    return np.clip(p1, 0.0, 1.0)


def spin_value_from_photon_fraction(photon_fraction, midpoint_fraction,
                                    remap_enabled=True):
    """Invert expected_photon_fraction.

    Vectorized port of Feedback.spin_value_from_photon_fraction
    (kexp/base/feedback.py:98-127) -- the quadratic inverse of the midpoint
    remap. Used only for plotting measured s_z; the posterior itself works in
    photon-count space and never needs this inverse.
    """
    p1 = np.clip(np.asarray(photon_fraction, dtype=float), 0.0, 1.0)
    delta = midpoint_fraction - 0.5
    if (not remap_enabled) or abs(delta) < 1.0e-15:
        return 2.0 * p1 - 1.0
    discriminant = np.clip(0.25 - 4.0 * delta * (p1 - midpoint_fraction), 0.0, None)
    return np.clip((0.5 - np.sqrt(discriminant)) / (2.0 * delta), -1.0, 1.0)


def apd_to_photon_count(v_apd, cal: RabiCalibration, round_counts=True):
    """Vectorized port of Feedback.convert_measurement (kexp/base/feedback.py:72)."""
    k = cal.n_photons_per_shot * (np.asarray(v_apd, dtype=float)
                                  - cal.v_apd_all_down) / cal.v_range
    return np.rint(k) if round_counts else k


def evolve_pulse_train(t_ideal, t_eff, f_rabi_grid, cal: RabiCalibration,
                       frequency_detuning_residual=0.0, phi=0.0,
                       s_initial=(0.0, 0.0, 1.0)):
    """Run the Bloch forward model for every hypothesis and every pulse.

    Args:
        t_ideal: (n_shot, n_pulse) coherent rotation area of each pulse, s.
        t_eff:   (n_shot, n_pulse) programmed duration of each pulse, s. Only
            matters when frequency_detuning_residual != 0.
        f_rabi_grid: (n_grid,) hypothesis grid, Hz.
        frequency_detuning_residual: drive minus resonance, Hz. Zero is the
            premise of the experiment; exposed so the assumption can be probed.
        phi: azimuth of the rotation axis, rad. Identically zero for a
            phase-continuous DDS held at a fixed frequency, which is what
            prep_raman(phase_mode=1) plus an unchanging drive gives us -- the
            drive axis is static in the frame rotating at the drive frequency.

    Returns:
        s_z_pre_measure: (n_shot, n_pulse, n_grid) the z component the APD
            actually sees on each pulse -- after that pulse's rotation, before
            the next pulse's back-action.
        state: (n_shot, n_pulse, n_grid, 3) the full Bloch vector after each
            complete cycle (rotation, z rotation, back-action).
    """
    t_ideal = np.atleast_2d(np.asarray(t_ideal, dtype=float))
    t_eff = np.atleast_2d(np.asarray(t_eff, dtype=float))
    f_grid = np.asarray(f_rabi_grid, dtype=float).ravel()

    n_shot, n_pulse = t_ideal.shape
    n_grid = f_grid.size

    Omega = 2.0 * np.pi * f_grid                                   # (n_grid,)
    delta = 2.0 * np.pi * float(frequency_detuning_residual)       # scalar

    norm_H = np.sqrt(Omega * Omega + delta * delta)                # (n_grid,)
    # Omega = 0 is a legitimate grid point (no rotation at all); guard the
    # reciprocal rather than letting it produce a nan axis.
    inv_H = np.where(norm_H > 0.0, 1.0 / np.where(norm_H > 0.0, norm_H, 1.0), 0.0)
    Omega_over_H = Omega * inv_H
    u_x = Omega_over_H * np.cos(phi)
    u_y = Omega_over_H * np.sin(phi)
    u_z = delta * inv_H

    C = cal.back_action_coherence

    s_x = np.full((n_shot, n_grid), float(s_initial[0]))
    s_y = np.full((n_shot, n_grid), float(s_initial[1]))
    s_z = np.full((n_shot, n_grid), float(s_initial[2]))

    s_z_pre_measure = np.empty((n_shot, n_pulse, n_grid), dtype=float)
    state = np.empty((n_shot, n_pulse, n_grid, 3), dtype=float)

    for i in range(n_pulse):
        # (1) Raman rotation. Sign matches sincos_lut_interp(-dt_ideal*norm_H).
        theta = -norm_H[None, :] * t_ideal[:, i][:, None]          # (n_shot, n_grid)
        c = np.cos(theta)
        s_ = np.sin(theta)
        one_minus_c = 1.0 - c

        dot = u_x * s_x + u_y * s_y + u_z * s_z
        cross_x = u_y * s_z - u_z * s_y
        cross_y = u_z * s_x - u_x * s_z
        cross_z = u_x * s_y - u_y * s_x

        h_x = s_x * c + cross_x * s_ + u_x * dot * one_minus_c
        h_y = s_y * c + cross_y * s_ + u_y * dot * one_minus_c
        h_z = s_z * c + cross_z * s_ + u_z * dot * one_minus_c

        # The APD sees the z component right here -- the z rotation below does
        # not touch z, and back-action never attenuates z.
        s_z_pre_measure[:, i, :] = h_z

        # (2) z rotation from the imaging light shift (plus free precession if a
        # residual detuning is being modelled).
        # Free precession in the frame rotating at the drive: the phase
        # accumulates at (omega_atom - omega_drive) = -delta, matching the
        # kernel, where the rotation's detuning is delta_omega = omega_raman -
        # omega while alpha_z is built from delta_omega0 = omega0 - omega_raman
        # (kexp/base/feedback.py:194,201,216) -- i.e. the opposite sign to the
        # one that sets u_z. Identically zero at delta = 0, which is the premise
        # of this experiment; it matters only for the detuning row of
        # systematic_budget() and for frequency_detuning_residual != 0.
        alpha_z = -delta * t_eff[:, i][:, None] - cal.omega_z_lightshift * cal.t_img_pulse
        cos_z = np.cos(alpha_z)
        sin_z = np.sin(alpha_z)
        n_x = cos_z * h_x + sin_z * h_y
        n_y = -sin_z * h_x + cos_z * h_y

        # (3) measurement back-action: transverse components only.
        s_x = C * n_x
        s_y = C * n_y
        s_z = h_z

        state[:, i, :, 0] = s_x
        state[:, i, :, 1] = s_y
        state[:, i, :, 2] = s_z

    return s_z_pre_measure, state


def simulate_pulse_train_apd(f_rabi_true, cal: RabiCalibration, n_shot=30,
                             n_pulse=10, t_raman_pulse=None, seed=0,
                             frequency_detuning_residual=0.0,
                             noise_scale=1.0,
                             randomize_pulse_times=True,
                             t_raman_pulse_min_frac_pi=DEFAULT_T_PULSE_MIN_FRAC_PI,
                             t_raman_pulse_max_frac_pi=DEFAULT_T_PULSE_MAX_FRAC_PI,
                             t_raman_pulse_seed=0):
    """Generate synthetic APD voltages from the forward model.

    Used by the notebook's round-trip test: simulate at a known f_rabi, run the
    posterior, confirm recovery. Noise is Gaussian in photon count at
    std_n_photons_per_shot, matching what the likelihood assumes.

    Args:
        t_raman_pulse: explicit durations -- scalar, (n_pulse,), or
            (n_shot, n_pulse). Overrides randomize_pulse_times, and a 2D value
            sets n_shot/n_pulse.
        randomize_pulse_times: draw each shot's durations the way the kernel
            does (independent uniform in [min_frac, max_frac] * t_pi, rounded to
            whole ns), which is what the experiment now runs. Set False for the
            old constant pi/2 train.
        t_raman_pulse_seed: seed for the per-shot draw; 0 falls back to `seed`.
            Each shot gets its own derived seed, so a simulated shot replays the
            same way a real one does.

    Returns:
        apd: (n_shot, n_pulse) integrator voltages.
        t_raman_pulse_rr: (n_shot, n_pulse) programmed pulse durations. Feed
            this straight back to RabiPosterior(t_raman_pulse=...).
    """
    t_pi = cal.t_raman_pi_pulse
    if not np.isfinite(t_pi) or t_pi <= 0:
        t_pi = 1.0 / (2.0 * f_rabi_true)

    if t_raman_pulse is not None:
        t_eff = np.asarray(t_raman_pulse, dtype=float)
        if t_eff.ndim == 0:
            t_eff = np.full((n_shot, n_pulse), float(t_eff))
        elif t_eff.ndim == 1:
            t_eff = np.tile(t_eff.reshape(1, -1), (n_shot, 1))
        else:
            t_eff = t_eff.reshape(-1, t_eff.shape[-1])
        n_shot, n_pulse = t_eff.shape
    elif randomize_pulse_times:
        shot_seeds = np.random.default_rng(
            int(t_raman_pulse_seed) or int(seed)).integers(1, 2 ** 31, size=n_shot)
        t_eff = np.stack([
            draw_t_raman_pulse_list(s, n_pulse, t_pi,
                                    t_raman_pulse_min_frac_pi,
                                    t_raman_pulse_max_frac_pi)
            for s in shot_seeds])
    else:
        # The pi/2 pulse the experiment used before randomization.
        t_eff = np.full((n_shot, n_pulse), t_pi / 2.0)

    t_ideal = t_eff - cal.t_turn_on_delay

    s_z, _ = evolve_pulse_train(
        t_ideal, t_eff, np.array([f_rabi_true]), cal,
        frequency_detuning_residual=frequency_detuning_residual)
    s_z = s_z[:, :, 0]                                             # (n_shot, n_pulse)

    p1 = expected_photon_fraction(
        s_z, cal.feedback_measurement_midpoint_fraction,
        cal.feedback_measurement_midpoint_remap_enabled)

    rng = np.random.default_rng(seed)
    k = cal.n_photons_per_shot * p1
    k = k + rng.normal(0.0, cal.std_n_photons_per_shot * noise_scale, size=k.shape)

    v_apd = cal.v_apd_all_down + k * cal.v_range / cal.n_photons_per_shot
    return v_apd, t_eff


# ---------------------------------------------------------------------------
# result
# ---------------------------------------------------------------------------

@dataclass
class RabiPosteriorResult:
    """Everything the posterior run produced.

    Shapes use n_shot = total shots (all scan/repeat axes flattened),
    n_pulse = pulses per shot, n_grid = hypothesis grid size.
    """

    f_rabi_grid: np.ndarray                 # (n_grid,) Hz
    posterior_joint: np.ndarray             # (n_grid,) all shots combined
    posterior_shot: np.ndarray              # (n_shot, n_grid) each shot alone
    posterior_vs_pulse: np.ndarray          # (n_shot, n_pulse, n_grid) sequential
    posterior_joint_vs_pulse: np.ndarray    # (n_pulse, n_grid) all shots, cumulative

    s_z_model: np.ndarray                   # (n_shot, n_pulse, n_grid)
    s_z_meas: np.ndarray                    # (n_shot, n_pulse) from the APD
    k_meas: np.ndarray                      # (n_shot, n_pulse) photon counts
    state: np.ndarray                       # (n_shot, n_pulse, n_grid, 3)

    # Pulse durations actually used, per shot -- randomized trains give every
    # shot its own row (see the module docstring).
    t_eff: np.ndarray                       # (n_shot, n_pulse) programmed, s
    t_ideal: np.ndarray                     # (n_shot, n_pulse) rotation area, s

    f_map: float
    f_mean: float
    f_std: float
    ci68: tuple
    ci95: tuple
    t_pi_map: float

    calibration: RabiCalibration = None
    metadata: dict = field(default_factory=dict)

    @property
    def pulse_times_vary(self):
        """True when the shots do not all share one pulse schedule.

        Cross-shot statistics at a fixed pulse index only mean something when
        this is False.
        """
        return bool(self.t_eff.shape[0] > 1
                    and not np.allclose(self.t_eff, self.t_eff[0:1, :]))

    @property
    def s_z_model_map(self):
        """(n_shot, n_pulse) model s_z at the MAP hypothesis."""
        j = int(np.argmax(self.posterior_joint))
        return self.s_z_model[:, :, j]

    def summary(self):
        cal_f = self.calibration.f_rabi_calibration if self.calibration else np.nan
        lines = [
            f"run {self.metadata.get('run_id', '?')} | "
            f"{self.s_z_meas.shape[0]} shots x {self.s_z_meas.shape[1]} pulses",
            f"  grid          : {self.f_rabi_grid[0]/1e3:.3f} - "
            f"{self.f_rabi_grid[-1]/1e3:.3f} kHz, {self.f_rabi_grid.size} points "
            f"({self.metadata.get('grid_step_hz', np.nan)/1e3:.4f} kHz step)",
            f"  likelihood    : {self.metadata.get('likelihood', '?')}",
            f"  fit quality   : residual RMS "
            f"{self.metadata.get('resid_rms_photons', float('nan')):.1f} photons "
            f"vs assumed sigma "
            f"{self.metadata.get('sigma_assumed_photons', float('nan')):.1f} "
            f"({self.metadata.get('excess_noise_factor', float('nan')):.2f}x)",
            f"  pulse times   : {self.t_eff.min()*1e6:.4f} - "
            f"{self.t_eff.max()*1e6:.4f} us "
            f"({'randomized per shot' if self.pulse_times_vary else 'constant'})",
            f"  f_rabi (MAP)  : {self.f_map/1e3:.4f} kHz",
            f"  f_rabi (mean) : {self.f_mean/1e3:.4f} +/- {self.f_std/1e3:.4f} kHz",
            f"  68% CI        : [{self.ci68[0]/1e3:.4f}, {self.ci68[1]/1e3:.4f}] kHz",
            f"  95% CI        : [{self.ci95[0]/1e3:.4f}, {self.ci95[1]/1e3:.4f}] kHz",
            f"  t_pi (MAP)    : {self.t_pi_map*1e6:.5f} us",
            f"  calibration   : f_rabi = {cal_f/1e3:.4f} kHz "
            f"(t_raman_pi_pulse = {self.calibration.t_raman_pi_pulse*1e6:.5f} us)"
            if self.calibration else "",
            f"  {self.calibration.provenance_line()}"
            if self.calibration else "",
        ]
        if self.metadata.get("gof_warning"):
            lines.append("  !! " + self.metadata["gof_warning"])
        if self.metadata.get("boundary_warning"):
            lines.append("  !! " + self.metadata["boundary_warning"])
        if self.calibration and self.calibration.defaulted_fields():
            lines.append(
                "  !! some calibration constants are NOT from this run's params "
                "(see 'calibration src' above). They fell back to the current "
                "module defaults, which may not be what this run was taken at.")
        return "\n".join(x for x in lines if x)

    def print(self):
        print(self.summary())


# ---------------------------------------------------------------------------
# posterior
# ---------------------------------------------------------------------------

class RabiPosterior:
    """Bayesian posterior over Rabi frequency from a Raman/measurement pulse train.

    Typical use:

        from kexp import atomdata
        from kexp.analysis import RabiPosterior

        ad = atomdata(76200)
        rp = RabiPosterior(ad)
        res = rp.run()
        res.print()
        rp.plot_posterior()
    """

    def __init__(self, ad=None, *,
                 f_rabi_min=DEFAULT_F_RABI_MIN,
                 f_rabi_max=DEFAULT_F_RABI_MAX,
                 n_grid=DEFAULT_N_GRID,
                 likelihood="gaussian",
                 student_t_dof=4.0,
                 prior=None,
                 frequency_detuning_residual=0.0,
                 phi=0.0,
                 round_photon_counts=True,
                 apd=None, t_raman_pulse=None, calibration=None,
                 **calibration_overrides):
        """
        Args:
            ad: atomdata from a rabi_posterior_pulse_train run. Optional if apd
                and calibration are supplied directly (synthetic data).
            f_rabi_min, f_rabi_max, n_grid: hypothesis grid, Hz / count.
            likelihood: "gaussian" (default; bit-for-bit the kernel's
                include_photon_noise=1 path, fixed sigma) or "student_t"
                (same location and scale, heavy tails).
            student_t_dof: degrees of freedom for the Student-t likelihood.
                Lower is more outlier-tolerant.
            prior: (n_grid,) prior over the grid. Defaults to uniform.
            frequency_detuning_residual: drive minus resonance, Hz. Zero is the
                premise of the experiment.
            apd: (n_shot, n_pulse) integrator voltages, if not taking them
                from ad.
            t_raman_pulse: programmed pulse durations -- scalar, (n_pulse,), or
                (n_shot, n_pulse) for a randomized train. Defaults to
                ad.data.t_raman_pulse, falling back to the scalar
                ad.p.t_raman_pulse for runs that predate the per-shot save.
            calibration_overrides: any RabiCalibration field, e.g.
                back_action_coherence=0.9.
        """
        if likelihood not in ("gaussian", "student_t"):
            raise ValueError(
                f"likelihood must be 'gaussian' or 'student_t', got {likelihood!r}")
        if n_grid < 1:
            raise ValueError(f"n_grid must be >= 1, got {n_grid}")

        self.ad = ad
        self.likelihood = likelihood
        self.student_t_dof = float(student_t_dof)
        self.frequency_detuning_residual = float(frequency_detuning_residual)
        self.phi = float(phi)
        self.round_photon_counts = bool(round_photon_counts)

        if calibration is not None:
            self.cal = calibration
            for k, v in calibration_overrides.items():
                setattr(self.cal, k, v)
        elif ad is not None:
            self.cal = RabiCalibration.from_params(ad.p, **calibration_overrides)
        else:
            self.cal = RabiCalibration(**calibration_overrides)

        self.apd, self.t_eff = self._load_data(ad, apd, t_raman_pulse)
        self.n_shot, self.n_pulse = self.apd.shape

        if n_grid == 1:
            self.f_rabi_grid = np.array([0.5 * (f_rabi_min + f_rabi_max)])
        else:
            self.f_rabi_grid = np.linspace(f_rabi_min, f_rabi_max, int(n_grid))

        if prior is None:
            self.prior = np.full(self.f_rabi_grid.size, 1.0 / self.f_rabi_grid.size)
        else:
            prior = np.asarray(prior, dtype=float).ravel()
            if prior.size != self.f_rabi_grid.size:
                raise ValueError(
                    f"prior has {prior.size} points but the grid has "
                    f"{self.f_rabi_grid.size}")
            if np.any(prior < 0) or not np.any(prior > 0):
                raise ValueError("prior must be non-negative with some positive mass")
            self.prior = prior / prior.sum()

        self.result = None

    # -- data ---------------------------------------------------------------

    def _load_data(self, ad, apd, t_raman_pulse):
        """Flatten all scan/repeat axes into one shot axis.

        Containers load as (*xvardims, n_pulse); the exact leading layout
        depends on the scan and on DataContainer.squeeze_axes, so collapsing
        everything but the trailing pulse axis is the robust move.
        """
        if apd is None:
            if ad is None:
                raise ValueError("provide either ad or apd")
            if not hasattr(ad.data, "apd"):
                raise AttributeError(
                    "ad.data has no 'apd' container -- is this a "
                    "rabi_posterior_pulse_train run?")
            apd = ad.data.apd

        apd = np.asarray(apd, dtype=float)
        if apd.ndim == 1:
            apd = apd[None, :]
        apd = apd.reshape(-1, apd.shape[-1])

        n_pulse = apd.shape[-1]
        n_declared = getattr(self.cal, "_n_pulses_declared", None)
        if ad is not None:
            n_declared = getattr(ad.p, "N_pulses", None)
        if n_declared is not None and int(n_declared) != n_pulse:
            print(f"[RabiPosterior] warning: ad.p.N_pulses = {int(n_declared)} but "
                  f"data.apd has {n_pulse} columns; using {n_pulse}.")

        # Programmed pulse durations, per shot and pulse. A randomized run saves
        # one drawn row per shot in data.t_raman_pulse; older runs only carry
        # the scalar param, and older still lack the container entirely.
        self.t_raman_pulse_source = "t_raman_pulse argument"
        if t_raman_pulse is None and ad is not None:
            t_raman_pulse = getattr(ad.data, "t_raman_pulse", None)
            self.t_raman_pulse_source = "ad.data.t_raman_pulse"
            if t_raman_pulse is not None and not _is_usable_pulse_times(t_raman_pulse):
                # Container present but never written (all zeros): a run from
                # before the per-shot save.
                print("[RabiPosterior] warning: ad.data.t_raman_pulse holds no "
                      "usable durations; falling back to ad.p.t_raman_pulse.")
                t_raman_pulse = None
        if t_raman_pulse is None and ad is not None:
            t_raman_pulse = getattr(ad.p, "t_raman_pulse", None)
            self.t_raman_pulse_source = "ad.p.t_raman_pulse"
        if t_raman_pulse is None:
            raise ValueError(
                "no pulse durations found -- pass t_raman_pulse explicitly")

        n_shot = apd.shape[0]
        t_eff = np.asarray(t_raman_pulse, dtype=float)
        if t_eff.ndim == 0:
            t_eff = np.full(apd.shape, float(t_eff))
        elif t_eff.ndim == 1 and t_eff.size == n_pulse:
            # One list shared by every shot: a constant train, or a run whose
            # per-shot container got squeezed down to a single row.
            t_eff = np.tile(t_eff, (n_shot, 1))
        else:
            # Per-shot lists. The container carries the same leading
            # scan/repeat axes as apd, so the same flatten lines the two up
            # shot for shot.
            t_eff = t_eff.reshape(-1, t_eff.shape[-1])
            if t_eff.shape[-1] != n_pulse:
                raise ValueError(
                    f"t_raman_pulse has {t_eff.shape[-1]} pulses per shot but "
                    f"apd has {n_pulse}")
            if t_eff.shape[0] == 1 and n_shot > 1:
                t_eff = np.tile(t_eff, (n_shot, 1))
            elif t_eff.shape[0] != n_shot:
                raise ValueError(
                    f"t_raman_pulse has {t_eff.shape[0]} shots but apd has "
                    f"{n_shot}")

        if not _is_usable_pulse_times(t_eff):
            raise ValueError(
                f"t_raman_pulse (from {self.t_raman_pulse_source}) contains "
                "non-positive or non-finite values")

        return apd, t_eff

    @property
    def pulse_times_vary(self):
        """True when the shots do not all share one pulse schedule."""
        return bool(self.t_eff.shape[0] > 1
                    and not np.allclose(self.t_eff, self.t_eff[0:1, :]))

    # -- likelihood ---------------------------------------------------------

    def _log_likelihood(self, k_meas, p1):
        """Log-likelihood of the measured photon count under each hypothesis.

        k_meas: (n_shot, 1) ; p1: (n_shot, n_grid) -> (n_shot, n_grid)

        Constant normalizers are dropped -- they do not depend on the hypothesis
        and cancel when the posterior is normalized.
        """
        sigma = self.cal.std_n_photons_per_shot
        resid = k_meas - self.cal.n_photons_per_shot * p1
        z_sq = (resid * resid) / (sigma * sigma)
        if self.likelihood == "gaussian":
            # Fixed sigma: the binomial n*p1*q term stays out, exactly as in
            # Feedback.generate_posterior (kexp/base/feedback.py). This is what
            # makes the posterior tolerant of unmodelled excess measurement noise.
            return -0.5 * z_sq
        dof = self.student_t_dof
        return -0.5 * (dof + 1.0) * np.log1p(z_sq / dof)

    # -- run ----------------------------------------------------------------

    def run(self):
        """Run the forward model over the grid and accumulate the posterior."""
        cal = self.cal
        t_ideal = self.t_eff - cal.t_turn_on_delay
        self.t_ideal = t_ideal
        if np.any(t_ideal <= 0):
            raise ValueError(
                f"t_turn_on_delay ({cal.t_turn_on_delay*1e9:.1f} ns) is >= the "
                f"shortest pulse ({self.t_eff.min()*1e9:.1f} ns)")

        s_z_model, state = evolve_pulse_train(
            t_ideal, self.t_eff, self.f_rabi_grid, cal,
            frequency_detuning_residual=self.frequency_detuning_residual,
            phi=self.phi)

        k_meas = apd_to_photon_count(self.apd, cal, self.round_photon_counts)

        n_shot, n_pulse = self.apd.shape
        n_grid = self.f_rabi_grid.size

        log_prior = np.log(np.where(self.prior > 0, self.prior, np.finfo(float).tiny))

        log_post = np.tile(log_prior, (n_shot, 1))          # (n_shot, n_grid)
        posterior_vs_pulse = np.empty((n_shot, n_pulse, n_grid))
        posterior_joint_vs_pulse = np.empty((n_pulse, n_grid))

        for i in range(n_pulse):
            p1 = expected_photon_fraction(
                s_z_model[:, i, :],
                cal.feedback_measurement_midpoint_fraction,
                cal.feedback_measurement_midpoint_remap_enabled)
            log_post = log_post + self._log_likelihood(k_meas[:, i][:, None], p1)
            posterior_vs_pulse[:, i, :] = _normalize_log(log_post, axis=-1)
            # Shots are independent given the hypothesis, so the joint is the
            # product of per-shot likelihoods -- but the prior must only be
            # counted once, not once per shot.
            posterior_joint_vs_pulse[i, :] = _normalize_log(
                log_post.sum(axis=0) - (n_shot - 1) * log_prior)

        posterior_shot = _normalize_log(log_post, axis=-1)
        posterior_joint = posterior_joint_vs_pulse[-1, :]

        f = self.f_rabi_grid
        f_map = float(f[int(np.argmax(posterior_joint))])
        f_mean = float(np.sum(posterior_joint * f))
        var = float(np.sum(posterior_joint * f * f) - f_mean * f_mean)
        f_std = float(np.sqrt(max(var, 0.0)))

        # Measured s_z, for plotting only.
        photon_fraction = np.clip(
            (self.apd - cal.v_apd_all_down) / cal.v_range, 0.0, 1.0)
        s_z_meas = spin_value_from_photon_fraction(
            photon_fraction, cal.feedback_measurement_midpoint_fraction,
            cal.feedback_measurement_midpoint_remap_enabled)

        grid_step = float(f[1] - f[0]) if f.size > 1 else np.nan
        metadata = {
            "run_id": getattr(getattr(self.ad, "run_info", None), "run_id", None),
            "likelihood": (self.likelihood if self.likelihood == "gaussian"
                           else f"student_t(dof={self.student_t_dof:g})"),
            "n_shot": n_shot,
            "n_pulse": n_pulse,
            "grid_step_hz": grid_step,
            "frequency_detuning_residual": self.frequency_detuning_residual,
            "t_raman_pulse_source": self.t_raman_pulse_source,
            "pulse_times_vary": bool(self.pulse_times_vary),
            "t_raman_pulse_min": float(self.t_eff.min()),
            "t_raman_pulse_max": float(self.t_eff.max()),
        }

        # -- goodness of fit -------------------------------------------------
        # The likelihood takes std_n_photons_per_shot as exact and every APD /
        # Bloch constant as exact, so f_rabi is the ONLY thing left to absorb a
        # mis-calibration. When the readout calibration does not describe the
        # data, the fit cannot say so -- it just reports a confident wrong
        # frequency. Worse, high-f hypotheses decorrelate s_z pulse-to-pulse
        # under randomized durations, so a large grid full of them acts like
        # many independent guesses and the MAP runs to whichever boundary you
        # chose. Run 76245 did exactly this: residuals were 7.8x the assumed
        # sigma at every hypothesis, and the "answer" tracked the grid maximum
        # (65 / 98 / 150 kHz for three different windows).
        #
        # So: measure the realized residual scatter at the MAP and compare it
        # with the sigma the likelihood assumed. This is the check that turns a
        # silent wrong number into a visible calibration failure.
        j_map = int(np.argmax(posterior_joint))
        p1_map = expected_photon_fraction(
            s_z_model[:, :, j_map],
            cal.feedback_measurement_midpoint_fraction,
            cal.feedback_measurement_midpoint_remap_enabled)
        resid = k_meas - cal.n_photons_per_shot * p1_map
        resid_rms = float(np.sqrt(np.mean(resid * resid)))
        sigma_assumed = float(cal.std_n_photons_per_shot)
        excess = resid_rms / sigma_assumed if sigma_assumed > 0 else np.inf
        metadata["resid_rms_photons"] = resid_rms
        metadata["sigma_assumed_photons"] = sigma_assumed
        metadata["excess_noise_factor"] = excess

        if excess > GOF_EXCESS_NOISE_LIMIT:
            metadata["gof_warning"] = (
                f"residual RMS at the MAP is {resid_rms:.1f} photons but the "
                f"likelihood assumed sigma = {sigma_assumed:.1f} ({excess:.1f}x). "
                f"The model does not describe this data, so f_rabi is absorbing "
                f"a calibration error and this number is NOT a measurement. "
                f"Check the APD readout calibration (v_apd_all_up/down, "
                f"midpoint_fraction) for this run, then re-fit with "
                f"RabiJointPosterior, which marginalizes them instead of "
                f"trusting them.")
            print("[RabiPosterior] WARNING: " + metadata["gof_warning"])

        # A MAP pinned near an edge means the window, not the data, chose the
        # answer. Widened from the two edge-most points, which under-covered a
        # MAP that is boundary-driven but a few steps in.
        edge = max(2, int(round(0.05 * f.size)))
        if f.size > 4 and (j_map <= edge or j_map >= f.size - 1 - edge):
            metadata["boundary_warning"] = (
                f"MAP is at grid index {j_map} of {f.size - 1} -- within "
                f"{edge} steps ({100.0 * edge / (f.size - 1):.0f}% of the span) "
                f"of a boundary. The posterior is probably truncated; widen the "
                f"grid and re-run.")
            print("[RabiPosterior] warning: " + metadata["boundary_warning"])

        self.result = RabiPosteriorResult(
            f_rabi_grid=f,
            posterior_joint=posterior_joint,
            posterior_shot=posterior_shot,
            posterior_vs_pulse=posterior_vs_pulse,
            posterior_joint_vs_pulse=posterior_joint_vs_pulse,
            s_z_model=s_z_model,
            s_z_meas=s_z_meas,
            k_meas=k_meas,
            state=state,
            t_eff=self.t_eff,
            t_ideal=t_ideal,
            f_map=f_map,
            f_mean=f_mean,
            f_std=f_std,
            ci68=_credible_interval(f, posterior_joint, 0.68),
            ci95=_credible_interval(f, posterior_joint, 0.95),
            t_pi_map=(1.0 / (2.0 * f_map) if f_map > 0 else np.nan),
            calibration=cal,
            metadata=metadata,
        )
        return self.result

    def _require_result(self):
        if self.result is None:
            self.run()
        return self.result

    # -- nuisance sweep -----------------------------------------------------

    def sweep_nuisance(self, name, values, **run_overrides):
        """Re-run the posterior for each value of a fixed nuisance parameter.

        A robustness check, not a joint fit: it answers "how much does the Rabi
        estimate move if this calibration constant is stale?".

        Returns a dict with 'values', 'f_map', 'f_mean', 'f_std' and the full
        'posteriors' array of shape (len(values), n_grid).
        """
        if not hasattr(self.cal, name):
            raise AttributeError(f"RabiCalibration has no field {name!r}")

        values = np.asarray(values, dtype=float).ravel()
        original = getattr(self.cal, name)
        saved_result = self.result

        f_map, f_mean, f_std, posteriors = [], [], [], []
        try:
            for v in values:
                setattr(self.cal, name, float(v))
                self.result = None
                res = self.run()
                f_map.append(res.f_map)
                f_mean.append(res.f_mean)
                f_std.append(res.f_std)
                posteriors.append(res.posterior_joint)
        finally:
            setattr(self.cal, name, original)
            self.result = saved_result

        return {
            "name": name,
            "values": values,
            "f_map": np.array(f_map),
            "f_mean": np.array(f_mean),
            "f_std": np.array(f_std),
            "posteriors": np.array(posteriors),
            "nominal": original,
        }

    # -- systematic budget --------------------------------------------------

    def systematic_budget(self, fractions=None, detuning_hz=500.0,
                          verbose=True):
        """Shift in the fitted Rabi frequency when each nuisance is perturbed.

        For each calibration constant, re-runs the posterior at (1 -/+ frac)
        times its nominal value and records how far the MAP moves. The
        half-range of that pair is that constant's contribution; contributions
        are combined in quadrature.

        This is a one-at-a-time sensitivity study, not a joint fit -- it assumes
        the nuisances are uncorrelated and the response is locally linear. Its
        job is to tell you whether you are statistics- or systematics-limited.

        NOTE: frequency_lightshift and t_img_pulse enter the model only through
        their product, so they are exactly degenerate. Their entries will match
        for equal fractional perturbations; do not count both.

        Args:
            fractions: {name: fractional 1-sigma uncertainty}. Defaults to
                DEFAULT_SYSTEMATIC_FRACTIONS, which are PLACEHOLDERS -- supply
                your measured uncertainties for a meaningful number.
            detuning_hz: assumed 1-sigma uncertainty on the Raman transition
                frequency being correct, Hz. Set to 0 to skip.

        Returns:
            dict with 'rows' (name, nominal, minus, plus, half_range),
            'total_quadrature', 'f_std' and 'f_map'.
        """
        base = self._require_result()
        f0 = base.f_mean
        if fractions is None:
            fractions = DEFAULT_SYSTEMATIC_FRACTIONS

        saved_result = self.result
        rows = []
        try:
            for name, frac in fractions.items():
                if not hasattr(self.cal, name):
                    raise AttributeError(
                        f"RabiCalibration has no field {name!r}")
                nominal = getattr(self.cal, name)
                shifts = []
                for sign in (-1.0, +1.0):
                    setattr(self.cal, name, nominal * (1.0 + sign * frac))
                    self.result = None
                    shifts.append(self.run().f_mean - f0)
                setattr(self.cal, name, nominal)
                rows.append({
                    "name": name, "nominal": nominal, "fraction": frac,
                    "minus": shifts[0], "plus": shifts[1],
                    "half_range": 0.5 * abs(shifts[1] - shifts[0]),
                })

            if detuning_hz:
                nominal = self.frequency_detuning_residual
                shifts = []
                for sign in (-1.0, +1.0):
                    self.frequency_detuning_residual = nominal + sign * detuning_hz
                    self.result = None
                    shifts.append(self.run().f_mean - f0)
                self.frequency_detuning_residual = nominal
                rows.append({
                    "name": "raman transition frequency",
                    "nominal": nominal, "fraction": np.nan,
                    "minus": shifts[0], "plus": shifts[1],
                    "half_range": 0.5 * abs(shifts[1] - shifts[0]),
                })
        finally:
            self.result = saved_result

        total = float(np.sqrt(sum(r["half_range"] ** 2 for r in rows)))
        out = {"rows": rows, "total_quadrature": total,
               "f_std": base.f_std, "f_mean": f0, "f_map": base.f_map}

        if verbose:
            # Shifts are quoted on the posterior MEAN, which moves smoothly with
            # the nuisances; the MAP would be quantized to the grid step.
            print(f"systematic budget about f_mean = {f0/1e3:.4f} kHz")
            print(f"  {'nuisance':<38} {'+/-':>7} {'minus':>9} {'plus':>9} "
                  f"{'half-range':>13}")
            print("-" * 82)
            for r in rows:
                frac = ("%.0f%%" % (100 * r["fraction"])
                        if np.isfinite(r["fraction"]) else "%.0f Hz" % detuning_hz)
                print(f"  {r['name']:<38} {frac:>7} {r['minus']:>+9.1f} "
                      f"{r['plus']:>+9.1f} {r['half_range']:>10.1f} Hz")
            print("-" * 82)
            print(f"  {'total (quadrature)':<38} {'':>7} {'':>9} {'':>9} "
                  f"{total:>10.1f} Hz")
            print(f"  {'statistical (posterior sigma)':<38} {'':>7} {'':>9} "
                  f"{'':>9} {base.f_std:>10.1f} Hz")
            if total > base.f_std:
                print("\n  -> SYSTEMATICS-LIMITED. More repeats will not help; "
                      "tighten the calibrations.")
            else:
                print("\n  -> statistics-limited; more repeats will help.")
            print("  (fractions are placeholders unless you supplied your own; "
                  "lightshift and t_img are\n   degenerate -- do not count both)")

        return out

    # -- plotting -----------------------------------------------------------
    def _title(self, extra=""):
        res = self.result
        run_id = res.metadata.get("run_id") if res else None
        head = f"run {run_id}" if run_id is not None else "synthetic"
        cal = self.cal
        head += (f" | t_img {cal.t_img_pulse*1e6:.1f} us"
                 f" | C {cal.back_action_coherence:.3f}"
                 f" | f_ls {cal.frequency_lightshift/1e3:.1f} kHz")
        return head + (f"\n{extra}" if extra else "")

    def plot_posterior(self, ax=None, show_shots=False):
        """Joint posterior over the Rabi-frequency grid."""
        import matplotlib.pyplot as plt
        res = self._require_result()
        if ax is None:
            _, ax = plt.subplots()

        f_khz = res.f_rabi_grid / 1e3
        if show_shots:
            for r in range(res.posterior_shot.shape[0]):
                ax.plot(f_khz, res.posterior_shot[r], color='0.8', lw=0.6, zorder=1)
            ax.plot([], [], color='0.8', lw=0.6, label='per shot')

        ax.plot(f_khz, res.posterior_joint, 'k-', lw=1.5, label='joint', zorder=3)
        ax.axvline(res.f_map / 1e3, color='C3', ls='--', lw=1,
                   label=f'MAP {res.f_map/1e3:.3f} kHz')
        ax.axvspan(res.ci95[0] / 1e3, res.ci95[1] / 1e3, color='C0', alpha=0.12,
                   label='95% CI')

        f_cal = self.cal.f_rabi_calibration
        if np.isfinite(f_cal):
            ax.axvline(f_cal / 1e3, color='C2', ls=':', lw=1,
                       label=f'calibration {f_cal/1e3:.3f} kHz')

        ax.set_xlabel('rabi frequency (kHz)')
        ax.set_ylabel('posterior')
        ax.legend(fontsize='small')
        ax.set_title(self._title('rabi frequency posterior'), fontsize='small')
        return ax

    def plot_posterior_vs_pulse(self, ax=None, log_scale=True, shot_idx=None):
        """Posterior convergence: pulse index vs hypothesis."""
        import matplotlib.pyplot as plt
        from matplotlib.colors import LogNorm
        res = self._require_result()
        if ax is None:
            _, ax = plt.subplots()

        if shot_idx is None:
            p = res.posterior_joint_vs_pulse
            label = 'all shots'
        else:
            p = res.posterior_vs_pulse[shot_idx]
            label = f'shot {shot_idx}'

        floor = max(p[p > 0].min(), 1e-12) if np.any(p > 0) else 1e-12
        norm = LogNorm(vmin=floor, vmax=max(p.max(), floor * 10)) if log_scale else None

        pulses = np.arange(p.shape[0] + 1) + 0.5
        f_edges = _bin_edges(res.f_rabi_grid) / 1e3
        mesh = ax.pcolormesh(pulses, f_edges, np.clip(p, floor, None).T,
                             norm=norm, cmap='viridis', shading='auto')
        plt.colorbar(mesh, ax=ax, label='posterior')

        ax.axhline(res.f_map / 1e3, color='w', ls='--', lw=1)
        ax.set_xlabel('pulse index')
        ax.set_ylabel('rabi frequency (kHz)')
        ax.set_title(self._title(f'posterior convergence ({label})'), fontsize='small')
        return ax

    def plot_traces(self, ax=None, max_shots=None):
        """Measured s_z per pulse against the MAP-hypothesis model.

        With randomized pulse times no two shots share a rotation schedule, so
        shot 3's fourth pulse is not the same rotation as shot 7's and a
        cross-shot mean at a fixed pulse index means nothing. In that regime
        each shot is drawn as its own measured/model pair instead; plot_parity
        is the aggregate view that does not care about the schedule.
        """
        import matplotlib.pyplot as plt
        res = self._require_result()
        if ax is None:
            _, ax = plt.subplots()

        pulses = np.arange(res.s_z_meas.shape[1]) + 1
        n_show = res.s_z_meas.shape[0] if max_shots is None else min(
            max_shots, res.s_z_meas.shape[0])

        if res.pulse_times_vary:
            model_map = res.s_z_model_map
            for r in range(n_show):
                ax.plot(pulses, res.s_z_meas[r], '-o', color='0.75',
                        lw=0.7, ms=2.5, zorder=1)
                ax.plot(pulses, model_map[r], '--s', color='C3',
                        lw=0.7, ms=2.5, alpha=0.75, zorder=2)
            ax.plot([], [], '-o', color='0.75', ms=3,
                    label='measured (per shot)')
            ax.plot([], [], '--s', color='C3', ms=3,
                    label=f'model @ MAP {res.f_map/1e3:.3f} kHz (per shot)')
            subtitle = (f'measured vs modelled spin '
                        f'({n_show} shots, randomized pulse times)')
        else:
            for r in range(n_show):
                ax.plot(pulses, res.s_z_meas[r], color='0.85', lw=0.6, zorder=1)

            # Every shot is an independent repeat of the same single scan point
            # AND the same pulse schedule, so the standard error is just
            # std / sqrt(n_shot).
            mean = res.s_z_meas.mean(axis=0)
            stderr = res.s_z_meas.std(axis=0, ddof=1) / np.sqrt(res.s_z_meas.shape[0]) \
                if res.s_z_meas.shape[0] > 1 else np.zeros_like(mean)
            ax.errorbar(pulses, mean, yerr=stderr, fmt='o', color='k', ms=4,
                        capsize=2, label='measured', zorder=3)

            ax.plot(pulses, res.s_z_model_map.mean(axis=0), 's--', color='C3',
                    ms=4, label=f'model @ MAP {res.f_map/1e3:.3f} kHz', zorder=4)

            f_cal = self.cal.f_rabi_calibration
            if np.isfinite(f_cal):
                j = int(np.argmin(np.abs(res.f_rabi_grid - f_cal)))
                if abs(res.f_rabi_grid[j] - f_cal) < 2 * abs(
                        res.metadata.get('grid_step_hz', np.inf)):
                    ax.plot(pulses, res.s_z_model[:, :, j].mean(axis=0), '^:',
                            color='C2', ms=4,
                            label=f'model @ calibration {f_cal/1e3:.3f} kHz',
                            zorder=2)
            subtitle = 'measured vs modelled spin'

        ax.set_xlabel('pulse index')
        ax.set_ylabel(r'$s_z$')
        ax.set_xticks(pulses)
        ax.legend(fontsize='small')
        ax.set_title(self._title(subtitle), fontsize='small')
        return ax

    def plot_parity(self, ax=None):
        """Every measurement against what the MAP hypothesis predicts for it.

        One point per (shot, pulse), coloured by pulse index. This is the
        goodness-of-fit view that survives randomized pulse times: it never
        compares one shot's pulse i to another's, so it stays meaningful when
        every shot follows its own rotation schedule. Points scatter about
        y = x if the model and the fitted Rabi frequency describe the data;
        curvature or a pulse-index-ordered drift away from the line is model
        error, not noise.
        """
        import matplotlib.pyplot as plt
        res = self._require_result()
        if ax is None:
            _, ax = plt.subplots()

        model = res.s_z_model_map
        meas = res.s_z_meas
        pulse_idx = np.tile(np.arange(meas.shape[1]) + 1, (meas.shape[0], 1))

        sc = ax.scatter(model.ravel(), meas.ravel(), c=pulse_idx.ravel(),
                        cmap='viridis', s=12, alpha=0.8, zorder=2)
        plt.colorbar(sc, ax=ax, label='pulse index')

        lo = min(model.min(), meas.min())
        hi = max(model.max(), meas.max())
        pad = 0.05 * (hi - lo) if hi > lo else 0.05
        line = np.array([lo - pad, hi + pad])
        ax.plot(line, line, 'k--', lw=1, zorder=1, label='y = x')

        rms = float(np.sqrt(np.mean((meas - model) ** 2)))
        ax.set_xlim(line)
        ax.set_ylim(line)
        ax.set_xlabel(rf'model $s_z$ @ MAP {res.f_map/1e3:.3f} kHz')
        ax.set_ylabel(r'measured $s_z$')
        ax.legend(fontsize='small')
        ax.set_title(self._title(f'parity (rms residual {rms:.4f})'),
                     fontsize='small')
        return ax

    def plot_bloch(self, ax=None, shot_idx=0):
        """Bloch components through the train at the MAP hypothesis."""
        import matplotlib.pyplot as plt
        res = self._require_result()
        if ax is None:
            _, ax = plt.subplots()

        j = int(np.argmax(res.posterior_joint))
        s = res.state[shot_idx, :, j, :]
        pulses = np.arange(s.shape[0]) + 1

        for k, (lbl, color) in enumerate(
                zip([r'$s_x$', r'$s_y$', r'$s_z$'], ['C0', 'C1', 'C3'])):
            ax.plot(pulses, s[:, k], 'o-', color=color, ms=4, label=lbl)

        norm = np.linalg.norm(s, axis=1)
        ax.plot(pulses, norm, 'k:', lw=1, label='|s|')

        ax.axhline(0, color='0.7', lw=0.5)
        ax.set_xlabel('pulse index')
        ax.set_ylabel('bloch component')
        ax.set_xticks(pulses)
        ax.legend(fontsize='small', ncol=2)
        sched = (f", t_pulse {res.t_eff[shot_idx].min()*1e6:.2f}-"
                 f"{res.t_eff[shot_idx].max()*1e6:.2f} us"
                 if res.pulse_times_vary else "")
        ax.set_title(
            self._title(f'bloch trajectory @ MAP {res.f_map/1e3:.3f} kHz '
                        f'(shot {shot_idx}{sched})'), fontsize='small')
        return ax

    def plot_report(self, figsize=(11, 8)):
        """Four diagnostics in one figure.

        The last panel is the parity plot when the pulse times are randomized
        (where the aggregate fit quality is the thing to check) and the Bloch
        trajectory otherwise; plot_bloch is still there to call directly.
        """
        import matplotlib.pyplot as plt
        res = self._require_result()
        fig, axes = plt.subplots(2, 2, figsize=figsize)
        self.plot_posterior(ax=axes[0, 0])
        self.plot_posterior_vs_pulse(ax=axes[0, 1])
        self.plot_traces(ax=axes[1, 0])
        if res.pulse_times_vary:
            self.plot_parity(ax=axes[1, 1])
        else:
            self.plot_bloch(ax=axes[1, 1])
        fig.tight_layout()
        return fig, axes


# ---------------------------------------------------------------------------
# joint posterior
# ---------------------------------------------------------------------------

# The outer grid axes, in array order. These are exactly the parameters that
# enter the model non-linearly; v_apd_all_down and v_apd_all_up do not appear
# because they are marginalized in closed form (see RabiJointPosterior).
JOINT_AXES = ("f_rabi", "midpoint_fraction", "frequency_lightshift",
              "back_action_coherence")

# expected_photon_fraction clips p1 into [0, 1]. Inside |midpoint - 0.5| <= 1/4
# that clip is provably inactive for |s_z| <= 1 -- p1 is monotonic in s_z there,
# hitting exactly 0 and 1 at s_z = -1 and +1 -- which is what makes the model
# exactly linear in (v_down, v_up). Outside it the clip bites and the closed
# form silently stops being the right answer, so the grid is refused instead.
MIDPOINT_HALF_RANGE = 0.25

# Peak element count of the (n_shot, n_pulse, n_f, n_midpoint) work array. The
# midpoint axis is chunked to respect this; ~4e6 doubles is ~32 MB per temporary.
_JOINT_CHUNK_ELEMS = 4_000_000


def _resolve_axis_grid(spec, default, name):
    """Turn a grid spec into (values, is_pinned).

    None            -> pinned to `default`, axis length 1
    scalar          -> pinned to that value, axis length 1
    (lo, hi, n)     -> np.linspace(lo, hi, n)      [tuple only]
    array-like      -> used verbatim, sorted ascending
    """
    if spec is None:
        if default is None or not np.isfinite(default):
            raise ValueError(f"{name}: no grid given and no calibration value "
                             f"to pin to")
        return np.array([float(default)]), True

    if isinstance(spec, tuple):
        if len(spec) != 3:
            raise ValueError(
                f"{name}: tuple spec must be (lo, hi, n), got {spec!r}")
        lo, hi, n = spec
        n = int(n)
        if n < 1:
            raise ValueError(f"{name}: n must be >= 1, got {n}")
        if n == 1:
            return np.array([0.5 * (float(lo) + float(hi))]), True
        return np.linspace(float(lo), float(hi), n), False

    values = np.atleast_1d(np.asarray(spec, dtype=float)).ravel()
    if values.size == 0:
        raise ValueError(f"{name}: empty grid")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{name}: grid contains non-finite values")
    values = np.sort(values)
    if values.size > 1 and np.any(np.diff(values) <= 0):
        raise ValueError(f"{name}: grid has duplicate values")
    return values, values.size == 1


def _group_identical_rows(t_eff, apd, quantum=1.e-12):
    """Collapse shots that share a pulse schedule into weighted groups.

    A deterministic duration scan repeats each schedule N_repeats times, so the
    forward model only has to run once per distinct schedule -- a 30x saving at
    30 repeats. A randomized-pulse-time run has no repeats and this is a no-op
    (n_group == n_shot), which is correct, just not a saving.

    Rows are keyed on durations rounded to `quantum` (1 ps) so that float noise
    in a saved container cannot split a group that is physically one schedule;
    the group's representative durations are the mean of its members.

    Returns:
        t_group: (n_group, n_pulse) representative durations.
        n_group_shots: (n_group,) how many shots each group stands for.
        sum_v: (n_group, n_pulse) sum of APD voltage over each group's shots.
    """
    keys = np.rint(t_eff / quantum).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True,
                                  return_inverse=True)
    inverse = np.asarray(inverse).ravel()
    n_group = first.size

    n_group_shots = np.bincount(inverse, minlength=n_group).astype(float)
    t_group = np.empty((n_group, t_eff.shape[1]), dtype=float)
    sum_v = np.empty((n_group, apd.shape[1]), dtype=float)
    for g in range(n_group):
        members = inverse == g
        t_group[g] = t_eff[members].mean(axis=0)
        sum_v[g] = apd[members].sum(axis=0)
    return t_group, n_group_shots, sum_v

@dataclass
class RabiJointPosteriorResult:
    """Joint posterior over the outer grid, plus the marginalized APD endpoints.

    `posterior` is indexed in JOINT_AXES order:
    (n_f_rabi, n_midpoint, n_lightshift, n_coherence). A pinned axis has length
    1, so a run that grids only f_rabi still returns a 4-D array.
    """

    posterior: np.ndarray                   # (n_f, n_m, n_ls, n_c)
    grids: dict                             # axis name -> (n,) values
    axis_stats: dict                        # axis name -> summary dict

    # Conditional posterior of the APD endpoints in every outer cell. These are
    # what the analytic marginalization produces on the way past; the reported
    # v_down / v_up combine them over the outer posterior.
    v_down_cond: np.ndarray                 # (n_f, n_m, n_ls, n_c) volts
    v_up_cond: np.ndarray
    v_down_var_cond: np.ndarray
    v_up_var_cond: np.ndarray

    v_down: tuple                           # (mean, std) volts
    v_up: tuple
    v_range: tuple

    calibration: RabiCalibration = None
    metadata: dict = field(default_factory=dict)

    # -- access -------------------------------------------------------------

    def marginal(self, name):
        """1-D marginal posterior over one outer axis."""
        i = JOINT_AXES.index(name)
        return self.posterior.sum(axis=tuple(k for k in range(4) if k != i))

    def marginal_2d(self, name_a, name_b):
        """2-D marginal over two outer axes, returned in (a, b) order."""
        ia, ib = JOINT_AXES.index(name_a), JOINT_AXES.index(name_b)
        if ia == ib:
            raise ValueError("marginal_2d needs two different axes")
        p = self.posterior.sum(axis=tuple(k for k in range(4)
                                          if k not in (ia, ib)))
        return p if ia < ib else p.T

    def best(self):
        """MAP value of every outer axis, plus the APD endpoints in that cell."""
        j = np.unravel_index(int(np.argmax(self.posterior)), self.posterior.shape)
        out = {name: float(self.grids[name][j[i]])
               for i, name in enumerate(JOINT_AXES)}
        out["v_apd_all_down"] = float(self.v_down_cond[j])
        out["v_apd_all_up"] = float(self.v_up_cond[j])
        return out

    def fitted_calibration(self):
        """A RabiCalibration with the posterior means substituted in.

        Feed this back into RabiPosterior to see what the tightened constants do
        to the Rabi answer, or into systematic_budget with the fitted spreads as
        the fractional uncertainties.
        """
        from dataclasses import replace as _replace
        cal = self.calibration or RabiCalibration()
        out = _replace(
            cal,
            frequency_lightshift=self.axis_stats["frequency_lightshift"]["mean"],
            back_action_coherence=self.axis_stats["back_action_coherence"]["mean"],
            feedback_measurement_midpoint_fraction=(
                self.axis_stats["midpoint_fraction"]["mean"]),
            v_apd_all_down=self.v_down[0],
            v_apd_all_up=self.v_up[0],
        )
        # replace() copies `sources` wholesale, which would keep claiming these
        # five came off ad.p when they are now fit results.
        out.sources = dict(cal.sources)
        for f in ("frequency_lightshift", "back_action_coherence",
                  "feedback_measurement_midpoint_fraction",
                  "v_apd_all_down", "v_apd_all_up"):
            out.sources[f] = "fitted"
        return out

    # -- reporting ----------------------------------------------------------

    def summary(self):
        md = self.metadata
        lines = [
            f"run {md.get('run_id', '?')} | {md.get('n_shot', '?')} shots x "
            f"{md.get('n_pulse', '?')} pulses "
            f"({md.get('n_group', '?')} distinct pulse schedules)",
            f"  likelihood    : {md.get('likelihood', '?')}",
            f"  apd endpoints : {md.get('apd_mode', '?')}",
        ]
        fmt = {
            "f_rabi": ("f_rabi", 1e-3, "kHz", 4),
            "midpoint_fraction": ("midpoint", 1.0, "", 4),
            "frequency_lightshift": ("f_lightshift", 1e-3, "kHz", 4),
            "back_action_coherence": ("back_action_C", 1.0, "", 4),
        }
        for name in JOINT_AXES:
            st = self.axis_stats[name]
            label, mult, unit, prec = fmt[name]
            unit = (" " + unit) if unit else ""
            if st["pinned"]:
                lines.append(f"  {label:<14}: {st['mean']*mult:.{prec}f}{unit} "
                             f"(pinned)")
                continue
            lines.append(
                f"  {label:<14}: {st['mean']*mult:.{prec}f} +/- "
                f"{st['std']*mult:.{prec}f}{unit}   "
                f"[MAP {st['map']*mult:.{prec}f}, 68% "
                f"{st['ci68'][0]*mult:.{prec}f} - {st['ci68'][1]*mult:.{prec}f}]")
        lines += [
            f"  v_apd_all_down: {self.v_down[0]*1e3:.4f} +/- "
            f"{self.v_down[1]*1e3:.4f} mV",
            f"  v_apd_all_up  : {self.v_up[0]*1e3:.4f} +/- "
            f"{self.v_up[1]*1e3:.4f} mV",
            f"  v_range       : {self.v_range[0]*1e3:.4f} +/- "
            f"{self.v_range[1]*1e3:.4f} mV",
        ]
        f_map = self.axis_stats["f_rabi"]["map"]
        if f_map > 0:
            lines.append(f"  t_pi (MAP)    : {1.0/(2.0*f_map)*1e6:.5f} us")
        if self.calibration is not None:
            lines.append(f"  {self.calibration.provenance_line()}")
        for w in md.get("boundary_warnings", []):
            lines.append("  !! " + w)
        if md.get("polarity_warning"):
            lines.append("  !! " + md["polarity_warning"])
        if md.get("design_warning"):
            lines.append("  !! " + md["design_warning"])
        if self.calibration is not None and self.calibration.defaulted_fields():
            lines.append(
                "  !! some fixed calibration constants are NOT from this run's "
                "params (see 'calibration src' above); they fell back to the "
                "current module defaults.")
        return "\n".join(lines)

    def print(self):
        print(self.summary())


class RabiJointPosterior:
    """Joint posterior over the Rabi frequency AND the measurement calibration.

    RabiPosterior grids over f_rabi with every APD and Bloch constant held
    fixed, which makes it systematics-limited (see the SYSTEMATICS WARNING at
    the top of this module). Given that the Raman transition frequency is
    already correct -- the premise of the pulse-train experiment -- the same
    data can instead constrain those constants.

    WHY THIS IS CHEAP
    -----------------
    Work in voltage rather than photon-count space. With

        g = midpoint + 0.5*s_z - (midpoint - 0.5)*s_z**2

    (expected_photon_fraction, rearranged) the forward model is

        v_model = v_down + (v_up - v_down)*g = (1 - g)*v_down + g*v_up

    Two things follow. s_z comes out of evolve_pulse_train and depends only on
    f_rabi, the pulse times, frequency_lightshift*t_img_pulse and
    back_action_coherence -- never on v_up, v_down or the midpoint. And
    v_model is exactly LINEAR in (v_down, v_up).

    So the six-parameter problem factors: a 4-D outer grid over the parameters
    that enter non-linearly (JOINT_AXES), with (v_down, v_up) marginalized in
    closed form by a 2x2 Bayesian linear regression in every cell. No MCMC, no
    optimizer, no six-dimensional grid. n_photons_per_shot drops out entirely,
    entering only through the noise scale, so it needs no calibration here.

    WHAT IS AND IS NOT IDENTIFIED
    -----------------------------
    frequency_lightshift and t_img_pulse enter only through their product, so
    only the product is determined. The lightshift axis is reported as a
    frequency at the recorded t_img_pulse; do not also claim t_img_pulse.

    frequency_lightshift and back_action_coherence are recoverable only
    CONDITIONAL on the drive being on resonance. A residual detuning would be
    partly absorbed by them.

    EXPERIMENT DESIGN MATTERS MORE THAN SHOT COUNT
    ----------------------------------------------
    Simulated round trips at the current calibration, all at 30 shots x 15
    pulses = 450 measurements, quoting the seed-to-seed scatter of the
    posterior mean:

        pulse schedule                        f_rabi   midpoint   v_down
        randomized in [1/4, 3/4]*t_pi         581 Hz     0.040    3.1 mV
        randomized in [0.15, 1.9]*t_pi        317 Hz     0.040    5.0 mV
        fixed per shot, scanned [0.15, 1.9]    80 Hz     0.036    0.9 mV

    Two separate effects compound. Holding the duration FIXED within a shot
    makes the accumulated rotation exactly i*theta at pulse i, so sensitivity
    to Omega grows coherently along the train; randomizing turns that into a
    partial random walk. And a WIDE duration range sweeps s_z across the whole
    [-1, +1] interval, so v_up and v_down (which live at s_z = +/-1) are
    interpolated rather than extrapolated.

    rabi_posterior_pulse_train randomizes its pulse times on purpose -- it
    calibrates Omega for a feedback loop that itself drives randomized
    durations. That is the right choice for that experiment and the wrong one
    for this fit; run apd_joint_calibration instead, which scans the duration
    deterministically. Running this on randomized data works, it is just
    several times less sharp, and summary() says so.

    Typical use:

        from kexp import atomdata
        from kexp.analysis import RabiJointPosterior

        ad = atomdata(76200)
        jp = RabiJointPosterior(
            ad,
            f_rabi_grid=(54.e3, 58.e3, 81),
            midpoint_grid=(0.50, 0.72, 45),
            lightshift_grid=(28.e3, 42.e3, 21),
            coherence_grid=(0.75, 0.95, 21),
        )
        jp.run().print()
        jp.plot_marginals()
    """

    def __init__(self, ad=None, *,
                 f_rabi_grid=(DEFAULT_F_RABI_MIN, DEFAULT_F_RABI_MAX,
                              DEFAULT_N_GRID),
                 midpoint_grid=None,
                 lightshift_grid=None,
                 coherence_grid=None,
                 marginalize_apd=True,
                 v_range_sign="calibration",
                 sigma_mode="marginalized",
                 sigma_v=None,
                 v_down_prior=None,
                 v_up_prior=None,
                 prior=None,
                 frequency_detuning_residual=0.0,
                 phi=0.0,
                 apd=None, t_raman_pulse=None, calibration=None,
                 **calibration_overrides):
        """
        Args:
            f_rabi_grid, midpoint_grid, lightshift_grid, coherence_grid: one
                spec per outer axis. None pins the axis to its calibration
                value (length 1); a 3-TUPLE (lo, hi, n) becomes a linspace; any
                other array-like is used verbatim. Pinning every axis but
                f_rabi reproduces RabiPosterior's question with the APD
                endpoints still fitted.
            marginalize_apd: True (default) marginalizes (v_down, v_up)
                analytically. False pins them at the calibration values, which
                is what RabiPosterior does.
            v_range_sign: which way round the APD readout is allowed to come
                out. "calibration" (default) takes the sign of
                v_apd_all_up - v_apd_all_down; "data" takes it from the
                model-free first-pulse regression (polarity_check); +1/-1 force
                it; None lets the fit choose.

                This must be pinned, because swapping v_up <-> v_down is an
                EXACT symmetry of the measurement map -- it is algebraically
                identical to (s_z -> -s_z, midpoint -> 1 - midpoint):

                    1 - g(s_z, m) == g(-s_z, 1 - m)

                (verified to 6e-17). Only the Bloch dynamics, which pin
                s_z(0) = +1, break the tie, and they break it weakly, so an
                unpinned fit can settle in the mirrored branch and report a
                mirrored midpoint with a negative v_range.

                "calibration" is right because "up" IS the prepared state by
                definition, and apd_voltage_vs_state_2 measures which voltage
                that state reads (s_z = +1 reads the HIGHER voltage). There is
                no reason to let the fit relitigate it.

                USE "data" FOR RUNS TAKEN BEFORE 2026-08-25. Both pulse-train
                experiments used to declare img_types.ABSORPTION while the APD
                calibration was taken under DISPERSIVE; since
                init_kernel(setup_slm=True) picks the SLM phase mask off that
                flag, those runs read the atoms out through a flat mask instead
                of the phase-contrast dot and their APD response is inverted
                with respect to v_apd_all_up/down. polarity_check() detects this
                per run -- 76245 gives slope -37.8 mV per unit s_z from the
                first pulse alone against a stored v_range/2 of +36.8 mV, corr
                -0.87: right magnitude, wrong sign. On such a run "calibration"
                pins the branch the data is not in (155 kHz, residual RMS
                9.55 mV against a raw data scatter of 10.29 mV -- a model
                explaining nothing) while "data" recovers 57.4 kHz, matching the
                independent Raman scan.

                Implemented as a truncated prior: each cell's marginal
                likelihood is multiplied by the posterior mass of v_range on
                the allowed side, so a cell that only just favours the wrong
                sign is penalized smoothly rather than hard-rejected.

            sigma_mode: "marginalized" (default) integrates the noise scale out
                under a Jeffreys prior, so std_n_photons_per_shot need not be
                trusted; "fixed" holds it at sigma_v.
            sigma_v: measurement sigma in VOLTS. Defaults to
                std_n_photons_per_shot*v_range/n_photons_per_shot, which is the
                exact voltage-space equivalent of RabiPosterior's fixed
                photon-count sigma. Only used when sigma_mode="fixed"; in
                "marginalized" mode it just sets the scale at which an absolute
                v_down_prior / v_up_prior is interpreted.
            v_down_prior, v_up_prior: (mean, sigma) Gaussian priors on the APD
                endpoints, in volts. None is flat. ad.data.apd_reference[0]
                (light leakage with the atoms released) is an approximate
                independent anchor on v_down -- approximate because "no atoms"
                is not identical to "all atoms in |down>".
            prior: {axis name: (n,) array} priors over the outer grid. Missing
                axes are uniform.
            frequency_detuning_residual: drive minus resonance, Hz. Zero is the
                premise of the experiment.
            calibration_overrides: any RabiCalibration field.
        """
        if sigma_mode not in ("marginalized", "fixed"):
            raise ValueError("sigma_mode must be 'marginalized' or 'fixed', "
                             f"got {sigma_mode!r}")

        self.ad = ad
        self.sigma_mode = sigma_mode
        self.marginalize_apd = bool(marginalize_apd)
        self._v_range_sign_spec = v_range_sign
        self.frequency_detuning_residual = float(frequency_detuning_residual)
        self.phi = float(phi)

        if calibration is not None:
            self.cal = calibration
            for k, v in calibration_overrides.items():
                setattr(self.cal, k, v)
        elif ad is not None:
            self.cal = RabiCalibration.from_params(ad.p, **calibration_overrides)
        else:
            self.cal = RabiCalibration(**calibration_overrides)

        # Sign the APD readout is allowed to take. Resolved here rather than
        # Reused verbatim from RabiPosterior -- the container layout, the
        # per-shot randomized pulse lists and the fallbacks for older runs are
        # all handled there, and _load_data touches no other instance state.
        self.apd, self.t_eff = RabiPosterior._load_data(
            self, ad, apd, t_raman_pulse)
        self.n_shot, self.n_pulse = self.apd.shape

        # Readout polarity. Resolved after _load_data because the "data" option
        # needs the loaded APD trace. See the v_range_sign docstring.
        if v_range_sign is None:
            self._v_range_sign = 0.0
        elif isinstance(v_range_sign, str):
            if v_range_sign == "calibration":
                self._v_range_sign = float(np.sign(
                    self.cal.v_apd_all_up - self.cal.v_apd_all_down))
                if self._v_range_sign == 0.0:
                    raise ValueError(
                        "v_range_sign='calibration' needs v_apd_all_up != "
                        "v_apd_all_down, but the calibration has them equal")
            elif v_range_sign == "data":
                chk = self.polarity_check()
                self._v_range_sign = float(chk["sign_from_data"])
                if self._v_range_sign == 0.0:
                    raise ValueError(
                        "v_range_sign='data' could not determine a sign -- the "
                        "first-pulse s_z range is too narrow to regress against "
                        "(see polarity_check()). Pass +1/-1 explicitly.")
            else:
                raise ValueError(
                    "v_range_sign must be 'calibration', 'data', +1, -1 or "
                    f"None, got {v_range_sign!r}")
        else:
            self._v_range_sign = float(np.sign(v_range_sign))
            if self._v_range_sign == 0.0:
                raise ValueError("v_range_sign must be nonzero")

        self.sigma_v = (float(sigma_v) if sigma_v is not None
                        else (self.cal.std_n_photons_per_shot * self.cal.v_range
                              / self.cal.n_photons_per_shot))
        if not np.isfinite(self.sigma_v) or self.sigma_v <= 0:
            raise ValueError(f"sigma_v must be positive, got {self.sigma_v}")

        # -- outer grids
        specs = (
            (f_rabi_grid, self.cal.f_rabi_calibration),
            (midpoint_grid, self.cal.feedback_measurement_midpoint_fraction),
            (lightshift_grid, self.cal.frequency_lightshift),
            (coherence_grid, self.cal.back_action_coherence),
        )
        self.grids = {}
        self.pinned = {}
        for name, (spec, default) in zip(JOINT_AXES, specs):
            values, is_pinned = _resolve_axis_grid(spec, default, name)
            self.grids[name] = values
            self.pinned[name] = is_pinned

        mid = self.grids["midpoint_fraction"]
        if np.any(np.abs(mid - 0.5) > MIDPOINT_HALF_RANGE + 1.e-12):
            raise ValueError(
                f"midpoint_grid spans {mid.min():.4f} - {mid.max():.4f}, "
                f"outside |midpoint - 0.5| <= {MIDPOINT_HALF_RANGE}. Beyond "
                "that the [0, 1] clip in expected_photon_fraction becomes "
                "active and the model stops being linear in (v_down, v_up), "
                "so the closed-form marginalization would be silently wrong.")
        coh = self.grids["back_action_coherence"]
        if np.any(coh <= 0) or np.any(coh > 1.0):
            raise ValueError("coherence_grid must lie in (0, 1]")

        # -- outer priors
        self.prior = {}
        for name in JOINT_AXES:
            n = self.grids[name].size
            if prior is None or name not in prior or prior[name] is None:
                self.prior[name] = np.full(n, 1.0 / n)
                continue
            p = np.asarray(prior[name], dtype=float).ravel()
            if p.size != n:
                raise ValueError(f"prior[{name!r}] has {p.size} points but the "
                                 f"grid has {n}")
            if np.any(p < 0) or not np.any(p > 0):
                raise ValueError(f"prior[{name!r}] must be non-negative with "
                                 "some positive mass")
            self.prior[name] = p / p.sum()

        # -- APD endpoint priors, as (precision, mean) in volt units
        self._v_prior = []
        for spec, nominal in ((v_down_prior, self.cal.v_apd_all_down),
                              (v_up_prior, self.cal.v_apd_all_up)):
            if spec is None:
                self._v_prior.append((0.0, float(nominal)))
                continue
            mu, sd = spec
            sd = float(sd)
            if sd <= 0:
                raise ValueError("APD endpoint prior sigma must be positive; "
                                 "use marginalize_apd=False to pin instead")
            self._v_prior.append((1.0 / (sd * sd), float(mu)))

        # -- collapse repeated pulse schedules
        self.t_group, self.n_group_shots, self.sum_v = _group_identical_rows(
            self.t_eff, self.apd)
        self.n_group = self.t_group.shape[0]

        self.result = None

    # -- run ----------------------------------------------------------------

    def polarity_check(self, verbose=False):
        """Which way round the APD readout actually is, model-free.

        Uses ONLY the first pulse of each shot, so no back-action, light shift
        or accumulated rotation enters -- s_z after pulse 1 is just
        cos(Omega*t_ideal) with Omega = pi/t_raman_pi_pulse taken from the
        independent absorption scan already stored in the params. Regressing the
        first APD read against that s_z gives the sign AND the size of the
        readout response with no reference to this module's forward model.

        A healthy run returns sign_from_data == sign_from_calibration and
        slope ~= v_range/2. Runs 76245 and 76269 return the right magnitude with
        the WRONG sign, because the pulse train then declared
        img_types.ABSORPTION and so read the atoms out through a flat SLM mask
        rather than the phase-contrast dot the APD calibration was taken with.
        Analyse those with v_range_sign='data'; runs taken after the
        2026-08-25 fix should agree and can use the default 'calibration'.

        Returns a dict with the correlation, slope, expected slope, both signs
        and whether they agree.
        """
        t_pi = self.cal.t_raman_pi_pulse
        v_range = self.cal.v_range
        out = {
            "sign_from_calibration": float(np.sign(v_range)),
            "sign_from_data": 0.0,
            "corr": np.nan, "slope": np.nan,
            "slope_expected": 0.5 * v_range,
            "agree": None,
            "note": "",
        }
        if not np.isfinite(t_pi) or t_pi <= 0:
            out["note"] = ("no t_raman_pi_pulse in the calibration, so there is "
                           "no independent Omega to regress against")
            return out

        omega = np.pi / t_pi
        s_z1 = np.cos(omega * (self.t_eff[:, 0] - self.cal.t_turn_on_delay))
        v1 = self.apd[:, 0]

        # Too little lever arm to say anything -- e.g. every shot's first pulse
        # lands near s_z = -1 where cos is flat.
        if s_z1.size < 3 or np.ptp(s_z1) < 0.15 or np.std(v1) == 0:
            out["note"] = (f"first-pulse s_z spans only {np.ptp(s_z1):.3f}; too "
                           "flat to determine polarity from this run")
            return out

        out["corr"] = float(np.corrcoef(s_z1, v1)[0, 1])
        out["slope"] = float(np.polyfit(s_z1, v1, 1)[0])
        out["sign_from_data"] = float(np.sign(out["slope"]))
        out["agree"] = bool(out["sign_from_data"] == out["sign_from_calibration"])

        if verbose:
            print(f"  first-pulse s_z spans [{s_z1.min():+.3f}, {s_z1.max():+.3f}]"
                  f" over {s_z1.size} shots")
            print(f"  corr(s_z, v_apd) = {out['corr']:+.3f}")
            print(f"  slope            = {out['slope']*1e3:+.2f} mV per unit s_z"
                  f"   (calibration expects {out['slope_expected']*1e3:+.2f})")
            print("  => " + ("polarity agrees with the calibration" if out["agree"]
                             else "POLARITY DISAGREES with the calibration"))
        return out

    def _cell_posterior(self, G00, G01, G11, h0, h1, Svv, n_data):
        """Marginalize (v_down, v_up) out of one block of outer cells.

        G* are the entries of X'X and h* of X'v, accumulated over every
        (shot, pulse); Svv is v'v. Everything is elementwise over whatever
        block shape the caller passes.

        Returns (log_likelihood, v_down, v_up, var_down, var_up), with
        hypothesis-independent constants dropped from the log-likelihood.
        """
        (lam0, mu0), (lam1, mu1) = self._v_prior

        if not self.marginalize_apd:
            # Endpoints are pinned at the calibration, so the polarity is
            # already whatever the calibration says -- nothing to constrain.
            vd, vu = mu0, mu1
            rss = (Svv - 2.0 * (vd * h0 + vu * h1)
                   + vd * vd * G00 + 2.0 * vd * vu * G01 + vu * vu * G11)
            rss = np.maximum(rss, np.finfo(float).tiny)
            if self.sigma_mode == "fixed":
                logL = -0.5 * rss / (self.sigma_v ** 2)
            else:
                logL = -0.5 * n_data * np.log(rss)
            zero = np.zeros_like(rss)
            return logL, np.full_like(rss, vd), np.full_like(rss, vu), zero, zero

        if self.sigma_mode == "fixed":
            # Precision in absolute volt^-2 units.
            inv_s2 = 1.0 / (self.sigma_v ** 2)
            A00 = G00 * inv_s2 + lam0
            A01 = G01 * inv_s2
            A11 = G11 * inv_s2 + lam1
            b0 = h0 * inv_s2 + lam0 * mu0
            b1 = h1 * inv_s2 + lam1 * mu1
            const = Svv * inv_s2 + lam0 * mu0 * mu0 + lam1 * mu1 * mu1
        else:
            # Normal-inverse-gamma with a Jeffreys prior on sigma^2: the
            # endpoint prior lives in sigma^2 units, calibrated so that an
            # absolute prior sigma means what it says at the nominal noise.
            s2 = self.sigma_v ** 2
            A00 = G00 + lam0 * s2
            A01 = G01
            A11 = G11 + lam1 * s2
            b0 = h0 + lam0 * s2 * mu0
            b1 = h1 + lam1 * s2 * mu1
            const = Svv + lam0 * s2 * mu0 * mu0 + lam1 * s2 * mu1 * mu1

        det = A00 * A11 - A01 * A01
        ok = det > 0
        det_safe = np.where(ok, det, 1.0)
        vd = (A11 * b0 - A01 * b1) / det_safe
        vu = (A00 * b1 - A01 * b0) / det_safe
        q = np.maximum(const - (b0 * vd + b1 * vu), np.finfo(float).tiny)

        if self.sigma_mode == "fixed":
            logL = -0.5 * np.log(det_safe) - 0.5 * q
            var_d = A11 / det_safe
            var_u = A00 / det_safe
        else:
            logL = -0.5 * np.log(det_safe) - 0.5 * n_data * np.log(q)
            # Posterior of (v_down, v_up) is multivariate-t; its covariance is
            # (b_n/(a_n - 1)) * A^-1 with a_n = n/2, b_n = q/2.
            scale = q / max(n_data - 2, 1)
            var_d = scale * A11 / det_safe
            var_u = scale * A00 / det_safe

        # Truncated prior on the readout polarity. The (v_down, v_up) posterior
        # in this cell is Gaussian (Student-t in marginalized sigma mode, but
        # with n_data in the hundreds the normal CDF is indistinguishable), so
        # restricting it to the half-plane sign*(v_up - v_down) > 0 just
        # multiplies the cell's marginal likelihood by the mass on that side.
        # The truncated prior's normalizer is hypothesis-independent and drops
        # out, so this is exact rather than a heuristic mask.
        #
        # Var(v_up - v_down) = var_u + var_d - 2*cov, and cov = -A01/det (times
        # the same `scale` the variances already carry).
        if self._v_range_sign and self.marginalize_apd:
            cov_scale = (q / max(n_data - 2, 1)
                         if self.sigma_mode != "fixed" else 1.0)
            cov_du = -cov_scale * A01 / det_safe
            var_range = np.maximum(var_d + var_u - 2.0 * cov_du,
                                   np.finfo(float).tiny)
            z = self._v_range_sign * (vu - vd) / np.sqrt(var_range)
            logL = logL + _log_ndtr(z)

        logL = np.where(ok, logL, -np.inf)
        return logL, vd, vu, var_d, var_u

    def run(self, verbose=False):
        """Evaluate the outer grid and marginalize the APD endpoints."""
        from dataclasses import replace

        cal = self.cal
        t_ideal = self.t_group - cal.t_turn_on_delay
        if np.any(t_ideal <= 0):
            raise ValueError(
                f"t_turn_on_delay ({cal.t_turn_on_delay*1e9:.1f} ns) is >= the "
                f"shortest pulse ({self.t_group.min()*1e9:.1f} ns)")

        f_g = self.grids["f_rabi"]
        m_g = self.grids["midpoint_fraction"]
        ls_g = self.grids["frequency_lightshift"]
        c_g = self.grids["back_action_coherence"]
        shape = (f_g.size, m_g.size, ls_g.size, c_g.size)

        logL = np.empty(shape)
        v_down_c = np.empty(shape)
        v_up_c = np.empty(shape)
        var_down_c = np.empty(shape)
        var_up_c = np.empty(shape)

        n_data = self.n_shot * self.n_pulse
        Svv = float((self.apd * self.apd).sum())
        Sv = float(self.apd.sum())
        w = self.n_group_shots

        step = max(1, _JOINT_CHUNK_ELEMS
                   // max(1, self.n_group * self.n_pulse * f_g.size))

        for a, ls in enumerate(ls_g):
            for b, coh in enumerate(c_g):
                lc = replace(cal, frequency_lightshift=float(ls),
                             back_action_coherence=float(coh))
                s_z, _ = evolve_pulse_train(
                    t_ideal, self.t_group, f_g, lc,
                    frequency_detuning_residual=self.frequency_detuning_residual,
                    phi=self.phi)                      # (n_group, n_pulse, n_f)
                s_z2 = s_z * s_z

                for j0 in range(0, m_g.size, step):
                    mm = m_g[j0:j0 + step]
                    # g is the photon fraction; the [0, 1] clip is provably
                    # inactive over the allowed midpoint range, which is what
                    # keeps the model linear in (v_down, v_up).
                    g = mm + 0.5 * s_z[..., None] - (mm - 0.5) * s_z2[..., None]
                    Sg = np.einsum('g,gpfm->fm', w, g)
                    Sgg = np.einsum('g,gpfm->fm', w, g * g)
                    bg = np.einsum('gp,gpfm->fm', self.sum_v, g)
                    del g

                    # X'X and X'v for design columns [1 - g, g], expanded so
                    # only g and g**2 ever have to be materialized.
                    G00 = n_data - 2.0 * Sg + Sgg
                    G01 = Sg - Sgg
                    G11 = Sgg
                    h0 = Sv - bg
                    h1 = bg

                    cell = self._cell_posterior(G00, G01, G11, h0, h1,
                                                Svv, n_data)
                    sl = (slice(None), slice(j0, j0 + step), a, b)
                    logL[sl], v_down_c[sl], v_up_c[sl] = cell[0], cell[1], cell[2]
                    var_down_c[sl], var_up_c[sl] = cell[3], cell[4]

            if verbose:
                print(f"[RabiJointPosterior] lightshift {a + 1}/{ls_g.size} done")

        # Outer priors are separable, so they add as a rank-1 log term per axis.
        for i, name in enumerate(JOINT_AXES):
            p = self.prior[name]
            lp = np.log(np.where(p > 0, p, np.finfo(float).tiny))
            logL = logL + lp.reshape([-1 if k == i else 1 for k in range(4)])

        posterior = np.exp(logL - np.max(logL))
        total = posterior.sum()
        if not np.isfinite(total) or total <= 0:
            raise RuntimeError("posterior underflowed to zero everywhere -- "
                               "check the grids and the calibration")
        posterior /= total

        # -- per-axis marginal statistics
        axis_stats = {}
        boundary = []
        for i, name in enumerate(JOINT_AXES):
            grid = self.grids[name]
            marg = posterior.sum(axis=tuple(k for k in range(4) if k != i))
            mean = float((marg * grid).sum())
            var = float((marg * grid * grid).sum() - mean * mean)
            j_map = int(np.argmax(marg))
            axis_stats[name] = {
                "mean": mean,
                "std": float(np.sqrt(max(var, 0.0))),
                "map": float(grid[j_map]),
                "ci68": _credible_interval(grid, marg, 0.68),
                "ci95": _credible_interval(grid, marg, 0.95),
                "marginal": marg,
                "grid": grid,
                "pinned": bool(self.pinned[name]),
            }
            if (not self.pinned[name] and grid.size > 4
                    and (j_map <= 1 or j_map >= grid.size - 2)):
                boundary.append(
                    f"{name}: MAP at grid index {j_map} of {grid.size - 1} -- "
                    "within two steps of a boundary; widen the grid and re-run.")

        # -- APD endpoints: law of total variance over the outer posterior.
        # The spread of the per-cell means alone would understate this by
        # leaving out each cell's own regression uncertainty.
        def _combine(mean_c, var_c):
            mean = float((posterior * mean_c).sum())
            second = float((posterior * (var_c + mean_c * mean_c)).sum())
            return mean, float(np.sqrt(max(second - mean * mean, 0.0)))

        v_down = _combine(v_down_c, var_down_c)
        v_up = _combine(v_up_c, var_up_c)
        # v_range shares the outer cell with both endpoints, so its spread has
        # to be built from the difference, not from the two marginals.
        v_range = _combine(v_up_c - v_down_c, var_down_c + var_up_c)

        schedules_vary = self.n_group > 1 and self.n_group == self.n_shot
        metadata = {
            "run_id": getattr(getattr(self.ad, "run_info", None), "run_id", None),
            "n_shot": self.n_shot,
            "n_pulse": self.n_pulse,
            "n_group": self.n_group,
            "n_data": n_data,
            "likelihood": ("gaussian, sigma marginalized (jeffreys)"
                           if self.sigma_mode == "marginalized"
                           else f"gaussian, sigma fixed at "
                                f"{self.sigma_v*1e3:.4f} mV"),
            "apd_mode": ("marginalized analytically" if self.marginalize_apd
                         else "pinned at calibration"),
            "sigma_v": self.sigma_v,
            "frequency_detuning_residual": self.frequency_detuning_residual,
            "t_img_pulse": cal.t_img_pulse,
            "boundary_warnings": boundary,
            "v_range_sign_constraint": self._v_range_sign,
        }
        if schedules_vary:
            metadata["design_warning"] = (
                "every shot has its own pulse schedule (randomized times). "
                "This fit is several times less sharp than a deterministic "
                "duration scan at equal shot count -- see the class docstring.")

        # Readout polarity. Three things can disagree here -- the calibration,
        # the model-free first-pulse regression, and the sign this fit settled
        # on -- and any disagreement invalidates the number, so say so rather
        # than letting the fitted v_range quietly carry the news.
        pol = self.polarity_check()
        metadata["polarity_check"] = pol
        sign_fit = float(np.sign(v_range[0]))
        if pol["sign_from_data"] and not pol["agree"]:
            metadata["polarity_warning"] = (
                f"this run's APD readout is INVERTED with respect to "
                f"v_apd_all_up/down. First pulse alone gives slope "
                f"{pol['slope']*1e3:+.2f} mV per unit s_z (corr "
                f"{pol['corr']:+.2f}) where the calibration expects "
                f"{pol['slope_expected']*1e3:+.2f} mV -- right magnitude, wrong "
                f"sign. Known cause: the experiment declared "
                f"img_types.ABSORPTION, so init_kernel(setup_slm=True) wrote a "
                f"FLAT SLM mask instead of the phase-contrast dot the APD "
                f"calibration was taken with (fixed 2026-08-25; runs before "
                f"that are affected). Re-run this fit with v_range_sign='data' "
                f"to analyse the polarity the run actually has, or re-take the "
                f"data now that the experiment declares DISPERSIVE.")
        elif pol["sign_from_data"] and sign_fit and sign_fit != pol["sign_from_data"]:
            metadata["polarity_warning"] = (
                f"this fit settled on v_range {v_range[0]*1e3:+.2f} mV but the "
                f"model-free first-pulse regression says the readout slope is "
                f"{pol['slope']*1e3:+.2f} mV per unit s_z. The fit is in the "
                f"mirrored branch (v_up<->v_down with midpoint -> 1-midpoint is "
                f"an exact symmetry of the measurement map); re-run with "
                f"v_range_sign='data'.")

        for warning in boundary:
            print("[RabiJointPosterior] warning: " + warning)
        if metadata.get("polarity_warning"):
            print("[RabiJointPosterior] WARNING: " + metadata["polarity_warning"])

        self.result = RabiJointPosteriorResult(
            posterior=posterior,
            grids={k: v for k, v in self.grids.items()},
            axis_stats=axis_stats,
            v_down_cond=v_down_c,
            v_up_cond=v_up_c,
            v_down_var_cond=var_down_c,
            v_up_var_cond=var_up_c,
            v_down=v_down,
            v_up=v_up,
            v_range=v_range,
            calibration=cal,
            metadata=metadata,
        )
        return self.result

    def _require_result(self):
        if self.result is None:
            self.run()
        return self.result

    # -- plotting -----------------------------------------------------------

    _AXIS_PLOT = {
        "f_rabi": ("rabi frequency (kHz)", 1.e-3),
        "midpoint_fraction": ("midpoint fraction", 1.0),
        "frequency_lightshift": ("lightshift frequency (kHz)", 1.e-3),
        "back_action_coherence": ("back-action coherence", 1.0),
    }

    def _free_axes(self):
        return [n for n in JOINT_AXES if not self.pinned[n]]

    def plot_marginals(self, axes=None, figsize=(11, 3)):
        """1-D marginal posterior for every free outer axis."""
        import matplotlib.pyplot as plt
        res = self._require_result()
        names = self._free_axes()
        if not names:
            raise ValueError("every outer axis is pinned -- nothing to plot")

        if axes is None:
            _, axes = plt.subplots(1, len(names), figsize=figsize)
        axes = np.atleast_1d(axes)

        nominal = {
            "f_rabi": self.cal.f_rabi_calibration,
            "midpoint_fraction": self.cal.feedback_measurement_midpoint_fraction,
            "frequency_lightshift": self.cal.frequency_lightshift,
            "back_action_coherence": self.cal.back_action_coherence,
        }
        for ax, name in zip(axes, names):
            st = res.axis_stats[name]
            label, mult = self._AXIS_PLOT[name]
            ax.plot(st["grid"] * mult, st["marginal"], 'k-', lw=1.5)
            ax.axvline(st["mean"] * mult, color='C3', ls='--', lw=1,
                       label=f"{st['mean']*mult:.4g} +/- {st['std']*mult:.3g}")
            ax.axvspan(st["ci95"][0] * mult, st["ci95"][1] * mult,
                       color='C0', alpha=0.12, label='95% CI')
            if np.isfinite(nominal[name]):
                ax.axvline(nominal[name] * mult, color='C2', ls=':', lw=1,
                           label=f'calibration {nominal[name]*mult:.4g}')
            ax.set_xlabel(label)
            ax.set_ylabel('marginal posterior')
            ax.legend(fontsize='x-small')
        return axes

    def plot_corner(self, figsize=(9, 8)):
        """Pairwise 2-D marginals over the free outer axes.

        Correlated ridges here are the whole point: a tilted (f_rabi,
        lightshift) blob says the two trade off, which is exactly the
        degeneracy the one-at-a-time systematic_budget cannot see.
        """
        import matplotlib.pyplot as plt
        res = self._require_result()
        names = self._free_axes()
        if len(names) < 2:
            raise ValueError("need at least two free axes for a corner plot")

        n = len(names)
        fig, axes = plt.subplots(n - 1, n - 1, figsize=figsize, squeeze=False)
        for i in range(n - 1):
            for j in range(n - 1):
                ax = axes[i][j]
                if j > i:
                    ax.axis('off')
                    continue
                ya, xa = names[i + 1], names[j]
                p = res.marginal_2d(xa, ya)
                xl, xm = self._AXIS_PLOT[xa]
                yl, ym = self._AXIS_PLOT[ya]
                ax.pcolormesh(_bin_edges(res.grids[xa]) * xm,
                              _bin_edges(res.grids[ya]) * ym,
                              p.T, cmap='viridis', shading='auto')
                if i == n - 2:
                    ax.set_xlabel(xl, fontsize='small')
                else:
                    ax.set_xticklabels([])
                if j == 0:
                    ax.set_ylabel(yl, fontsize='small')
                else:
                    ax.set_yticklabels([])
                ax.tick_params(labelsize='x-small')
        fig.suptitle(f"run {res.metadata.get('run_id', 'synthetic')} | "
                     "joint posterior", fontsize='small')
        fig.tight_layout()
        return fig, axes


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _is_usable_pulse_times(x):
    """True if x is a non-empty array of finite, strictly positive durations.

    An unwritten data container reads back as all zeros, which this rejects so
    the caller can fall back to the scalar param instead of raising.
    """
    x = np.asarray(x, dtype=float)
    return bool(x.size and np.all(np.isfinite(x)) and np.all(x > 0))


def _log_ndtr(z):
    """log of the standard normal CDF, stable far into the left tail.

    Used for the v_range_sign truncated prior, where a cell that strongly
    prefers the forbidden polarity gives z ~ -50 and a naive log(cdf) would
    underflow to -inf and lose the ordering between such cells.
    """
    z = np.asarray(z, dtype=float)
    try:
        from scipy.special import log_ndtr as _sp_log_ndtr
        return _sp_log_ndtr(z)
    except ImportError:
        # phi(z)/(-z) asymptotics in the far tail, erfc elsewhere. Matches
        # scipy to ~1e-12 over the range that matters here.
        from math import erfc as _erfc
        out = np.empty_like(z)
        tail = z < -6.0
        zt = z[tail]
        out[tail] = (-0.5 * zt * zt - 0.5 * np.log(2.0 * np.pi)
                     - np.log(-zt) + np.log1p(-1.0 / (zt * zt)))
        zb = z[~tail]
        out[~tail] = np.log(np.array(
            [0.5 * _erfc(-v / np.sqrt(2.0)) for v in np.ravel(zb)]
        ).reshape(zb.shape))
        return out


def _normalize_log(log_p, axis=-1):
    """Exponentiate and normalize a log-probability array, stably."""
    log_p = np.asarray(log_p, dtype=float)
    p = np.exp(log_p - np.max(log_p, axis=axis, keepdims=True))
    total = np.sum(p, axis=axis, keepdims=True)
    # An all-underflow row would divide by zero; fall back to uniform.
    n = log_p.shape[axis]
    return np.where(total > 0, p / np.where(total > 0, total, 1.0), 1.0 / n)


def _credible_interval(f, posterior, level):
    """Equal-tailed credible interval from the discrete posterior."""
    f = np.asarray(f, dtype=float)
    if f.size == 1:
        return (float(f[0]), float(f[0]))
    cdf = np.cumsum(posterior)
    cdf = cdf / cdf[-1]
    lo_q = 0.5 * (1.0 - level)
    hi_q = 1.0 - lo_q
    lo = float(np.interp(lo_q, cdf, f))
    hi = float(np.interp(hi_q, cdf, f))
    return (lo, hi)


def _bin_edges(centers):
    """Cell edges for pcolormesh from grid centers."""
    centers = np.asarray(centers, dtype=float)
    if centers.size == 1:
        return np.array([centers[0] - 0.5, centers[0] + 0.5])
    mid = 0.5 * (centers[1:] + centers[:-1])
    return np.concatenate((
        [centers[0] - (mid[0] - centers[0])],
        mid,
        [centers[-1] + (centers[-1] - mid[-1])]))
