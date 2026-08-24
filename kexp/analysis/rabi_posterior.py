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
shot-noise term n*p1*q is deliberately left out (it is commented out at
kexp/base/feedback.py:265), so a single fixed, generously-sized sigma absorbs
unmodelled excess noise instead of the likelihood becoming razor-sharp wherever
the model happens to predict p1 near 0 or 1. A heavier-tailed Student-t option
is also available for outlier robustness.

Everything is vectorized over (shot, hypothesis); only the short pulse axis is a
Python loop.

SYSTEMATICS WARNING
-------------------
With the current calibration the answer is systematics-limited, not
statistics-limited. At N_repeats = 30 the posterior width is ~0.6 kHz, but a 5%
error in the light shift moves the MAP by ~1 kHz. The reason is that the
per-pulse azimuthal kick is large:

    alpha_z = -2*pi*frequency_lightshift*t_img_pulse
            = -2*pi*35 kHz*5 us = -1.10 rad = -63 deg

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

__all__ = [
    "RabiPosterior",
    "RabiPosteriorResult",
    "RabiCalibration",
    "simulate_pulse_train_apd",
    "DEFAULT_F_RABI_MIN",
    "DEFAULT_F_RABI_MAX",
    "DEFAULT_N_GRID",
    "DEFAULT_SYSTEMATIC_FRACTIONS",
]

DEFAULT_F_RABI_MIN = 55.e3
DEFAULT_F_RABI_MAX = 75.e3
DEFAULT_N_GRID = 51

