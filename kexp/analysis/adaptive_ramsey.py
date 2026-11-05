"""Adaptive Ramsey -- host simulator, replay and scoring (2026-10-30, DESIGN STAGE).

Companion of kexp.base.adaptive_ramsey (the policies, kernel-safe) and of the test experiment
kexp/experiments/HF_experiments/feedback/adaptive_ramsey/. Built on the feedback posterior
framework exactly as FeedbackReplay.simulate_feedback_run_apd is: the controller is the kernel's
own Feedback.generate_posterior (the @portable code, run on the host), the true spin is stepped
by the same Bloch rotation / imaging-light-shift z rotation / state-dependent read model as the
posterior assumes, photons are Gaussian at std_n_photons_per_shot, and the injected truth is
known -- so a protocol is scored against a truth that is deliberately not the calibration label.

    python -m kexp.analysis.adaptive_ramsey --shots 60 --seeds 3 --out <folder>

compares the policies in DEFAULT_POLICIES (production-like fixed gap + no phase control; fixed gap
+ adaptive phase; posterior-driven gap + adaptive phase; the doubling schedule + adaptive phase;
random phases as the non-adaptive control) on the shipped feedback calibration, and writes a JSON
table and figures. Everything is model physics: no free-evolution dephasing and no shot-to-shot
field jitter unless a TruthModel asks for them, and the read model is the one that fails the
hardware simulation checks (chi2/n ~33 on-resonance, 2026-10-29). Numbers are UPPER BOUNDS on
what the hardware can do, and differences between policies are what the study is for.

Replay of a real run (the test experiment records t_gap, phase and drive per pulse):

    rep = replay_posterior(run_arrays_from_atomdata(ad), grid_size=161, phase_sign=+1)
    rep = replay_posterior(..., phase_sign=-1)          # the hardware phase-sign check
    phase_sign_check(run_arrays_from_atomdata(ad))      # log-evidence under both signs
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Sequence

import numpy as np

from kexp.base.feedback import Feedback, map_estimate
from kexp.base.adaptive_ramsey import (
    AdaptiveRamsey, adaptive_ramsey_param_defaults, draw_ramsey_phase_list,
    PHASE_NONE, PHASE_MEAN_PAR, PHASE_MAP_PAR, PHASE_RANDOM, PHASE_MAXVAR,
    GAP_FIXED, GAP_POSTERIOR, GAP_DOUBLING, GAP_MAXVAR, PHASE_POLICIES, GAP_POLICIES)

#: the slack the kernel needs per step: the posterior update (fast-path bench 2026-09-29: ~0.7 us
#: per grid point), the plan step (one sincos + ~10 flops per grid point per gap candidate, ~0.35 us
#: a guess), the fixed part of expt_params_feedback's formula and RamanBeamPair.set(relative_phase)
#: per pulse (two DDS register writes). GUESSES until the test experiment measures them
#: (AdaptiveRamseyExpt.initialize_feedback times both and records data.ramsey_timing); the floor
#: they set is what limits the first fringe, so the simulator takes them as parameters.
T_SLACK_PER_POINT_S = 0.7e-6
T_PLAN_PER_POINT_PER_CANDIDATE_S = 0.35e-6
T_SLACK_FIXED_S = 25.0e-6
T_SET_PHASE_EXTRA_S = 10.0e-6


@dataclass
class RamseyPolicy:
    """What the kernel would do; every field maps to a p.ramsey_* parameter."""
    name: str
    phase_policy: int = PHASE_MEAN_PAR
    gap_policy: int = GAP_POSTERIOR
    gap_factor: float = 0.125
    t_gap_min: float = 0.0
    t_gap_max: float = 300.0e-6     # user 2026-10-30: coherence-time cap
    t_gap_0: float = 66.0e-6
    t_total_max: float = 4.0e-3
    pulse_area_pi: float = 0.5
    random_pulse_times: bool = False    # production's uniform 0.5..1 t_pi durations instead
    drive_hop: bool = False             # production's drive = MAP after every pulse
    gap_candidates: tuple = (1., 2., 3., 4., 6., 8.)   # GAP_MAXVAR: multiples of the floor
    gap_maxvar_margin: float = 0.05

    def apply(self, p):
        p.ramsey_phase_policy = int(self.phase_policy)
        p.ramsey_gap_policy = int(self.gap_policy)
        p.ramsey_gap_candidates = np.asarray(self.gap_candidates, float)
        p.ramsey_gap_maxvar_margin = float(self.gap_maxvar_margin)
        p.ramsey_gap_factor = float(self.gap_factor)
        p.t_ramsey_gap_min = float(self.t_gap_min)
        p.t_ramsey_gap_max = float(self.t_gap_max)
        p.t_ramsey_gap_0 = float(self.t_gap_0)
        p.t_ramsey_total_max = float(self.t_total_max)
        p.ramsey_pulse_area_pi = float(self.pulse_area_pi)
        p.t_raman_pulse_random_bool = int(self.random_pulse_times)
        p.update_raman_frequency_bool = int(self.drive_hop)

    def describe(self):
        return (f"{self.name}: phase {PHASE_POLICIES[self.phase_policy]}, gap "
                f"{GAP_POLICIES[self.gap_policy]}"
                + (f" (factor {self.gap_factor:g})" if self.gap_policy == GAP_POSTERIOR else "")
                + (f" (x{', '.join(f'{c:g}' for c in self.gap_candidates)} floor)" if self.gap_policy == GAP_MAXVAR else "")
                + (f" (T0 {self.t_gap_0 * 1e6:.0f} us)" if self.gap_policy == GAP_DOUBLING else "")
                + f", area {self.pulse_area_pi:g} pi"
                + (", random durations" if self.random_pulse_times else "")
                + (", drive hops" if self.drive_hop else ""))


DEFAULT_POLICIES: List[RamseyPolicy] = [
    RamseyPolicy("production", PHASE_NONE, GAP_FIXED, random_pulse_times=True, drive_hop=True),
    RamseyPolicy("production_nohop", PHASE_NONE, GAP_FIXED, random_pulse_times=True),
    RamseyPolicy("fixed_gap_pi2", PHASE_NONE, GAP_FIXED),
    RamseyPolicy("fixed_gap_meanpar", PHASE_MEAN_PAR, GAP_FIXED),
    RamseyPolicy("fixed_gap_maxvar", PHASE_MAXVAR, GAP_FIXED),
    RamseyPolicy("doubling_maxvar", PHASE_MAXVAR, GAP_DOUBLING),
    RamseyPolicy("maxvar_gap_random_phase", PHASE_RANDOM, GAP_MAXVAR),
    RamseyPolicy("adaptive_maxvar", PHASE_MAXVAR, GAP_MAXVAR),
    RamseyPolicy("adaptive_maxvar_hop", PHASE_MAXVAR, GAP_MAXVAR, drive_hop=True),
    RamseyPolicy("adaptive_meanpar_stdgap", PHASE_MEAN_PAR, GAP_POSTERIOR),
]


@dataclass
class TruthModel:
    """Perturbations of the TRUE spin only (the posterior keeps its own calibration). All off =
    the posterior's model is the truth, as in simulate_feedback_run_apd."""
    coherence: Optional[float] = None       # per-read coherence of the truth (None: the model's)
    twist_per_sz: Optional[float] = None    # read twist of the truth (None: the model's)
    t2_star: Optional[float] = None         # Gaussian free-evolution dephasing exp(-(t/T2*)^2)
    f_jitter_hz: float = 0.0                # per-shot resonance scatter (Gaussian, Hz)
    noise_scale: float = 1.0                # multiplies std_n_photons_per_shot for the draw


