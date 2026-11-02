"""Adaptive Ramsey policies for the single-shot frequency estimator (2026-10-30, DESIGN STAGE).

Where this comes from
---------------------
The feedback loop (kexp.base.feedback.Feedback + base_expt_feedback.FeedbackExpt) is, physically,
a Ramsey sequence already: every gap between two Raman pulses is a free evolution in the frame of
the drive, and the pulse that follows maps the accumulated phase onto S_z, which the weak APD read
samples. Its two findings that motivate this module (session notes 2026-10-07 .. 10-30):

* the posterior aliases at 1/T, T the pulse-start period (~66 us -> 15 kHz), because every gap
  is the same length; alternating gaps killed the first alias tooth;
* the final width saturates at ~1.5 kHz and stretching ALL later gaps by x2..x8 (longgap_sim,
  10-30 00:21) did not narrow it: the width is coherence-limited (each read costs x0.84 of the
  transverse Bloch length, so ~5-6 reads carry information) and a long gap aliases unless the
  posterior is already narrower than 1/T.

The textbook answer (Berry & Wiseman 2000; Said, Berry & Twamley 2011; Bonato et al. 2016) is to
make the Ramsey sequence adaptive within the shot: choose the next gap from the current posterior
width -- short while the posterior is broad, longer as it narrows, so the fringe period 1/T always
spans the credible interval and never aliases -- and choose the phase of the next pulse so the
expected S_z after it sits on the steepest slope of the fringe (maximum Fisher information per
read). Nothing here re-prepares the spin: there is no optical pumping mid shot and the posterior
is not carried across shots (user rule 2026-10-07). The pulse that reads the phase is also the
pulse that puts the (shrunk) Bloch vector back on the equator for the next gap: with the axis
parallel to the transverse state a pi/2 pulse maps the full remaining length onto the equator
and the measured S_z is ~0 at the posterior mean, so each read is a Ramsey read with amplitude
C^k (C the per-read coherence).

What this module provides
-------------------------
Kernel-safe (@portable) policy methods, mixed into a class that already has the Feedback
posterior state (``m``, ``omega_guess_list``, ``state_x/y/z``, ``P0``, ``max_idx``,
``sincos_lut_interp``). The same code runs in the kernel (the test experiment
kexp/experiments/HF_experiments/feedback/adaptive_ramsey/) and on the host (the simulator
kexp.analysis.adaptive_ramsey), so the simulator's policy IS the kernel's policy.

Conventions (those of Feedback.generate_posterior, nothing new):
  hypothesis j, frame rotating at omega_j; a pulse at time t with DDS phase Phi(t) (the accumulated
  drive phase, ``phase_raman_pulse_start``) has axis azimuth phi_j = Phi(t) - omega_j t and rotates
  by -dt_ideal * H about (Omega cos phi_j, Omega sin phi_j, delta_j)/H. With a programmable offset
  theta on the two-photon phase, Phi(t) = theta + omega_d t (constant drive omega_d).

  For a resonant pi/2 pulse (the detuned correction is O(delta/Omega) <= 0.05 and is ignored in the
  CHOICE only; the posterior update itself is exact) the z after the pulse is
      s'_z,j(theta) = sin(theta + psi_j) s_x,j - cos(theta + psi_j) s_y,j,   psi_j = omega_d t - omega_j t
                    = sin(theta) A_j - cos(theta) B_j,
      A_j = cos(psi_j) s_x,j + sin(psi_j) s_y,j    (the hypothesis' transverse vector, rotated
      B_j = cos(psi_j) s_y,j - sin(psi_j) s_x,j     into the drive frame at time t)
  so the posterior-expected E[s'_z](theta) = sin(theta) A - cos(theta) B with A = sum P_j A_j,
  B = sum P_j B_j, and theta* = atan2(B, A) is its zero with positive slope R = sqrt(A^2 + B^2):
  the drive axis parallel to the posterior-mean transverse vector in the drive frame. R is the
  posterior-mean transverse length -- the Ramsey amplitude the next read will see -- and is
  recorded per pulse. PHASE_MAP_PAR uses the MAP hypothesis alone (policy_sim's 'maxslope',
  which lost to production on a FIXED gap; the mean handles a bimodal posterior, the MAP does not).

  PHASE_MAXVAR / GAP_MAXVAR (the defaults) use the posterior VARIANCE of the predicted S_z,
  Var[s'_z] = w^T Sigma w with w = (sin theta, -cos theta) and Sigma the posterior covariance of
  (A_j, B_j): for a weak read with fixed Gaussian noise sigma_s the expected information gain is
  ~ 1/2 ln(1 + Var/sigma_s^2), monotone in Var, so maximizing Var over theta (the largest
  eigenvector of Sigma) and over the candidate gaps (p.ramsey_gap_candidates x the hardware floor)
  is the one-step Bayesian experimental design. It covers the two regimes in one rule: a broad,
  multimodal posterior (every gap on this machine is >= ~70 us, so the first fringe already
  wraps over the 12 kHz prior and the mean transverse length R is ~0) is told apart by the read
  that spreads its lobes most; a unimodal posterior of width sigma gives Var ~ R^2 (2 pi sigma T)^2
  until the fan wraps, so the preferred gap grows as 1/sigma -- the textbook adaptive schedule
  emerges without a tuned gap factor. Aliased hypotheses (delta and delta + 1/T) predict the same
  S_z and add nothing to Var, so an aliasing gap is never chosen for its own sake.

Sign caveat (hardware): whether RamanBeamPair.set(relative_phase=theta) enters the model as +theta
or -theta relative to omega_d t has not been checked against the posterior model (check_twist /
check_lightshift only use fringes in theta). ``ramsey_phase_sign`` carries it; a run with
PHASE_RANDOM phases decides it offline (kexp.analysis.adaptive_ramsey.phase_sign_check).
"""
from artiq.experiment import portable, TFloat, TInt64, TTuple
import numpy as np
from numpy import int64