# Programmed pulse time minus coherent rotation area (AOM/switch turn-on
# latency). Matches expt_params_feedback.py: t_raman_pulse_ideal =
# t_raman_pulse - 127e-9.
DEFAULT_T_TURN_ON_DELAY = 127.e-9

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
    """

    t_img_pulse: float = 5.e-6
    frequency_lightshift: float = 3.5e4
    back_action_coherence: float = 0.852941
    feedback_measurement_midpoint_fraction: float = 0.607
    feedback_measurement_midpoint_remap_enabled: bool = True
    v_apd_all_up: float = -0.10884
    v_apd_all_down: float = -0.17686
    n_photons_per_shot: float = 1028.0
    std_n_photons_per_shot: float = 206.44
    t_turn_on_delay: float = DEFAULT_T_TURN_ON_DELAY
    t_raman_pi_pulse: float = np.nan

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
        """Scrape an ExptParams (or ad.p) for whatever it has, defaults elsewhere."""
        kwargs = {}
        for f in ("t_img_pulse", "frequency_lightshift", "back_action_coherence",
                  "feedback_measurement_midpoint_fraction",
                  "feedback_measurement_midpoint_remap_enabled",
                  "v_apd_all_up", "v_apd_all_down",
                  "std_n_photons_per_shot", "t_raman_pi_pulse"):
            v = getattr(p, f, None)
            if v is not None:
                kwargs[f] = v

        # The kernel stores this as N_photons_per_shot after
        # _initialize_measurement_calibrations; the params file declares it
        # lowercase. Accept either.
        for name in ("n_photons_per_shot", "N_photons_per_shot"):
            v = getattr(p, name, None)
            if v is not None:
                kwargs["n_photons_per_shot"] = float(v)
                break

        # Turn-on delay is only implied, as the gap between the programmed and
        # ideal pulse times.
        t_prog = getattr(p, "t_raman_pulse", None)
        t_ideal = getattr(p, "t_raman_pulse_ideal", None)
        if t_prog is not None and t_ideal is not None:
            t_prog = float(np.ravel(t_prog)[0])
            t_ideal = float(np.ravel(t_ideal)[0])
            if np.isfinite(t_prog) and np.isfinite(t_ideal):
                kwargs["t_turn_on_delay"] = t_prog - t_ideal

        kwargs.update(overrides)

        # Coerce so a stray numpy scalar or 0-d array cannot poison broadcasting.
        for k, v in list(kwargs.items()):
            if k == "feedback_measurement_midpoint_remap_enabled":
                kwargs[k] = bool(v)
            else:
                kwargs[k] = float(v)
        return cls(**kwargs)


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
        alpha_z = delta * t_eff[:, i][:, None] - cal.omega_z_lightshift * cal.t_img_pulse
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
                             noise_scale=1.0):
    """Generate synthetic APD voltages from the forward model.

    Used by the notebook's round-trip test: simulate at a known f_rabi, run the
    posterior, confirm recovery. Noise is Gaussian in photon count at
    std_n_photons_per_shot, matching what the likelihood assumes.

    Returns:
        apd: (n_shot, n_pulse) integrator voltages.
        t_raman_pulse_rr: (n_shot, n_pulse) programmed pulse durations.
    """
    if t_raman_pulse is None:
        # Default to the pi/2 pulse the experiment actually uses.
        t_pi = cal.t_raman_pi_pulse
        if not np.isfinite(t_pi) or t_pi <= 0:
            t_pi = 1.0 / (2.0 * f_rabi_true)
        t_raman_pulse = t_pi / 2.0

    t_eff = np.full((n_shot, n_pulse), float(t_raman_pulse))
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

    f_map: float
    f_mean: float
    f_std: float
    ci68: tuple
    ci95: tuple
    t_pi_map: float

    calibration: RabiCalibration = None
    metadata: dict = field(default_factory=dict)

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
            f"  f_rabi (MAP)  : {self.f_map/1e3:.4f} kHz",
            f"  f_rabi (mean) : {self.f_mean/1e3:.4f} +/- {self.f_std/1e3:.4f} kHz",
            f"  68% CI        : [{self.ci68[0]/1e3:.4f}, {self.ci68[1]/1e3:.4f}] kHz",
            f"  95% CI        : [{self.ci95[0]/1e3:.4f}, {self.ci95[1]/1e3:.4f}] kHz",
            f"  t_pi (MAP)    : {self.t_pi_map*1e6:.5f} us",
            f"  calibration   : f_rabi = {cal_f/1e3:.4f} kHz "
            f"(t_raman_pi_pulse = {self.calibration.t_raman_pi_pulse*1e6:.5f} us)"
            if self.calibration else "",
        ]
        if self.metadata.get("boundary_warning"):
            lines.append("  !! " + self.metadata["boundary_warning"])
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

        # Programmed pulse durations, per shot and pulse.
        if t_raman_pulse is None and ad is not None:
            t_raman_pulse = getattr(ad.data, "t_raman_pulse", None)
        if t_raman_pulse is None and ad is not None:
            # Older/simpler runs may only carry the scalar param.
            t_raman_pulse = getattr(ad.p, "t_raman_pulse", None)
        if t_raman_pulse is None:
            raise ValueError(
                "no pulse durations found -- pass t_raman_pulse explicitly")

        t_eff = np.asarray(t_raman_pulse, dtype=float)
        if t_eff.ndim == 0:
            t_eff = np.full(apd.shape, float(t_eff))
        else:
            if t_eff.ndim == 1 and t_eff.size == n_pulse:
                t_eff = np.tile(t_eff, (apd.shape[0], 1))
            else:
                t_eff = t_eff.reshape(-1, t_eff.shape[-1])
                if t_eff.shape[0] != apd.shape[0]:
                    raise ValueError(
                        f"t_raman_pulse has {t_eff.shape[0]} shots but apd has "
                        f"{apd.shape[0]}")

        if not np.all(np.isfinite(t_eff)) or np.any(t_eff <= 0):
            raise ValueError("t_raman_pulse contains non-positive or non-finite values")

        return apd, t_eff

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
            # Fixed sigma: the binomial n*p1*q term stays out, exactly as at
            # kexp/base/feedback.py:265. This is what makes the posterior
            # tolerant of unmodelled excess measurement noise.
            return -0.5 * z_sq
        dof = self.student_t_dof
        return -0.5 * (dof + 1.0) * np.log1p(z_sq / dof)

    # -- run ----------------------------------------------------------------

    def run(self):
        """Run the forward model over the grid and accumulate the posterior."""
        cal = self.cal
        t_ideal = self.t_eff - cal.t_turn_on_delay
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
        }

        # The current calibration (55.68 kHz for t_pi = 8.9806 us) sits very
        # close to the low edge of the default 55-75 kHz window, so this check
        # earns its keep.
        j_map = int(np.argmax(posterior_joint))
        if f.size > 4 and (j_map <= 1 or j_map >= f.size - 2):
            metadata["boundary_warning"] = (
                f"MAP is at grid index {j_map} of {f.size - 1} -- within two "
                f"steps of a boundary. The posterior is probably truncated; "
                f"widen the grid and re-run.")
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
        """Measured s_z per pulse against the MAP-hypothesis model."""
        import matplotlib.pyplot as plt
        res = self._require_result()
        if ax is None:
            _, ax = plt.subplots()

        pulses = np.arange(res.s_z_meas.shape[1]) + 1
        n_show = res.s_z_meas.shape[0] if max_shots is None else min(
            max_shots, res.s_z_meas.shape[0])
        for r in range(n_show):
            ax.plot(pulses, res.s_z_meas[r], color='0.85', lw=0.6, zorder=1)

        # Every shot is an independent repeat of the same single scan point, so
        # the standard error is just std / sqrt(n_shot).
        mean = res.s_z_meas.mean(axis=0)
        stderr = res.s_z_meas.std(axis=0, ddof=1) / np.sqrt(res.s_z_meas.shape[0]) \
            if res.s_z_meas.shape[0] > 1 else np.zeros_like(mean)
        ax.errorbar(pulses, mean, yerr=stderr, fmt='o', color='k', ms=4,
                    capsize=2, label='measured', zorder=3)

        ax.plot(pulses, res.s_z_model_map.mean(axis=0), 's--', color='C3', ms=4,
                label=f'model @ MAP {res.f_map/1e3:.3f} kHz', zorder=4)

        f_cal = self.cal.f_rabi_calibration
        if np.isfinite(f_cal):
            j = int(np.argmin(np.abs(res.f_rabi_grid - f_cal)))
            if abs(res.f_rabi_grid[j] - f_cal) < 2 * abs(
                    res.metadata.get('grid_step_hz', np.inf)):
                ax.plot(pulses, res.s_z_model[:, :, j].mean(axis=0), '^:',
                        color='C2', ms=4,
                        label=f'model @ calibration {f_cal/1e3:.3f} kHz', zorder=2)

        ax.set_xlabel('pulse index')
        ax.set_ylabel(r'$s_z$')
        ax.set_xticks(pulses)
        ax.legend(fontsize='small')
        ax.set_title(self._title('measured vs modelled spin'), fontsize='small')
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
        ax.set_title(
            self._title(f'bloch trajectory @ MAP {res.f_map/1e3:.3f} kHz '
                        f'(shot {shot_idx})'), fontsize='small')
        return ax

    def plot_report(self, figsize=(11, 8)):
        """All four diagnostics in one figure."""
        import matplotlib.pyplot as plt
        self._require_result()
        fig, axes = plt.subplots(2, 2, figsize=figsize)
        self.plot_posterior(ax=axes[0, 0])
        self.plot_posterior_vs_pulse(ax=axes[0, 1])
        self.plot_traces(ax=axes[1, 0])
        self.plot_bloch(ax=axes[1, 1])
        fig.tight_layout()
        return fig, axes


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

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