@dataclass
class RunArrays:
    """What the kernel records per shot and pulse (and what the simulator produces): enough to
    replay the posterior on any grid. Shapes (n_shot, n_pulse) unless noted."""
    apd: np.ndarray                 # integrator volts
    t_pulse_start: np.ndarray       # s from the shot's pulse 0
    t_raman_pulse: np.ndarray       # programmed durations, s
    phase: np.ndarray               # theta per pulse, MODEL convention (rad)
    omega_drive: np.ndarray         # rad/s per pulse
    offset_u: np.ndarray            # (n_shot,) feedback_fractional_initial_offset per shot
    params: object                  # the ExptParams the posterior ran with
    f_true: Optional[np.ndarray] = None    # (n_shot,) injected truth, Hz (simulation only)
    s_z_true: Optional[np.ndarray] = None
    R: Optional[np.ndarray] = None         # expected Ramsey amplitude chosen per pulse

    @property
    def n_shot(self):
        return int(self.apd.shape[0])

    @property
    def n_pulse(self):
        return int(self.apd.shape[1])


@dataclass
class PosteriorTrace:
    """A posterior run over RunArrays: P after every pulse (row 0 = prior)."""
    grid_hz: np.ndarray             # (n_shot, m)
    P: np.ndarray                   # (n_shot, n_pulse + 1, m)
    log_evidence: np.ndarray        # (n_shot,) sum over pulses of log of the normaliser
    f_map: np.ndarray
    f_mean: np.ndarray
    f_std: np.ndarray

    def errors(self, f_true):
        f_true = np.asarray(f_true, float)
        return self.f_map - f_true, self.f_mean - f_true


def slack_estimate_s(m, n_candidates):
    """The kernel slack guess for grid size m and n gap candidates (see the constants above)."""
    return (T_SLACK_PER_POINT_S * m + T_PLAN_PER_POINT_PER_CANDIDATE_S * m * max(int(n_candidates), 1)
            + T_SLACK_FIXED_S + T_SET_PHASE_EXTRA_S)