#: phase policies (p.ramsey_phase_policy)
PHASE_NONE = 0        # theta = 0 every pulse: the phase-continuous DDS, no control (the production loop)
PHASE_MEAN_PAR = 1    # axis parallel to the posterior-MEAN transverse vector (default)
PHASE_MAP_PAR = 2     # axis parallel to the MAP hypothesis' transverse vector
PHASE_RANDOM = 3      # a host-drawn list per shot (p.ramsey_phase_list): the non-adaptive control
PHASE_MAXVAR = 4      # axis maximizing the posterior VARIANCE of the predicted S_z (default; see below)

#: gap policies (p.ramsey_gap_policy): the pulse-start-to-pulse-start period of the NEXT step
GAP_FIXED = 0         # the hardware floor every step (the production loop)
GAP_POSTERIOR = 1     # T = ramsey_gap_factor / sigma_Hz, clipped to [floor, t_ramsey_gap_max] (default)
GAP_DOUBLING = 2      # T_i = t_ramsey_gap_0 * 2**i, clipped: the non-adaptive schedule
GAP_MAXVAR = 3        # T from p.ramsey_gap_candidates x floor maximizing the predicted-S_z variance (default)

PHASE_POLICIES = {PHASE_NONE: "none", PHASE_MEAN_PAR: "mean_par", PHASE_MAP_PAR: "map_par",
                  PHASE_RANDOM: "random", PHASE_MAXVAR: "maxvar"}
GAP_POLICIES = {GAP_FIXED: "fixed", GAP_POSTERIOR: "posterior", GAP_DOUBLING: "doubling",
                GAP_MAXVAR: "maxvar"}


def adaptive_ramsey_param_defaults(p):
    """The adaptive-Ramsey parameters, set on an ExptParams only where absent (so a run file's
    recorded values win in replay, and a params class may pre-set them)."""
    defaults = dict(
        ramsey_phase_policy=PHASE_MAXVAR,
        ramsey_gap_policy=GAP_MAXVAR,
        # GAP_MAXVAR candidates: multiples of the hardware floor (the production gap formula)
        ramsey_gap_candidates=np.array([1., 2., 3., 4., 6., 8.]),
        # a longer candidate must beat the shorter one's variance by this fraction (ties -> short)
        ramsey_gap_maxvar_margin=0.05,
        # T_next = gap_factor / sigma_Hz: 0.125 puts +-2 sigma of the posterior inside the
        # monotonic half-fringe (|2 pi sigma T| <= pi/4 per sigma)
        ramsey_gap_factor=0.125,
        t_ramsey_gap_min=0.,          # 0 = the hardware floor (compute_t_between_pulses_mu)
        t_ramsey_gap_max=300.e-6,     # free-evolution cap: 300 us, the coherence time is the limit (user, 2026-10-30)
        t_ramsey_gap_0=66.e-6,        # doubling schedule base
        t_ramsey_total_max=4.0e-3,    # the shot's whole train, pulse 0 start to last read
        ramsey_pulse_area_pi=0.5,     # every pulse pi/2 (rate time; the turn-on offset is added)
        ramsey_phase_sign=1.0,        # +1: set(relative_phase=theta) is +theta in the model
        ramsey_phase_seed=0,          # PHASE_RANDOM list seed; 0 = fresh per shot
        # RamanBeamPair.set(relative_phase=...) is written this long before each pulse (replaces
        # the fast-frequency-update pretrigger in the gap formula)
        t_ramsey_phase_set_pretrigger_mu=int64(12000),
    )
    for k, v in defaults.items():
        if not hasattr(p, k):
            setattr(p, k, v)
    return p