def _slack_s(p, m):
    n_cand = len(np.ravel(getattr(p, "ramsey_gap_candidates", [1.]))) if int(
        getattr(p, "ramsey_gap_policy", GAP_MAXVAR)) == GAP_MAXVAR else 1
    return slack_estimate_s(m, n_cand)


def make_params(grid_size=41, full_span_hz=12.0e3, n_pulses=12, policy: Optional[RamseyPolicy] = None,
                base_params=None, **overrides):
    """An ExptParams for the simulator: the shipped feedback calibration (expt_params_feedback),
    the adaptive-Ramsey defaults, the hypothesis grid (convention 2) and the policy."""
    if base_params is None:
        from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams
        p = ExptParams()
    else:
        p = copy.deepcopy(base_params)
    adaptive_ramsey_param_defaults(p)
    p.feedback_grid_convention = 2
    p.feedback_grid_size = int(grid_size)
    p.frequency_feedback_grid_full_span = float(full_span_hz)
    p.feedback_fractional_initial_offset = 0.0
    p.feedback_grid_shift = 0.0
    p.feedback_remesh_threshold_Omega = 0.0
    p.N_pulses = int(n_pulses)
    p.preshot_contrast = 0
    p.feedback_initial_sz = 1.0
    p.feedback_read_model = -1.0
    if policy is not None:
        policy.apply(p)
    for k, v in overrides.items():
        setattr(p, k, v)
    p.t_raman_pulse = float(p.ramsey_pulse_area_pi) * float(p.t_raman_pi_pulse) + float(p.t_raman_pulse_offset)
    p.t_raman_pulse_ideal = p.t_raman_pulse - float(p.t_raman_pulse_offset)
    if "t_calculation_slack_compensation_mu" not in overrides:
        p.t_calculation_slack_compensation_mu = np.int64(_slack_s(p, grid_size) * 1e9)
    p.compute_feedback_grid()
    return p


class RamseyPosterior(Feedback, AdaptiveRamsey):
    """The kernel's posterior + policies, instantiated on the host from an ExptParams."""

    def __init__(self, p):
        self.p = p
        if not hasattr(self.p, "ramsey_phase_list"):
            self.p.ramsey_phase_list = np.zeros(int(p.N_pulses))
        Feedback.__init__(self, expt_params=p)

    # -- per-shot set-up ------------------------------------------------------------------------
    def start_shot(self, offset_u, phase_list=None):
        """Grid centred on the drive at fractional offset u, every hypothesis at the pole, the drive
        at omega_res + Omega * offset; returns the drive (rad/s)."""
        self.p.feedback_fractional_initial_offset = float(offset_u)
        self.p.compute_feedback_grid()
        self._initialize_frequency_grid()
        self.reset_feedback_state()
        self._flat_prob_counter = 0
        self.omega_z_lightshift = 2.0 * np.pi * float(self.p.frequency_lightshift)
        if phase_list is not None:
            self.p.ramsey_phase_list = np.asarray(phase_list, float)
        return float(self.omega_raman)

    def hardware_floor_mu(self, t_raman_pulse):
        """The production gap formula with the phase-set pretrigger in place of the
        fast-frequency-update one (as AdaptiveRamseyExpt.feedback_loop)."""
        pre = getattr(self.p, "t_ramsey_phase_set_pretrigger_mu", self.p.t_raman_set_pretrigger_mu)
        return int(self.compute_t_between_pulses_mu(
            np.int64(self.p.t_calculation_slack_compensation_mu), float(t_raman_pulse),
            float(self.p.t_img_pulse), np.int64(pre), np.int64(self.p.t_fifo_mu)))

    def pulse_duration(self, i, rng):
        if int(getattr(self.p, "t_raman_pulse_random_bool", 0)):
            lo = float(self.p.t_raman_pulse_min_frac_pi) * float(self.p.t_raman_pi_pulse)
            hi = float(self.p.t_raman_pulse_max_frac_pi) * float(self.p.t_raman_pi_pulse)
            return float(np.rint(rng.uniform(lo, hi) * 1e9) * 1e-9)
        return float(self.p.ramsey_pulse_area_pi) * float(self.p.t_raman_pi_pulse) + float(
            self.p.t_raman_pulse_offset)

    def grid_hz(self):
        return np.asarray(self.omega_guess_list[:self.m], float) / (2.0 * np.pi)


def _true_step(fb: RamseyPosterior, s, omega_true, omega_d, phase, t, dt_eff, dt_ideal, truth: TruthModel):
    """One pulse + read on the true Bloch vector s (the physics of simulate_feedback_run_apd;
    exact trig, truth-side read-model values). Returns (hz_seen_by_the_APD, s_after_read)."""
    sx, sy, sz = s
    Omega = float(fb.Omega)
    delta = omega_d - omega_true
    H = np.sqrt(Omega * Omega + delta * delta)
    if H > 0.0:
        Oh, uz = Omega / H, delta / H
        th = -dt_ideal * H
        sin_H, cos_H = np.sin(th), np.cos(th)
    else:
        Oh, uz, sin_H, cos_H = 0.0, 0.0, 0.0, 1.0
    phi = phase - omega_true * t
    ux, uy = Oh * np.cos(phi), Oh * np.sin(phi)
    omc = 1.0 - cos_H
    hx = (cos_H + omc * ux * ux) * sx + (omc * ux * uy - sin_H * uz) * sy + (omc * ux * uz + sin_H * uy) * sz
    hy = (omc * ux * uy + sin_H * uz) * sx + (cos_H + omc * uy * uy) * sy + (omc * uy * uz - sin_H * ux) * sz
    hz = (omc * ux * uz - sin_H * uy) * sx + (omc * uy * uz + sin_H * ux) * sy + (cos_H + omc * uz * uz) * sz
    # the read: z rotation (pulse detuning phase + light shift), twist, coherence loss
    alpha_z = dt_eff * (omega_true - omega_d) - fb.omega_z_lightshift * float(fb.p.t_img_pulse)
    if fb.read_alpha_lightshift_on:
        alpha_z = dt_eff * (omega_true - omega_d) - fb.read_alpha_lightshift
    twist = fb.read_twist if truth.twist_per_sz is None else float(truth.twist_per_sz)
    if twist != 0.0:
        alpha_z = alpha_z + twist * hz
    coherence = fb.back_action_coherence if truth.coherence is None else float(truth.coherence)
    if fb.read_coherence_slope_on:
        coherence = float(np.clip(coherence + fb.read_coherence_slope * hz, 0.0, 1.0))
    cz, sz_ = np.cos(alpha_z), np.sin(alpha_z)
    nx = (cz * hx + sz_ * hy) * coherence
    ny = (-sz_ * hx + cz * hy) * coherence
    return hz, (nx, ny, hz)


class AdaptiveRamseySimulator:
    """Closed-loop simulation of the adaptive Ramsey shot on the kernel's own posterior.

    >>> sim = AdaptiveRamseySimulator(make_params(policy=RamseyPolicy("adaptive")))
    >>> arrays = sim.run(n_shots=30, truth_offset_hz=777., seed=1)
    >>> trace = replay_posterior(arrays)            # the controller's grid
    >>> summarize(trace, arrays.f_true)
    """

    def __init__(self, params, truth: Optional[TruthModel] = None):
        self.p = params
        self.truth = truth or TruthModel()
        self.fb = RamseyPosterior(self.p)

    def run(self, n_shots, truth_offset_hz=0.0, seed=0, offsets_u=None) -> RunArrays:
        """n_shots shots; the true resonance = p.frequency_raman_transition + truth_offset_hz
        (scalar or per shot) + jitter; offsets_u = the drive's fractional initial offset per shot
        (default 0: drive on the nominal resonance)."""
        fb, p, truth = self.fb, self.p, self.truth
        rng = np.random.default_rng(int(seed))
        n_pulse = int(p.N_pulses)
        offs = np.zeros(n_shots) if offsets_u is None else np.resize(np.asarray(offsets_u, float), n_shots)
        f_off = np.resize(np.asarray(truth_offset_hz, float), n_shots)
        f_res = float(p.frequency_raman_transition)
        n_ph = float(fb.N_photons_per_shot)
        sig_ph = float(fb.std_n_photons_per_shot) * float(truth.noise_scale)
        v_down, v_range = float(fb.v_apd_all_down), float(fb.v_range)
        sign = float(p.ramsey_phase_sign)
        hop = bool(int(p.update_raman_frequency_bool))
        T_pre = float(p.t_io_update_pretrigger_mu) * 1e-9

        A = {k: np.zeros((n_shots, n_pulse)) for k in
             ("apd", "t_pulse_start", "t_raman_pulse", "phase", "omega_drive", "s_z_true", "R")}
        f_true = np.zeros(n_shots)
        for r in range(n_shots):
            phase_list = draw_ramsey_phase_list(rng.integers(1, 2 ** 31), n_pulse)
            omega_d = fb.start_shot(offs[r], phase_list=phase_list)
            f_true[r] = f_res + f_off[r] + (rng.normal(0.0, truth.f_jitter_hz) if truth.f_jitter_hz > 0 else 0.0)
            omega_true = 2.0 * np.pi * f_true[r]
            s = (0.0, 0.0, float(fb.initial_sz))
            t = 0.0
            Phi = 0.0                       # the drive's accumulated phase at t (no offset)
            theta = float(phase_list[0]) if p.ramsey_phase_policy == PHASE_RANDOM else 0.0
            R = 0.0
            for i in range(n_pulse):
                dt_eff = fb.pulse_duration(i, rng)
                dt_ideal = dt_eff - float(p.t_raman_pulse_offset)
                phase = sign * theta + Phi
                fb.omega_raman = omega_d
                fb.t_raman_pulse_current = dt_eff
                fb.t_raman_pulse_ideal_current = dt_ideal
                hz, s_after = _true_step(fb, s, omega_true, omega_d, phase, t, dt_eff, dt_ideal, truth)
                p1 = float(fb.expected_photon_fraction(hz))
                k = n_ph * p1 + (rng.normal(0.0, sig_ph) if sig_ph > 0 else 0.0)
                v = v_down + k * v_range / n_ph
                A["apd"][r, i], A["t_pulse_start"][r, i], A["t_raman_pulse"][r, i] = v, t, dt_eff
                A["phase"][r, i], A["omega_drive"][r, i], A["s_z_true"][r, i], A["R"][r, i] = theta, omega_d, hz, R
                k_val = float(np.rint(n_ph * (v - v_down) / v_range))
                omega_new, _, _ = fb.generate_posterior(
                    k_val, t, phase_raman_pulse_start=phase, update_raman_frequency=1 if hop else 0,
                    update_rabi_frequency=0, include_photon_noise=1)
                # next step: gap and phase from the posterior (the kernel's own plan function)
                floor_mu = fb.hardware_floor_mu(dt_eff)
                omega_d_next = float(omega_new) if hop else omega_d
                dT_mu, theta, R = fb.ramsey_plan_next(i + 1, t, Phi, omega_d, omega_d_next, T_pre,
                                                      np.int64(floor_mu))
                dT = int(dT_mu) * 1e-9
                t_next = t + dT
                Phi_next = Phi + omega_d * (dT - T_pre) + omega_d_next * T_pre
                theta, R = float(theta), float(R)
                # free evolution of the truth over the gap (the model has none; T2* is a truth knob)
                nx, ny, nz = s_after
                if truth.t2_star:
                    fac = np.exp(-(t_next ** 2 - t ** 2) / float(truth.t2_star) ** 2)
                    nx, ny = nx * fac, ny * fac
                s = (nx, ny, nz)
                t, Phi, omega_d = t_next, Phi_next, omega_d_next
        return RunArrays(apd=A["apd"], t_pulse_start=A["t_pulse_start"], t_raman_pulse=A["t_raman_pulse"],
                         phase=A["phase"], omega_drive=A["omega_drive"], offset_u=offs,
                         params=copy.deepcopy(p), f_true=f_true, s_z_true=A["s_z_true"], R=A["R"])