def draw_ramsey_phase_list(seed, n_pulses):
    """The PHASE_RANDOM list: uniform in [0, 2 pi), a pure function of the seed."""
    rng = np.random.default_rng(int(seed))
    return rng.uniform(0.0, 2.0 * np.pi, size=int(n_pulses))


def wrap_phase_positive(theta):
    """theta into [0, 2 pi): RamanBeamPair.set treats a negative relative_phase as 'unchanged'."""
    x = theta % (2.0 * np.pi)
    if x < 0.0:
        x += 2.0 * np.pi
    if x >= 2.0 * np.pi:
        x -= 2.0 * np.pi
    return x


class AdaptiveRamsey:
    """Policy methods; mixed in beside kexp.base.feedback.Feedback (needs its state)."""

    @portable(flags={"fast-math"})
    def ramsey_wrap_phase(self, theta) -> TFloat:
        """theta into [0, 2 pi) for RamanBeamPair.set (a negative relative_phase means 'unchanged').
        No loops (reviewer, 2026-10-30): a non-finite or absurd theta (|theta| > 1e6 rad) gives
        0.0 rather than a spin or an undefined cast; otherwise one truncating division."""
        if theta != theta:
            return 0.0
        if theta > 1.0e6 or theta < -1.0e6:
            return 0.0
        two_pi = 2.0 * np.pi
        turns = int(theta * self.inv_two_pi)
        x = theta - two_pi * turns
        if x < 0.0:
            x += two_pi
        if x >= two_pi:
            x -= two_pi
        return x

    @portable(flags={"fast-math"})
    def ramsey_prediction_moments(self, phi_dds_next, t_next, use_map) -> TTuple([TFloat, TFloat, TFloat, TFloat, TFloat]):
        """Posterior moments of the transverse vector (A_j, B_j) in the drive frame at the next
        pulse: (A, B, Saa, Sab, Sbb) = means and central second moments (use_map = 1: the MAP
        hypothesis alone, second moments 0)."""
        A = 0.0
        B = 0.0
        AA = 0.0
        AB = 0.0
        BB = 0.0
        if use_map:
            j = self.max_idx
            psi = phi_dds_next - self.omega_guess_list[j] * t_next
            (s, c) = self.sincos_lut_interp(psi)
            A = c * self.state_x[j] + s * self.state_y[j]
            B = c * self.state_y[j] - s * self.state_x[j]
            return A, B, 0.0, 0.0, 0.0
        j = 0
        while j < self.m:
            psi = phi_dds_next - self.omega_guess_list[j] * t_next
            (s, c) = self.sincos_lut_interp(psi)
            pj = self.P0[j]
            a = c * self.state_x[j] + s * self.state_y[j]
            b = c * self.state_y[j] - s * self.state_x[j]
            A += pj * a
            B += pj * b
            AA += pj * a * a
            AB += pj * a * b
            BB += pj * b * b
            j += 1
        return A, B, AA - A * A, AB - A * B, BB - B * B

    @portable(flags={"fast-math"})
    def ramsey_maxvar_phase(self, Saa, Sab, Sbb) -> TTuple([TFloat, TFloat]):
        """(theta, lambda): the phase maximizing Var[s'_z] = w^T Sigma w over w = (sin theta,
        -cos theta), and that maximum (the largest eigenvalue of Sigma)."""
        tr = Saa + Sbb
        det = Saa * Sbb - Sab * Sab
        disc = 0.25 * tr * tr - det
        if disc < 0.0:
            disc = 0.0
        lam = 0.5 * tr + np.sqrt(disc)
        # eigenvector of lam: (Sab, lam - Saa) or (lam - Sbb, Sab), the longer one
        w0 = Sab
        w1 = lam - Saa
        v0 = lam - Sbb
        v1 = Sab
        if v0 * v0 + v1 * v1 > w0 * w0 + w1 * w1:
            w0 = v0
            w1 = v1
        if w0 * w0 + w1 * w1 < 1.0e-24:
            return 0.0, lam
        return np.arctan2(w0, -w1), lam

    @portable(flags={"fast-math"})
    def ramsey_choose_phase(self, phi_dds_next, t_next, policy, i_next) -> TTuple([TFloat, TFloat]):
        """(theta, Q) for pulse i_next: the two-photon phase offset in the MODEL convention and the
        quality the policy maximized (PHASE_MEAN_PAR/MAP_PAR: R = the expected Ramsey amplitude;
        PHASE_MAXVAR: Var[s'_z]; 0 where undefined). phi_dds_next = the drive's accumulated phase
        at t_next (rad)."""
        if policy == PHASE_NONE:
            return 0.0, 0.0
        if policy == PHASE_RANDOM:
            # the plan after the last pulse is recorded, not taken: clamp to the list
            idx = i_next
            if idx >= len(self.p.ramsey_phase_list):
                idx = len(self.p.ramsey_phase_list) - 1
            return self.p.ramsey_phase_list[idx], 0.0
        use_map = 0
        if policy == PHASE_MAP_PAR:
            use_map = 1
        (A, B, Saa, Sab, Sbb) = self.ramsey_prediction_moments(phi_dds_next, t_next, use_map)
        if policy == PHASE_MAXVAR:
            return self.ramsey_maxvar_phase(Saa, Sab, Sbb)
        R = np.sqrt(A * A + B * B)
        if R < 1.0e-12:
            return 0.0, 0.0
        return np.arctan2(B, A), R

    @portable(flags={"fast-math"})
    def ramsey_clip_gap_mu(self, t_gap, t_floor_mu, t_elapsed) -> TInt64:
        """t_gap (s) into mu: 8-aligned, within [max(floor, p.t_ramsey_gap_min), p.t_ramsey_gap_max]
        and cut so the train ends by p.t_ramsey_total_max (t_elapsed = the pulse just taken, s)."""
        if t_gap != t_gap:
            # NaN compares false with everything below and its cast is undefined: the floor
            t_gap = 0.0
        if t_gap < self.p.t_ramsey_gap_min:
            t_gap = self.p.t_ramsey_gap_min
        if t_gap > self.p.t_ramsey_gap_max:
            t_gap = self.p.t_ramsey_gap_max
        t_left = self.p.t_ramsey_total_max - t_elapsed
        if t_gap > t_left:
            t_gap = t_left
        if t_gap < 0.0:
            t_gap = 0.0
        t_gap_mu = int64(t_gap * 1.0e9) & ~7
        if t_gap_mu < t_floor_mu:
            t_gap_mu = t_floor_mu
        return t_gap_mu

    @portable(flags={"fast-math"})
    def ramsey_plan_next(self, i_next, t_now, phi_dds_now, omega_d, omega_d_next, t_pre,
                         t_floor_mu) -> TTuple([TInt64, TFloat, TFloat]):
        """The next step from the posterior: (dT_mu, theta, Q) = the pulse-start period before
        pulse i_next (mu), its phase offset (model convention) and the quality the choice
        maximized. phi_dds_now = the drive's accumulated phase at t_now; the DDS runs at omega_d
        until t_pre before the next pulse and at omega_d_next after (production's pretrigger;
        equal without a hop). i_next >= 1."""
        gap_policy = self.p.ramsey_gap_policy
        phase_policy = self.p.ramsey_phase_policy
        if gap_policy == GAP_MAXVAR:
            best_mu = t_floor_mu
            best_q = -1.0
            best_theta = 0.0
            k = 0
            while k < len(self.p.ramsey_gap_candidates):
                t_gap_mu = self.ramsey_clip_gap_mu(
                    self.p.ramsey_gap_candidates[k] * float(t_floor_mu) * 1.0e-9, t_floor_mu, t_now)
                if k == 0 or t_gap_mu != best_mu:
                    dT = float(t_gap_mu) * 1.0e-9
                    t_next = t_now + dT
                    phi_next = phi_dds_now + omega_d * (dT - t_pre) + omega_d_next * t_pre
                    (theta, q) = self.ramsey_choose_phase(phi_next, t_next, phase_policy, i_next)
                    if phase_policy != PHASE_MAXVAR:
                        # the gap still by the variance criterion; the phase by its own rule
                        (A, B, Saa, Sab, Sbb) = self.ramsey_prediction_moments(phi_next, t_next, 0)
                        (theta_v, q) = self.ramsey_maxvar_phase(Saa, Sab, Sbb)
                    if k == 0 or q > best_q * (1.0 + self.p.ramsey_gap_maxvar_margin):
                        best_q = q
                        best_mu = t_gap_mu
                        best_theta = theta
                k += 1
            return best_mu, best_theta, best_q
        t_gap = 0.0
        if gap_policy == GAP_POSTERIOR:
            sigma_hz = self._posterior_std / (2.0 * np.pi)
            if sigma_hz > 1.0e-3:
                t_gap = self.p.ramsey_gap_factor / sigma_hz
            else:
                t_gap = self.p.t_ramsey_gap_max
        elif gap_policy == GAP_DOUBLING:
            t_gap = self.p.t_ramsey_gap_0
            k = 0
            while k < i_next - 1:
                t_gap = t_gap * 2.0
                k += 1
        dT_mu = self.ramsey_clip_gap_mu(t_gap, t_floor_mu, t_now)
        dT = float(dT_mu) * 1.0e-9
        phi_next = phi_dds_now + omega_d * (dT - t_pre) + omega_d_next * t_pre
        (theta, q) = self.ramsey_choose_phase(phi_next, t_now + dT, phase_policy, i_next)
        return dT_mu, theta, q