# ---------------------------------------------------------------------------------------------
# replay / scoring
# ---------------------------------------------------------------------------------------------

def replay_posterior(arrays: RunArrays, grid_size=None, full_span_hz=None, phase_sign=None,
                     params=None) -> PosteriorTrace:
    """Run the posterior over recorded (or simulated) data: a grid of grid_size points over
    full_span_hz (defaults: the run's), phases entering as phase_sign * theta (default: the run's
    ramsey_phase_sign). On the run's own grid and sign this reproduces the kernel's posterior;
    a finer grid scores the estimate without the grid floor (policy_sim's 'fine MAP')."""
    p = copy.deepcopy(params if params is not None else arrays.params)
    adaptive_ramsey_param_defaults(p)
    if grid_size is not None:
        p.feedback_grid_size = int(grid_size)
    if full_span_hz is not None:
        p.frequency_feedback_grid_full_span = float(full_span_hz)
    p.compute_feedback_grid()
    sign = float(p.ramsey_phase_sign if phase_sign is None else phase_sign)
    fb = RamseyPosterior(p)
    n_shot, n_pulse = arrays.n_shot, arrays.n_pulse
    n_ph, v_down, v_range = float(fb.N_photons_per_shot), float(fb.v_apd_all_down), float(fb.v_range)
    m = fb.m
    P = np.zeros((n_shot, n_pulse + 1, m))
    G = np.zeros((n_shot, m))
    logZ = np.zeros(n_shot)
    for r in range(n_shot):
        fb.start_shot(float(arrays.offset_u[r]))
        G[r] = fb.grid_hz()
        P[r, 0] = fb.P0[:m]
        Phi = 0.0
        t_prev = 0.0
        omega_prev = float(arrays.omega_drive[r, 0])
        T_pre = float(p.t_io_update_pretrigger_mu) * 1e-9
        for i in range(n_pulse):
            t = float(arrays.t_pulse_start[r, i])
            omega_d = float(arrays.omega_drive[r, i])
            if i > 0:
                Phi += omega_prev * (t - t_prev - T_pre) + omega_d * T_pre
            dt_eff = float(arrays.t_raman_pulse[r, i])
            fb.omega_raman = omega_d
            fb.t_raman_pulse_current = dt_eff
            fb.t_raman_pulse_ideal_current = dt_eff - float(p.t_raman_pulse_offset)
            k_val = float(np.rint(n_ph * (float(arrays.apd[r, i]) - v_down) / v_range))
            fb.generate_posterior(k_val, t, phase_raman_pulse_start=sign * float(arrays.phase[r, i]) + Phi,
                                  update_raman_frequency=0, update_rabi_frequency=0, include_photon_noise=1)
            logZ[r] += np.log(max(float(fb.P0_total), 1e-300))
            P[r, i + 1] = fb.P0[:m]
            t_prev, omega_prev = t, omega_d
    Pf = P[:, -1, :]
    f_map = map_estimate(Pf, G)
    f_mean = (Pf * G).sum(1)
    f_std = np.sqrt(np.maximum((Pf * (G - f_mean[:, None]) ** 2).sum(1), 0.0))
    return PosteriorTrace(grid_hz=G, P=P, log_evidence=logZ, f_map=f_map, f_mean=f_mean, f_std=f_std)


def posterior_std_per_pulse(trace: PosteriorTrace):
    """(n_shot, n_pulse + 1) posterior std in Hz after each pulse."""
    G = trace.grid_hz[:, None, :]
    mean = (trace.P * G).sum(-1, keepdims=True)
    return np.sqrt(np.maximum((trace.P * (G - mean) ** 2).sum(-1), 0.0))


def _bootstrap(values, stat, rng, n=400):
    values = np.asarray(values, float)
    if values.size < 2:
        return float("nan")
    idx = rng.integers(0, values.size, size=(n, values.size))
    return float(np.std([stat(values[i]) for i in idx], ddof=1))


def summarize(trace: PosteriorTrace, f_true, arrays: Optional[RunArrays] = None, seed=0) -> Dict[str, float]:
    """Scores vs the injected truth (Hz): median |err| of MAP and mean, P(|err| < 1 / 2 kHz) with
    bootstrap SE, median posterior std, coverage (|err_mean| <= 2 std), the mean train time and
    the mean expected Ramsey amplitude R at the last pulse."""
    rng = np.random.default_rng(seed)
    e_map, e_mean = trace.errors(f_true)
    a_map, a_mean = np.abs(e_map), np.abs(e_mean)
    out = dict(
        n_shots=int(e_map.size),
        median_abs_err_map_hz=float(np.median(a_map)),
        median_abs_err_map_se=_bootstrap(a_map, np.median, rng),
        median_abs_err_mean_hz=float(np.median(a_mean)),
        p_err_lt_1khz=float(np.mean(a_mean < 1e3)),
        p_err_lt_1khz_se=float(np.sqrt(np.mean(a_mean < 1e3) * (1 - np.mean(a_mean < 1e3)) / max(a_mean.size, 1))),
        p_err_lt_2khz=float(np.mean(a_mean < 2e3)),
        signed_mean_err_hz=float(np.mean(e_mean)),
        signed_mean_err_se=float(np.std(e_mean, ddof=1) / np.sqrt(e_mean.size)) if e_mean.size > 1 else float("nan"),
        median_posterior_std_hz=float(np.median(trace.f_std)),
        coverage_2sigma=float(np.mean(a_mean <= 2.0 * trace.f_std)),
    )
    if arrays is not None:
        t_end = arrays.t_pulse_start[:, -1] + arrays.t_raman_pulse[:, -1] + float(arrays.params.t_img_pulse)
        out["mean_train_time_s"] = float(np.mean(t_end))
        if arrays.R is not None:
            out["mean_R_last"] = float(np.mean(arrays.R[:, -1]))
    return out


def phase_sign_check(arrays: RunArrays, grid_size=None) -> Dict[str, float]:
    """Which sign of the programmed phase the data support: total log evidence of the posterior
    under +theta and -theta. Meaningful on PHASE_RANDOM (or any non-degenerate) phases; a run with
    theta = 0 everywhere cannot tell. Report the difference, never only the winner."""
    plus = replay_posterior(arrays, grid_size=grid_size, phase_sign=+1.0)
    minus = replay_posterior(arrays, grid_size=grid_size, phase_sign=-1.0)
    d = plus.log_evidence - minus.log_evidence
    return dict(log_evidence_plus=float(plus.log_evidence.sum()),
                log_evidence_minus=float(minus.log_evidence.sum()),
                delta_total=float(d.sum()),
                delta_per_shot_mean=float(d.mean()),
                delta_per_shot_se=float(d.std(ddof=1) / np.sqrt(d.size)) if d.size > 1 else float("nan"),
                n_shots=int(d.size),
                preferred=("+" if d.sum() > 0 else "-"),
                degenerate=bool(np.allclose(arrays.phase, 0.0)))


def run_arrays_from_atomdata(ad) -> RunArrays:
    """The test experiment's recorded containers (data.apd, data.ramsey_t_gap, data.ramsey_phase,
    data.omega_raman, data.t_raman_pulse) as RunArrays; offsets from the run's params/xvars."""
    n_pulse = int(np.ravel(ad.p.N_pulses)[0])
    apd = np.asarray(ad.data.apd, float).reshape(-1, n_pulse)
    gaps = np.asarray(ad.data.ramsey_t_gap, float).reshape(-1, n_pulse)
    t_start = np.concatenate([np.zeros((apd.shape[0], 1)), np.cumsum(gaps[:, :-1], axis=1)], axis=1)
    u = np.ravel(np.asarray(ad.p.feedback_fractional_initial_offset, float))
    u = np.resize(u, apd.shape[0]) if u.size != apd.shape[0] else u
    return RunArrays(apd=apd, t_pulse_start=t_start,
                     t_raman_pulse=np.asarray(ad.data.t_raman_pulse, float).reshape(-1, n_pulse),
                     phase=np.asarray(ad.data.ramsey_phase, float).reshape(-1, n_pulse),
                     omega_drive=np.asarray(ad.data.omega_raman, float).reshape(-1, n_pulse),
                     offset_u=u, params=copy.deepcopy(ad.p),
                     R=np.asarray(ad.data.ramsey_R, float).reshape(-1, n_pulse) if hasattr(ad.data, "ramsey_R") else None)


# ---------------------------------------------------------------------------------------------
# policy comparison
# ---------------------------------------------------------------------------------------------

def compare_policies(policies: Sequence[RamseyPolicy], n_shots=40, seeds=(1, 2, 3), truth_offsets_hz=(0.0,),
                     offsets_u=(0.0,), grid_size=41, full_span_hz=12.0e3, n_pulses=12, score_grid_size=241,
                     truth: Optional[TruthModel] = None, base_params=None, verbose=True):
    """Every policy on the same seeds / truth offsets / drive offsets. Scores on the controller's
    grid and on a fine score grid (the same data replayed). Returns {policy: {...}} and keeps the
    per-pulse posterior widths for plotting."""
    results = {}
    for pol in policies:
        p = make_params(grid_size, full_span_hz, n_pulses, pol, base_params=base_params)
        sim = AdaptiveRamseySimulator(p, truth)
        arrays_all, traces, fine = [], [], []
        for s in seeds:
            for f_off in truth_offsets_hz:
                for u in offsets_u:
                    arr = sim.run(n_shots, truth_offset_hz=f_off, seed=int(s) * 1000 + int(abs(f_off)) % 1000, offsets_u=u)
                    arrays_all.append(arr)
                    traces.append(replay_posterior(arr))
                    fine.append(replay_posterior(arr, grid_size=score_grid_size))
        arr = _concat_arrays(arrays_all)
        tr, fn = _concat_traces(traces), _concat_traces(fine)
        res = dict(policy=pol.describe(), controller_grid=summarize(tr, arr.f_true, arr),
                   fine_grid=summarize(fn, arr.f_true, arr), grid_size=grid_size, score_grid_size=score_grid_size)
        res["_std_per_pulse_hz"] = posterior_std_per_pulse(fn)
        res["_abs_err_fine_hz"] = np.abs(fn.f_mean - arr.f_true)
        res["_gaps_s"] = np.diff(arr.t_pulse_start, axis=1)
        results[pol.name] = res
        if verbose:
            c, f = res["controller_grid"], res["fine_grid"]
            print(f"{pol.name:28s} | fine median |err| {f['median_abs_err_map_hz']:6.0f} +/- {f['median_abs_err_map_se']:4.0f} Hz"
                  f" | P(<1 kHz) {f['p_err_lt_1khz']:.2f} +/- {f['p_err_lt_1khz_se']:.2f}"
                  f" | post. std {f['median_posterior_std_hz']:6.0f} Hz | coverage {f['coverage_2sigma']:.2f}"
                  f" | train {c.get('mean_train_time_s', float('nan')) * 1e3:5.2f} ms | R_last {c.get('mean_R_last', float('nan')):.2f}")
    return results


def _concat_arrays(arrs: List[RunArrays]) -> RunArrays:
    cat = lambda k: np.concatenate([getattr(a, k) for a in arrs], axis=0)
    return RunArrays(apd=cat("apd"), t_pulse_start=cat("t_pulse_start"), t_raman_pulse=cat("t_raman_pulse"),
                     phase=cat("phase"), omega_drive=cat("omega_drive"), offset_u=cat("offset_u"),
                     params=arrs[0].params, f_true=cat("f_true"), s_z_true=cat("s_z_true"), R=cat("R"))


def _concat_traces(trs: List[PosteriorTrace]) -> PosteriorTrace:
    cat = lambda k: np.concatenate([getattr(t, k) for t in trs], axis=0)
    return PosteriorTrace(grid_hz=cat("grid_hz"), P=cat("P"), log_evidence=cat("log_evidence"),
                          f_map=cat("f_map"), f_mean=cat("f_mean"), f_std=cat("f_std"))


# categorical palette (dataviz reference instance, fixed slot order)
_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#7a5cc7", "#8c8c8c"]


def plot_comparison(results: Dict[str, dict], out_png: str, title=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = list(results)
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    for k, name in enumerate(names):
        # fixed-order categorical hues; beyond the eight slots the line style carries identity
        c = _COLORS[k % len(_COLORS)]
        ls = ["-", "--", ":"][k // len(_COLORS)]
        sd = results[name]["_std_per_pulse_hz"]
        med = np.median(sd, axis=0)
        axes[0].plot(np.arange(med.size), med / 1e3, color=c, ls=ls, lw=2, label=name)
        e = np.sort(results[name]["_abs_err_fine_hz"]) / 1e3
        axes[1].plot(e, np.linspace(0, 1, e.size, endpoint=False), color=c, ls=ls, lw=2)
        g = results[name]["_gaps_s"]
        axes[2].plot(np.arange(1, g.shape[1] + 1), np.median(g, axis=0) * 1e6, color=c, ls=ls, lw=2)
    axes[0].set_xlabel("pulses taken"); axes[0].set_ylabel("median posterior std (kHz), fine grid")
    axes[1].set_xlabel("|posterior mean - truth| (kHz)"); axes[1].set_ylabel("fraction of shots below")
    axes[1].set_xlim(0, 6)
    axes[2].set_xlabel("pulse index"); axes[2].set_ylabel("median gap before pulse (us)")
    axes[2].set_yscale("log")
    for ax in axes:
        ax.grid(alpha=0.25)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].legend(fontsize=7, frameon=False)
    fig.suptitle(title or "adaptive Ramsey, model physics only (optimistic)", fontsize=10)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def _json_safe(results):
    out = {}
    for k, v in results.items():
        out[k] = {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--shots", type=int, default=40)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--pulses", type=int, default=12)
    ap.add_argument("--grid", type=int, default=41)
    ap.add_argument("--span", type=float, default=12.0e3, help="hypothesis grid full span, Hz")
    ap.add_argument("--truth-offsets", type=float, nargs="*", default=[0.0, 777.0, -2345.0],
                    help="injected truth - nominal resonance, Hz")
    ap.add_argument("--offsets-u", type=float, nargs="*", default=[0.0], help="drive fractional offsets")
    ap.add_argument("--coherence", type=float, default=None, help="truth per-read coherence (model's if unset)")
    ap.add_argument("--t2star", type=float, default=None, help="truth free-evolution T2* (s)")
    ap.add_argument("--jitter", type=float, default=0.0, help="truth per-shot resonance jitter (Hz)")
    ap.add_argument("--policies", nargs="*", default=None, help="names from DEFAULT_POLICIES")
    ap.add_argument("--gap-factors", type=float, nargs="*", default=None,
                    help="also run the 'adaptive' policy at these gap factors")
    ap.add_argument("--out", default=None, help="folder for results.json and the figure")
    a = ap.parse_args(argv)
    pols = [p for p in DEFAULT_POLICIES if a.policies is None or p.name in a.policies]
    for gf in (a.gap_factors or []):
        pols.append(RamseyPolicy(f"meanpar_stdgap_gf{gf:g}", PHASE_MEAN_PAR, GAP_POSTERIOR, gap_factor=gf))
    truth = TruthModel(coherence=a.coherence, t2_star=a.t2star, f_jitter_hz=a.jitter)
    print(f"truth model: {truth}")
    res = compare_policies(pols, n_shots=a.shots, seeds=tuple(range(1, a.seeds + 1)),
                           truth_offsets_hz=tuple(a.truth_offsets), offsets_u=tuple(a.offsets_u),
                           grid_size=a.grid, full_span_hz=a.span, n_pulses=a.pulses, truth=truth)
    print("CAVEAT: model physics (the posterior's own model is the truth unless --coherence/--t2star/"
          "--jitter say otherwise; the read model fails the hardware sim checks): upper bounds.")
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        with open(os.path.join(a.out, "results.json"), "w") as f:
            json.dump(dict(args=vars(a), truth=asdict(truth), results=_json_safe(res)), f, indent=1)
        plot_comparison(res, os.path.join(a.out, "comparison.png"),
                        title=f"adaptive Ramsey sim: grid {a.grid} over {a.span / 1e3:g} kHz, {a.pulses} pulses, "
                              f"{a.shots} shots x {a.seeds} seeds x {len(a.truth_offsets)} truths (model physics)")
        print(f"wrote {a.out}")
    return res


if __name__ == "__main__":
    main()
