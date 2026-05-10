from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np

try:
    from joblib import Parallel, delayed
    HAS_JOBLIB = True
except ImportError:
    HAS_JOBLIB = False

from kexp.base.feedback import Feedback, _feedback_kwargs_from_atomdata


DEFAULT_OMEGA_GROUP_TOLERANCE_RAD_S = 2.0 * np.pi * 100.0


@dataclass
class FeedbackReplayResult:
    """Container for replay/simulation outputs.

    Shapes use repeat on axis 0 and pulse-step on axis 1.

    Attributes
    ----------
    s_z_rr
        Resonance-track expectation value for each repeat and step.
        Shape: (N_repeat, N_step).
    P0_rr
        Posterior over frequency hypotheses for each repeat/step.
        Shape: (N_repeat, N_step, m).
    omega_control_rr
        Control omega used as experiment input per repeat/step (rad/s).
    omega_recomputed_rr
        Recomputed omega from posterior per repeat/step (rad/s).
    t_input_rr
        Reconstructed pulse-start time used as input to posterior update (s).
    t_s_z_rr
        Time associated with stored s_z values (post-measurement, s).
    k_rr
        Photon-count-equivalent measurement used by posterior update.
    apd_rr
        APD voltages used by replay/simulation (V).
    apd_norm_rr
        APD mapped to spin-like scale in [-1, 1] via calibration range.
    omega_guess_list
        Frequency hypothesis grid used in this run (rad/s).
    zidx
        Index in omega_guess_list nearest to real resonance.
    state_rr
        Optional resonance Bloch trajectory [sx, sy, sz].
        Shape: (N_repeat, N_step, 3) when requested, else None.
    metadata
        Additional run metadata and applied overrides.
    """

    s_z_rr: np.ndarray
    P0_rr: np.ndarray
    omega_control_rr: np.ndarray
    omega_recomputed_rr: np.ndarray
    t_input_rr: np.ndarray
    t_s_z_rr: np.ndarray
    k_rr: np.ndarray
    apd_rr: np.ndarray
    apd_norm_rr: np.ndarray
    omega_guess_list: np.ndarray
    zidx: int
    state_rr: Optional[np.ndarray] = None
    metadata: Dict[str, object] = field(default_factory=dict)


class FeedbackReplayCore(Feedback):
    """Replay engine for feedback experiments using atomdata.

    Public API
    ----------
    replay_measured(...)
        Reconstructs measured experiment behavior using measured APD and,
        by default, measured control omega.

    simulate_counterfactual(...)
        Runs what-if simulations with override knobs for timing, coherence,
        grid size, and control-omega source.

    Notes
    -----
    - No dummy leading sample handling is applied. All provided pulse steps are
      simulated in-order as actual measurements.
    - Posterior input time uses reconstructed pulse-start time from
      `t_between_pulses_mu`.
    - `t_s_z_rr` is returned for post-measurement alignment in plotting.
    """

    def __init__(
        self,
        ad,
        omega_group_tolerance_rad_s: float = DEFAULT_OMEGA_GROUP_TOLERANCE_RAD_S,
    ):
        self.ad = ad
        self._base_kwargs = self._build_base_feedback_kwargs(ad)
        self.omega_group_tolerance_rad_s = float(omega_group_tolerance_rad_s)
        self._default_timing = self._get_default_timing_params()
        Feedback.__init__(self, **self._base_kwargs)

    def _build_base_feedback_kwargs(self, ad) -> Dict[str, object]:
        kwargs = _feedback_kwargs_from_atomdata(ad)

        p = getattr(ad, "p", None)
        if p is None:
            raise ValueError("atomdata must provide ad.p with feedback parameters.")

        if kwargs.get("frequency_resonance") is None:
            raise ValueError("Missing ad.p.frequency_raman_transition required for replay.")
        if kwargs.get("t_raman_pi_pulse") is None:
            raise ValueError("Missing ad.p.t_raman_pi_pulse required for replay.")
        if kwargs.get("t_raman_pulse") is None and kwargs.get("dt_eff") is None:
            raise ValueError("Missing t_raman_pulse/dt_eff required for replay timing.")
        if kwargs.get("t_img_pulse") is None:
            raise ValueError("Missing ad.p.t_img_pulse required for replay timing.")
        if kwargs.get("back_action_coherence") is None:
            kwargs["back_action_coherence"] = float(getattr(p, "back_action_coherence", 1.0))

        if not hasattr(ad, "data") or not hasattr(ad.data, "apd"):
            raise ValueError("atomdata must provide ad.data.apd for replay.")

        if hasattr(p, "omega_guess_list"):
            omega_guess = np.asarray(p.omega_guess_list, dtype=float)
            if omega_guess.ndim == 1 and omega_guess.size > 0:
                kwargs["m"] = int(omega_guess.size)

        return kwargs

    def _get_default_timing_params(self) -> Dict[str, float]:
        p = self.ad.p

        t_between = getattr(p, "t_between_pulses_mu", None)
        if t_between is None:
            t_calc = int(getattr(p, "t_calculation_slack_compensation_mu", 0))
            t_fifo = int(getattr(p, "t_fifo_mu", 1000))
            t_between = int(
                self.compute_t_between_pulses_mu(
                    t_calculation_slack_compensation_mu=t_calc,
                    t_raman_pulse=float(getattr(p, "t_raman_pulse", getattr(p, "dt_eff"))),
                    t_img_pulse=float(getattr(p, "t_img_pulse")),
                    t_fifo_mu=np.int64(t_fifo),
                )
            )

        return {
            "t_between_pulses_mu": int(t_between),
            "delta_t_mu": int(getattr(p, "delta_t_mu", 0)),
            "t_raman_set_pretrigger_mu": int(getattr(p, "t_raman_set_pretrigger_mu", 0)),
            "t_calculation_slack_compensation_mu": int(getattr(p, "t_calculation_slack_compensation_mu", 0)),
            "t_fifo_mu": int(getattr(p, "t_fifo_mu", 1000)),
        }

    def _to_repeat_step(self, arr, name: str) -> np.ndarray:
        x = np.asarray(arr)

        if x.dtype == object:
            rows = [np.asarray(row, dtype=float).ravel() for row in x]
            if len(rows) == 0:
                raise ValueError(f"{name} cannot be empty.")
            n_step = len(rows[0])
            for idx, row in enumerate(rows):
                if len(row) != n_step:
                    raise ValueError(
                        f"{name} has ragged row lengths; row 0 has {n_step}, row {idx} has {len(row)}."
                    )
            return np.vstack(rows)

        x = np.asarray(arr, dtype=float)
        if x.ndim == 1:
            return x.reshape(1, -1)
        if x.ndim == 2:
            return x
        raise ValueError(f"{name} must be 1D or 2D (repeat, step), got shape {x.shape}.")

    def _broadcast_override(
        self,
        arr: Optional[Sequence[float]],
        name: str,
        n_repeat: int,
        n_step: int,
    ) -> Optional[np.ndarray]:
        if arr is None:
            return None

        x = np.asarray(arr, dtype=float)
        if x.ndim == 1:
            if x.shape[0] != n_step:
                raise ValueError(f"{name} length must be {n_step}, got {x.shape[0]}.")
            return np.tile(x.reshape(1, -1), (n_repeat, 1))
        if x.ndim == 2:
            if x.shape != (n_repeat, n_step):
                raise ValueError(f"{name} shape must be ({n_repeat}, {n_step}), got {x.shape}.")
            return x
        raise ValueError(f"{name} must be 1D or 2D, got shape {x.shape}.")

    def _resolve_grid(
        self,
        m_override: Optional[int],
        omega_guess_list_override: Optional[Sequence[float]],
    ) -> Tuple[np.ndarray, int]:
        freq_res = float(self._base_kwargs["frequency_resonance"])
        omega_res = 2.0 * np.pi * freq_res

        if omega_guess_list_override is not None:
            omega_guess = np.asarray(omega_guess_list_override, dtype=float).ravel()
            if omega_guess.size < 2:
                raise ValueError("omega_guess_list_override must contain at least two points.")
            return omega_guess, int(np.argmin(np.abs(omega_guess - omega_res)))

        if hasattr(self.ad.p, "omega_guess_list"):
            omega_saved = np.asarray(self.ad.p.omega_guess_list, dtype=float).ravel()
        else:
            omega_saved = np.asarray(self.omega_guess_list, dtype=float).ravel()

        if m_override is None or int(m_override) == omega_saved.size:
            omega_guess = omega_saved
        else:
            omega_guess = np.linspace(float(np.min(omega_saved)), float(np.max(omega_saved)), int(m_override))

        zidx = int(np.argmin(np.abs(omega_guess - omega_res)))
        return omega_guess, zidx

    def _reinitialize_feedback(
        self,
        *,
        back_action_coherence: Optional[float],
        t_raman_pulse: Optional[float],
        t_raman_pulse_ideal: Optional[float],
        t_img_pulse: Optional[float],
        m_override: Optional[int],
        omega_guess_list_override: Optional[Sequence[float]],
    ) -> Tuple[np.ndarray, int]:
        kwargs = dict(self._base_kwargs)

        if back_action_coherence is not None:
            kwargs["back_action_coherence"] = float(back_action_coherence)

        if t_raman_pulse is not None:
            kwargs["t_raman_pulse"] = float(t_raman_pulse)
            kwargs["dt_eff"] = float(t_raman_pulse)

        if t_raman_pulse_ideal is not None:
            kwargs["t_raman_pulse_ideal"] = float(t_raman_pulse_ideal)
            kwargs["dt_ideal"] = float(t_raman_pulse_ideal)

        if t_img_pulse is not None:
            kwargs["t_img_pulse"] = float(t_img_pulse)

        omega_guess, zidx = self._resolve_grid(m_override=m_override, omega_guess_list_override=omega_guess_list_override)

        kwargs["m"] = int(omega_guess.size)

        Feedback.__init__(self, **kwargs)

        self.omega_guess_list = np.asarray(omega_guess, dtype=float)
        self.omega_sq_list = self.omega_guess_list * self.omega_guess_list
        self.omega_guess_start = float(self.omega_guess_list[0])

        return self.omega_guess_list.copy(), int(zidx)

    def _resolve_timing(
        self,
        *,
        t_raman_pulse: Optional[float],
        t_raman_pulse_ideal: Optional[float],
        t_img_pulse: Optional[float],
        delta_t_mu: Optional[int],
        t_between_pulses_mu: Optional[int],
    ) -> Dict[str, float]:
        timing = dict(self._default_timing)

        if delta_t_mu is not None:
            timing["delta_t_mu"] = int(delta_t_mu)

        dt_eff = float(self.dt_eff if t_raman_pulse is None else t_raman_pulse)
        dt_ideal = float(self.dt_ideal if t_raman_pulse_ideal is None else t_raman_pulse_ideal)
        dt_img = float(self.dt_z if t_img_pulse is None else t_img_pulse)

        timing["dt_eff"] = dt_eff
        timing["dt_ideal"] = dt_ideal
        timing["t_img_pulse"] = dt_img

        if t_between_pulses_mu is not None:
            timing["t_between_pulses_mu"] = int(t_between_pulses_mu)
        elif (t_raman_pulse is not None) or (t_img_pulse is not None):
            timing["t_between_pulses_mu"] = int(
                self.compute_t_between_pulses_mu(
                    t_calculation_slack_compensation_mu=int(timing["t_calculation_slack_compensation_mu"]),
                    t_raman_pulse=dt_eff,
                    t_img_pulse=dt_img,
                    t_fifo_mu=np.int64(int(timing["t_fifo_mu"])),
                )
            )

        return timing

    def _resolve_apd_rr(self, apd_override_rr: Optional[Sequence[float]]) -> np.ndarray:
        if apd_override_rr is None:
            apd_rr = self._to_repeat_step(self.ad.data.apd, "ad.data.apd")
        else:
            apd_rr = self._to_repeat_step(apd_override_rr, "apd_override_rr")

        if apd_rr.shape[1] == 0:
            raise ValueError("APD input must contain at least one pulse step.")

        return apd_rr

    def _resolve_omega_rr(
        self,
        n_repeat: int,
        n_step: int,
        omega_override_rr: Optional[Sequence[float]],
    ) -> Optional[np.ndarray]:
        if omega_override_rr is not None:
            return self._broadcast_override(omega_override_rr, "omega_override_rr", n_repeat, n_step)

        if hasattr(self.ad.data, "omega_raman"):
            omega_rr = self._to_repeat_step(self.ad.data.omega_raman, "ad.data.omega_raman")
            if omega_rr.shape != (n_repeat, n_step):
                raise ValueError(
                    f"ad.data.omega_raman shape {omega_rr.shape} does not match APD shape ({n_repeat}, {n_step})."
                )
            return omega_rr

        return None

    def _normalize_apd(self, apd_rr: np.ndarray) -> np.ndarray:
        v_range = float(self.v_apd_all_up - self.v_apd_all_down)
        if abs(v_range) < 1.0e-15:
            raise ValueError("APD calibration range is zero; cannot normalize APD.")
        return 2.0 * (apd_rr - float(self.v_apd_all_down)) / v_range - 1.0

    def _group_repeats_by_omega(
        self,
        omega_rr: np.ndarray,
        tolerance_rad_s: Optional[float] = None,
    ) -> List[List[int]]:
        tol = self.omega_group_tolerance_rad_s if tolerance_rad_s is None else float(tolerance_rad_s)
        n_repeat = omega_rr.shape[0]

        groups: List[List[int]] = []
        for r in range(n_repeat):
            placed = False
            for group in groups:
                ref = group[0]
                if np.max(np.abs(omega_rr[r] - omega_rr[ref])) <= tol:
                    group.append(r)
                    placed = True
                    break
            if not placed:
                groups.append([r])

        return groups

    def average_by_omega_group(
        self,
        result: FeedbackReplayResult,
        *,
        use_stderr: bool = True,
        tolerance_rad_s: Optional[float] = None,
    ) -> List[Dict[str, np.ndarray]]:
        """Compute grouped averages for repeats sharing the same omega sequence."""
        groups = self._group_repeats_by_omega(result.omega_control_rr, tolerance_rad_s=tolerance_rad_s)

        summaries: List[Dict[str, np.ndarray]] = []
        for members in groups:
            idx = np.asarray(members, dtype=int)
            n = max(1, len(members))
            denom = np.sqrt(float(n)) if use_stderr and n > 1 else 1.0

            apd_mean = np.mean(result.apd_norm_rr[idx], axis=0)
            apd_std = np.std(result.apd_norm_rr[idx], axis=0, ddof=1) if n > 1 else np.zeros(result.apd_norm_rr.shape[1])

            sz_mean = np.mean(result.s_z_rr[idx], axis=0)
            sz_std = np.std(result.s_z_rr[idx], axis=0, ddof=1) if n > 1 else np.zeros(result.s_z_rr.shape[1])

            omega_mean = np.mean(result.omega_control_rr[idx], axis=0)
            omega_comp_mean = np.mean(result.omega_recomputed_rr[idx], axis=0)

            summaries.append(
                {
                    "members": idx,
                    "t_input": np.mean(result.t_input_rr[idx], axis=0),
                    "t_s_z": np.mean(result.t_s_z_rr[idx], axis=0),
                    "apd_norm_mean": apd_mean,
                    "apd_norm_err": apd_std / denom,
                    "s_z_mean": sz_mean,
                    "s_z_err": sz_std / denom,
                    "omega_control_mean": omega_mean,
                    "omega_recomputed_mean": omega_comp_mean,
                }
            )

        return summaries

    def replay_measured(
        self,
        *,
        include_photon_noise: Optional[bool] = None,
        update_raman_frequency: Optional[bool] = None,
        update_rabi_frequency: bool = False,
        control_omega_source: str = "measured",
        return_full_state: bool = False,
        back_action_coherence: Optional[float] = None,
        t_raman_pulse: Optional[float] = None,
        t_raman_pulse_ideal: Optional[float] = None,
        t_img_pulse: Optional[float] = None,
        delta_t_mu: Optional[int] = None,
        t_between_pulses_mu: Optional[int] = None,
        m_override: Optional[int] = None,
        omega_guess_list_override: Optional[Sequence[float]] = None,
        apd_override_rr: Optional[Sequence[float]] = None,
        omega_override_rr: Optional[Sequence[float]] = None,
        n_jobs: int = 1,
        parallel_verbose: int = 0,
    ) -> FeedbackReplayResult:
        """Replay using measured APD and measured control omega by default.

        Parameters
        ----------
        n_jobs
            Number of cores to use for parallel shot simulation. Default 1 (sequential).
            Use -1 to use all available cores. Values > 1 enable parallel processing.
        parallel_verbose
            Verbosity level for joblib parallel execution (0-10).
        """
        return self._run_sequence(
            include_photon_noise=include_photon_noise,
            update_raman_frequency=update_raman_frequency,
            update_rabi_frequency=update_rabi_frequency,
            control_omega_source=control_omega_source,
            return_full_state=return_full_state,
            back_action_coherence=back_action_coherence,
            t_raman_pulse=t_raman_pulse,
            t_raman_pulse_ideal=t_raman_pulse_ideal,
            t_img_pulse=t_img_pulse,
            delta_t_mu=delta_t_mu,
            t_between_pulses_mu=t_between_pulses_mu,
            m_override=m_override,
            omega_guess_list_override=omega_guess_list_override,
            apd_override_rr=apd_override_rr,
            omega_override_rr=omega_override_rr,
            default_use_measured_apd=True,
            n_jobs=int(n_jobs),
            parallel_verbose=int(parallel_verbose),
        )

    def simulate_counterfactual(
        self,
        *,
        apd_input_rr: Optional[Sequence[float]] = None,
        omega_control_rr: Optional[Sequence[float]] = None,
        include_photon_noise: Optional[bool] = None,
        update_raman_frequency: Optional[bool] = None,
        update_rabi_frequency: bool = False,
        control_omega_source: str = "recomputed",
        return_full_state: bool = False,
        back_action_coherence: Optional[float] = None,
        t_raman_pulse: Optional[float] = None,
        t_raman_pulse_ideal: Optional[float] = None,
        t_img_pulse: Optional[float] = None,
        delta_t_mu: Optional[int] = None,
        t_between_pulses_mu: Optional[int] = None,
        m_override: Optional[int] = None,
        omega_guess_list_override: Optional[Sequence[float]] = None,
        n_jobs: int = 1,
        parallel_verbose: int = 0,
    ) -> FeedbackReplayResult:
        """Run a what-if simulation with optional APD and omega inputs.

        Parameters
        ----------
        n_jobs
            Number of cores to use for parallel shot simulation. Default 1 (sequential).
            Use -1 to use all available cores. Values > 1 enable parallel processing.
        parallel_verbose
            Verbosity level for joblib parallel execution (0-10).
        """
        return self._run_sequence(
            include_photon_noise=include_photon_noise,
            update_raman_frequency=update_raman_frequency,
            update_rabi_frequency=update_rabi_frequency,
            control_omega_source=control_omega_source,
            return_full_state=return_full_state,
            back_action_coherence=back_action_coherence,
            t_raman_pulse=t_raman_pulse,
            t_raman_pulse_ideal=t_raman_pulse_ideal,
            t_img_pulse=t_img_pulse,
            delta_t_mu=delta_t_mu,
            t_between_pulses_mu=t_between_pulses_mu,
            m_override=m_override,
            omega_guess_list_override=omega_guess_list_override,
            apd_override_rr=apd_input_rr,
            omega_override_rr=omega_control_rr,
            default_use_measured_apd=False,
            n_jobs=int(n_jobs),
            parallel_verbose=int(parallel_verbose),
        )

    def _run_shot_parallel(
        self,
        r: int,
        n_step: int,
        apd_rr: np.ndarray,
        omega_measured_rr: Optional[np.ndarray],
        control_omega_source: str,
        timing: Dict[str, float],
        include_photon_noise: bool,
        update_raman_frequency: bool,
        update_rabi_frequency: bool,
        return_full_state: bool,
        zidx: int,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, Optional[np.ndarray]]:
        """Process a single shot (repeat) in parallel-safe manner.

        Returns (s_z, P0, omega_control, omega_recomputed, t_input, t_s_z, k, state).
        """
        self.reset_feedback_state()

        phase_tracker = 0.0
        omega_prev = 0.0

        s_z = np.zeros(n_step, dtype=float)
        P0 = np.zeros((n_step, self.m), dtype=float)
        omega_control = np.zeros(n_step, dtype=float)
        omega_recomputed = np.zeros(n_step, dtype=float)
        t_input = np.zeros(n_step, dtype=float)
        t_s_z = np.zeros(n_step, dtype=float)
        k = np.zeros(n_step, dtype=float)
        state = np.zeros((n_step, 3), dtype=float) if return_full_state else None

        tP_mu = int(timing["t_between_pulses_mu"])
        dt_mu = int(timing["delta_t_mu"])
        tR_mu = int(timing["t_raman_set_pretrigger_mu"])

        if control_omega_source in {"measured", "override"}:
            self.omega_raman = float(omega_measured_rr[r, 0])
        else:
            self.omega_raman = float(self.omega_guess_start)

        for i in range(n_step):
            if control_omega_source in {"measured", "override"}:
                omega_ctrl = float(omega_measured_rr[r, i])
            else:
                omega_ctrl = float(self.omega_raman)

            self.omega_raman = omega_ctrl

            phase_tracker += (
                ((tP_mu - tR_mu + dt_mu) * omega_prev + (tR_mu - dt_mu) * self.omega_raman) * 1.0e-9
            )

            t_in = i * tP_mu * 1.0e-9
            k_val = self.convert_measurement(float(apd_rr[r, i]))

            omega_prev = self.omega_raman
            omega_new, omega_std = self.generate_posterior(
                k_val,
                t_in,
                phase_raman_pulse_start=phase_tracker,
                update_raman_frequency=1 if update_raman_frequency else 0,
                update_rabi_frequency=1 if update_rabi_frequency else 0,
                include_photon_noise=1 if include_photon_noise else 0,
            )

            self.omega_raman = float(omega_new)
            self.Omega = float(omega_std)

            s_z[i] = float(self.state_z[zidx])
            P0[i, :] = self.P0
            omega_control[i] = omega_ctrl
            omega_recomputed[i] = float(self.omega_raman)
            t_input[i] = t_in
            t_s_z[i] = t_in + float(timing["dt_eff"]) + float(timing["t_img_pulse"])
            k[i] = float(k_val)

            if state is not None:
                state[i, 0] = float(self.state_x[zidx])
                state[i, 1] = float(self.state_y[zidx])
                state[i, 2] = float(self.state_z[zidx])

        return s_z, P0, omega_control, omega_recomputed, t_input, t_s_z, k, state


    def _run_sequence(
        self,
        *,
        include_photon_noise: Optional[bool],
        update_raman_frequency: Optional[bool],
        update_rabi_frequency: bool,
        control_omega_source: str,
        return_full_state: bool,
        back_action_coherence: Optional[float],
        t_raman_pulse: Optional[float],
        t_raman_pulse_ideal: Optional[float],
        t_img_pulse: Optional[float],
        delta_t_mu: Optional[int],
        t_between_pulses_mu: Optional[int],
        m_override: Optional[int],
        omega_guess_list_override: Optional[Sequence[float]],
        apd_override_rr: Optional[Sequence[float]],
        omega_override_rr: Optional[Sequence[float]],
        default_use_measured_apd: bool,
        n_jobs: int = 1,
        parallel_verbose: int = 0,
    ) -> FeedbackReplayResult:
        if include_photon_noise is None:
            include_photon_noise = bool(getattr(self.ad.p, "include_photon_noise", 1))

        if update_raman_frequency is None:
            update_raman_frequency = bool(getattr(self.ad.p, "update_raman_frequency_bool", 1))

        if control_omega_source not in {"measured", "recomputed", "override"}:
            raise ValueError("control_omega_source must be one of: measured, recomputed, override.")

        if control_omega_source == "override" and omega_override_rr is None:
            raise ValueError("control_omega_source='override' requires omega_override_rr.")

        if (apd_override_rr is None) and (not default_use_measured_apd):
            raise ValueError("simulate_counterfactual requires apd_input_rr when not using measured APD.")

        omega_guess_list, zidx = self._reinitialize_feedback(
            back_action_coherence=back_action_coherence,
            t_raman_pulse=t_raman_pulse,
            t_raman_pulse_ideal=t_raman_pulse_ideal,
            t_img_pulse=t_img_pulse,
            m_override=m_override,
            omega_guess_list_override=omega_guess_list_override,
        )

        timing = self._resolve_timing(
            t_raman_pulse=t_raman_pulse,
            t_raman_pulse_ideal=t_raman_pulse_ideal,
            t_img_pulse=t_img_pulse,
            delta_t_mu=delta_t_mu,
            t_between_pulses_mu=t_between_pulses_mu,
        )

        apd_rr = self._resolve_apd_rr(apd_override_rr=apd_override_rr)
        n_repeat, n_step = apd_rr.shape

        omega_measured_rr = self._resolve_omega_rr(n_repeat=n_repeat, n_step=n_step, omega_override_rr=omega_override_rr)
        if control_omega_source in {"measured", "override"} and omega_measured_rr is None:
            raise ValueError("No omega control data available. Provide omega_override_rr or saved ad.data.omega_raman.")

        # Use parallel processing if n_jobs != 1 and joblib is available
        use_parallel = n_jobs != 1 and HAS_JOBLIB
        if n_jobs != 1 and not HAS_JOBLIB:
            import warnings
            warnings.warn(
                "joblib not installed; falling back to sequential processing. "
                "Install joblib for parallel execution: pip install joblib",
                UserWarning,
            )

        if use_parallel:
            shot_results = Parallel(n_jobs=n_jobs, verbose=parallel_verbose, backend='threading')(
                delayed(self._run_shot_parallel)(
                    r,
                    n_step,
                    apd_rr,
                    omega_measured_rr,
                    control_omega_source,
                    timing,
                    include_photon_noise,
                    update_raman_frequency,
                    update_rabi_frequency,
                    return_full_state,
                    zidx,
                )
                for r in range(n_repeat)
            )
            # Collect results from parallel execution
            s_z_rr = np.zeros((n_repeat, n_step), dtype=float)
            P0_rr = np.zeros((n_repeat, n_step, self.m), dtype=float)
            omega_control_rr = np.zeros((n_repeat, n_step), dtype=float)
            omega_recomputed_rr = np.zeros((n_repeat, n_step), dtype=float)
            t_input_rr = np.zeros((n_repeat, n_step), dtype=float)
            t_s_z_rr = np.zeros((n_repeat, n_step), dtype=float)
            k_rr = np.zeros((n_repeat, n_step), dtype=float)
            state_rr = np.zeros((n_repeat, n_step, 3), dtype=float) if return_full_state else None

            for r, (s_z, P0, omega_ctrl, omega_recomp, t_in, t_s, k, state) in enumerate(shot_results):
                s_z_rr[r, :] = s_z
                P0_rr[r, :, :] = P0
                omega_control_rr[r, :] = omega_ctrl
                omega_recomputed_rr[r, :] = omega_recomp
                t_input_rr[r, :] = t_in
                t_s_z_rr[r, :] = t_s
                k_rr[r, :] = k
                if state_rr is not None and state is not None:
                    state_rr[r, :, :] = state
        else:
            # Sequential processing (original code)
            s_z_rr = np.zeros((n_repeat, n_step), dtype=float)
            P0_rr = np.zeros((n_repeat, n_step, self.m), dtype=float)
            omega_control_rr = np.zeros((n_repeat, n_step), dtype=float)
            omega_recomputed_rr = np.zeros((n_repeat, n_step), dtype=float)
            t_input_rr = np.zeros((n_repeat, n_step), dtype=float)
            t_s_z_rr = np.zeros((n_repeat, n_step), dtype=float)
            k_rr = np.zeros((n_repeat, n_step), dtype=float)
            state_rr = np.zeros((n_repeat, n_step, 3), dtype=float) if return_full_state else None

            for r in range(n_repeat):
                s_z, P0, omega_ctrl, omega_recomp, t_in, t_s, k, state = self._run_shot_parallel(
                    r, n_step, apd_rr, omega_measured_rr, control_omega_source, timing,
                    include_photon_noise, update_raman_frequency, update_rabi_frequency,
                    return_full_state, zidx,
                )
                s_z_rr[r, :] = s_z
                P0_rr[r, :, :] = P0
                omega_control_rr[r, :] = omega_ctrl
                omega_recomputed_rr[r, :] = omega_recomp
                t_input_rr[r, :] = t_in
                t_s_z_rr[r, :] = t_s
                k_rr[r, :] = k
                if state_rr is not None and state is not None:
                    state_rr[r, :, :] = state

        apd_norm_rr = self._normalize_apd(apd_rr)

        return FeedbackReplayResult(
            s_z_rr=s_z_rr,
            P0_rr=P0_rr,
            omega_control_rr=omega_control_rr,
            omega_recomputed_rr=omega_recomputed_rr,
            t_input_rr=t_input_rr,
            t_s_z_rr=t_s_z_rr,
            k_rr=k_rr,
            apd_rr=apd_rr,
            apd_norm_rr=apd_norm_rr,
            omega_guess_list=omega_guess_list,
            zidx=int(zidx),
            state_rr=state_rr,
            metadata={
                "run_id": int(getattr(self.ad.run_info, "run_id", -1)),
                "N_repeat": int(n_repeat),
                "N_step": int(n_step),
                "m": int(self.m),
                "control_omega_source": str(control_omega_source),
                "include_photon_noise": bool(include_photon_noise),
                "update_raman_frequency": bool(update_raman_frequency),
                "update_rabi_frequency": bool(update_rabi_frequency),
                "timing": timing,
            },
        )


class FeedbackReplay(FeedbackReplayCore):
    """Notebook-friendly wrapper around FeedbackReplayCore.

    This subclass keeps plotting and quick-analysis helpers separate from the
    core replay engine so simulation methods stay focused and readable.
    """

    def run_default(self, *, return_full_state: bool = False) -> FeedbackReplayResult:
        """Convenience default: replay measured APD with measured omega control."""
        return self.replay_measured(return_full_state=return_full_state)

    def run_with_recomputed_omega_control(
        self,
        *,
        return_full_state: bool = False,
        include_photon_noise: Optional[bool] = None,
        update_raman_frequency: Optional[bool] = None,
    ) -> FeedbackReplayResult:
        """Replay APD while applying recomputed omega as control at each step."""
        return self.replay_measured(
            control_omega_source="recomputed",
            return_full_state=return_full_state,
            include_photon_noise=include_photon_noise,
            update_raman_frequency=update_raman_frequency,
        )

    def grouped_average(
        self,
        result: FeedbackReplayResult,
        *,
        use_stderr: bool = True,
    ) -> List[Dict[str, np.ndarray]]:
        """Easy-call grouped averaging by shared omega control sequence."""
        return self.average_by_omega_group(result, use_stderr=use_stderr)

    def compute_group_fit_metrics(
        self,
        groups: List[Dict[str, np.ndarray]],
        *,
        use_weighted_loss: bool = False,
        eps: float = 1.0e-12,
    ) -> Dict[str, object]:
        """Compute aggregate fit metrics between grouped APD and grouped resonant s_z.

        Parameters
        ----------
        groups
            Output of `grouped_average(...)` or `average_by_omega_group(...)`.
        use_weighted_loss
            If True, use weights 1/(apd_norm_err^2 + eps).
        eps
            Small positive number for weighted-loss stability.
        """
        group_rows: List[Dict[str, float]] = []

        weighted_sq_sum = 0.0
        weight_sum = 0.0
        total_points = 0

        for gidx, group in enumerate(groups):
            sim = np.asarray(group["s_z_mean"], dtype=float).ravel()
            apd = np.asarray(group["apd_norm_mean"], dtype=float).ravel()

            if sim.size == 0 or apd.size == 0 or sim.shape != apd.shape:
                group_rows.append(
                    {
                        "group_index": float(gidx),
                        "mse": np.nan,
                        "n_points": 0.0,
                    }
                )
                continue

            residual = sim - apd
            sq = residual * residual

            if use_weighted_loss:
                sigma = np.asarray(group.get("apd_norm_err", np.zeros_like(residual)), dtype=float).ravel()
                if sigma.shape != residual.shape:
                    sigma = np.zeros_like(residual)
                w = 1.0 / (sigma * sigma + float(eps))
            else:
                w = np.ones_like(residual)

            group_weight_sum = float(np.sum(w))
            group_sq_sum = float(np.sum(w * sq))
            group_mse = np.nan if group_weight_sum <= 0.0 else group_sq_sum / group_weight_sum

            weighted_sq_sum += group_sq_sum
            weight_sum += group_weight_sum
            total_points += int(residual.size)

            group_rows.append(
                {
                    "group_index": float(gidx),
                    "mse": float(group_mse),
                    "n_points": float(residual.size),
                }
            )

        overall_mse = np.nan if weight_sum <= 0.0 else weighted_sq_sum / weight_sum
        return {
            "overall_mse": float(overall_mse) if np.isfinite(overall_mse) else np.nan,
            "n_groups": int(len(groups)),
            "n_points": int(total_points),
            "use_weighted_loss": bool(use_weighted_loss),
            "group_metrics": group_rows,
        }

    def _extract_apd_noise_fraction(self) -> float:
        """Extract APD measurement noise as a fraction of expected photon count.

        Returns ratio of std_n_photons_per_shot / N_photons_per_shot if available,
        else returns 0.0 (noiseless assumption).
        """
        try:
            N_photons = float(getattr(self.ad.p, "N_photons_per_shot", 1.0))
            std_photons = float(getattr(self.ad.p, "std_n_photons_per_shot", 0.0))
            if N_photons > 0.0:
                return std_photons / N_photons
        except (AttributeError, TypeError, ValueError):
            pass
        return 0.0

    def compute_group_fit_metrics_with_noise(
        self,
        result: FeedbackReplayResult,
        *,
        include_apd_noise: Optional[bool] = None,
        apd_noise_override_fraction: Optional[float] = None,
        apd_noise_min_std: float = 0.03,
        aggregate_mode: str = "point_weighted",
        tolerance_rad_s: Optional[float] = None,
        eps: float = 1.0e-12,
    ) -> Dict[str, object]:
        """Compute per-omega-group fit metrics (naturally per-shot for feedback runs).

        Groups repeats by omega sequence similarity. For validation experiments
        with deterministic omega (all repeats same), this yields 1 group and 1 MSE.
        For feedback experiments with varying omega per shot, this yields N groups
        (one per unique omega) and returns the average MSE across groups.

        Parameters
        ----------
        result
            Replay result from replay_measured(...) or similar.
        include_apd_noise
            Global APD-noise enable flag.
            If None (default), APD noise is enabled in principle and then filtered
            per group by shot count: groups with more than one run do not use APD
            noise weighting. Groups with exactly one run can use APD noise weighting.
            If False, APD noise weighting is disabled for all groups.
            If True, APD noise weighting is enabled for singleton groups only
            (groups with >1 run still do not use APD noise weighting).
        apd_noise_override_fraction
            Optional override for APD noise fraction (std_photons / N_photons).
            If provided, use this value instead of extracting from calibration.
            Only used when APD noise weighting is enabled.
        apd_noise_min_std
            Minimum APD uncertainty floor on normalized APD scale. This prevents
            near-zero APD points from receiving extremely large weights.
        aggregate_mode
            Group-loss aggregation mode:
            - 'point_weighted': aggregate by total weighted residual across points
            - 'mean_over_groups': arithmetic mean of per-group MSE values
        tolerance_rad_s
            Omega grouping tolerance. If None, uses self.omega_group_tolerance_rad_s.
            Tighter tolerance → more groups (for feedback: closer to 1 group per shot).
        eps
            Small positive number for numerical stability.

        Returns
        -------
        dict
            Keys: overall_mse, n_groups, n_points, apd_noise_fraction,
            apd_noise_applied_any, group_metrics.
        """
        groups = self.average_by_omega_group(result, use_stderr=True, tolerance_rad_s=tolerance_rad_s)

        if float(apd_noise_min_std) < 0.0:
            raise ValueError("apd_noise_min_std must be non-negative.")
        if aggregate_mode not in ("point_weighted", "mean_over_groups"):
            raise ValueError(
                f"Unsupported aggregate_mode={aggregate_mode!r}. "
                "Use 'point_weighted' or 'mean_over_groups'."
            )

        # Auto: enable APD noise globally, but still filter per-group by member count.
        global_include_apd_noise = True if include_apd_noise is None else bool(include_apd_noise)

        # Determine APD noise fraction once, then apply per eligible group.
        if global_include_apd_noise:
            if apd_noise_override_fraction is not None:
                apd_noise_frac = float(apd_noise_override_fraction)
            else:
                apd_noise_frac = self._extract_apd_noise_fraction()
        else:
            apd_noise_frac = 0.0

        if apd_noise_frac < 0.0:
            raise ValueError("APD noise fraction must be non-negative.")

        group_rows: List[Dict[str, float]] = []
        group_mse_values: List[float] = []
        total_points = 0
        apd_noise_applied_any = False
        weighted_sq_sum = 0.0
        weight_sum = 0.0

        for gidx, group in enumerate(groups):
            sim = np.asarray(group["s_z_mean"], dtype=float).ravel()
            apd = np.asarray(group["apd_norm_mean"], dtype=float).ravel()
            n_members = int(np.asarray(group.get("members", []), dtype=int).size)
            use_group_apd_noise = bool(global_include_apd_noise and apd_noise_frac > 0.0 and n_members <= 1)

            if sim.size == 0 or apd.size == 0 or sim.shape != apd.shape:
                group_rows.append(
                    {
                        "group_index": float(gidx),
                        "mse": np.nan,
                        "n_points": 0.0,
                        "n_members": float(n_members),
                        "use_apd_noise": float(1 if use_group_apd_noise else 0),
                    }
                )
                continue

            residual = sim - apd
            sq = residual * residual

            if use_group_apd_noise:
                # Weight by inverse measurement uncertainty with a floor to avoid
                # pathological overweighting at near-zero APD.
                measurement_std = np.hypot(np.abs(apd) * apd_noise_frac, float(apd_noise_min_std))
                w = 1.0 / (measurement_std * measurement_std + float(eps))
                apd_noise_applied_any = True
            else:
                w = np.ones_like(residual)

            group_weight_sum = float(np.sum(w))
            group_sq_sum = float(np.sum(w * sq))
            group_mse = np.nan if group_weight_sum <= 0.0 else group_sq_sum / group_weight_sum
            weighted_sq_sum += group_sq_sum
            weight_sum += group_weight_sum

            total_points += int(residual.size)

            if np.isfinite(group_mse):
                group_mse_values.append(float(group_mse))

            group_rows.append({
                "group_index": float(gidx),
                "mse": float(group_mse) if np.isfinite(group_mse) else np.nan,
                "n_points": float(residual.size),
                "n_members": float(n_members),
                "use_apd_noise": float(1 if use_group_apd_noise else 0),
                "weight_sum": float(group_weight_sum),
            })

        if aggregate_mode == "point_weighted":
            overall_mse = np.nan if weight_sum <= 0.0 else float(weighted_sq_sum / weight_sum)
        else:
            overall_mse = np.nan if len(group_mse_values) == 0 else float(np.mean(group_mse_values))

        return {
            "overall_mse": float(overall_mse) if np.isfinite(overall_mse) else np.nan,
            "n_groups": int(len(groups)),
            "n_points": int(total_points),
            "apd_noise_fraction": float(apd_noise_frac),
            "apd_noise_min_std": float(apd_noise_min_std),
            "aggregate_mode": str(aggregate_mode),
            "apd_noise_applied_any": bool(apd_noise_applied_any),
            "group_metrics": group_rows,
        }

    def replay_validation_mode(
        self,
        *,
        back_action_coherence: Optional[float] = None,
        control_omega_source: str = "measured",
        include_photon_noise: Optional[bool] = None,
        update_raman_frequency: Optional[bool] = None,
        update_rabi_frequency: bool = False,
        use_stderr: bool = True,
        tolerance_rad_s: Optional[float] = None,
        use_weighted_loss: bool = False,
        eps: float = 1.0e-12,
    ) -> Dict[str, object]:
        """Run fixed-omega validation-style replay and return grouped fit summary."""
        result = self.replay_measured(
            back_action_coherence=back_action_coherence,
            control_omega_source=control_omega_source,
            include_photon_noise=include_photon_noise,
            update_raman_frequency=update_raman_frequency,
            update_rabi_frequency=update_rabi_frequency,
            return_full_state=False,
        )

        if tolerance_rad_s is None:
            groups = self.grouped_average(result, use_stderr=use_stderr)
        else:
            groups = self.average_by_omega_group(result, use_stderr=use_stderr, tolerance_rad_s=tolerance_rad_s)

        fit_metrics = self.compute_group_fit_metrics(groups, use_weighted_loss=use_weighted_loss, eps=eps)
        return {
            "result": result,
            "groups": groups,
            "fit": fit_metrics,
            "mode": "validation",
            "control_omega_source": str(control_omega_source),
        }

    def replay_feedback_mode(
        self,
        *,
        back_action_coherence: Optional[float] = None,
        control_omega_source: str = "measured",
        include_photon_noise: Optional[bool] = None,
        update_raman_frequency: Optional[bool] = None,
        update_rabi_frequency: bool = False,
        return_full_state: bool = False,
        use_stderr: bool = True,
        tolerance_rad_s: Optional[float] = None,
    ) -> Dict[str, object]:
        """Run feedback-enabled replay and return posterior-ready summary payload."""
        result = self.replay_measured(
            back_action_coherence=back_action_coherence,
            control_omega_source=control_omega_source,
            include_photon_noise=include_photon_noise,
            update_raman_frequency=update_raman_frequency,
            update_rabi_frequency=update_rabi_frequency,
            return_full_state=return_full_state,
        )

        if tolerance_rad_s is None:
            groups = self.grouped_average(result, use_stderr=use_stderr)
        else:
            groups = self.average_by_omega_group(result, use_stderr=use_stderr, tolerance_rad_s=tolerance_rad_s)

        return {
            "result": result,
            "groups": groups,
            "mode": "feedback",
            "control_omega_source": str(control_omega_source),
            "zidx": int(result.zidx),
            "posterior_rrm": result.P0_rr,
        }

    def sweep_replay_parameter(
        self,
        parameter_name: str,
        values: Sequence[float],
        *,
        replay_kwargs: Optional[Dict[str, object]] = None,
        tolerance_rad_s: Optional[float] = None,
        include_apd_noise: Optional[bool] = None,
        apd_noise_override_fraction: Optional[float] = None,
        apd_noise_min_std: float = 0.03,
        aggregate_mode: str = "point_weighted",
        n_jobs: int = 1,
        parallel_verbose: int = 0,
        eps: float = 1.0e-12,
    ) -> Dict[str, object]:
        """Sweep one replay parameter and rank fits against APD data via per-omega-group metrics.

        For each parameter value, groups repeats by omega sequence similarity and computes
        per-group MSE, then returns the average MSE.

        **Automatic behavior:**
        - **Validation runs** (deterministic omega, all repeats same): 1 omega group → 1 MSE
        - **Feedback runs** (varying omega per shot): N omega groups (one per unique omega) → avg of N MSEs

        The grouping is automatic: use `tolerance_rad_s` to control tightness.
        - Small tolerance: tight grouping (feedback: closer to 1 group per shot)
        - Large tolerance: loose grouping (validation: all together)
        - None (default): uses `self.omega_group_tolerance_rad_s`

        Parameters
        ----------
        parameter_name
            Parameter to sweep (e.g., 'back_action_coherence'). Must be a
            keyword argument accepted by replay_measured(...).
        values
            Sequence of parameter values to evaluate.
        replay_kwargs
            Additional keyword arguments passed to replay_measured(...).
        tolerance_rad_s
            Omega grouping tolerance (rad/s). Controls how similar two omega sequences
            must be to be considered the same group. If None, uses class default.
            Tighter (smaller) → more groups. For feedback with unique omegas per shot,
            use small tolerance to get one group per shot.
        include_apd_noise
                        Global APD-noise flag for fit weighting.
                        If None (default), APD noise is enabled in principle and then filtered
                        by per-group shot count in fit evaluation.
                        If True, APD noise is enabled for singleton groups only.
                        If False, APD noise is disabled for all groups.
        apd_noise_override_fraction
            Optional override for APD noise fraction (std_photons / N_photons).
            If provided, use this value instead of extracting from calibration.
            Only used when APD noise weighting is enabled.
        apd_noise_min_std
            Minimum APD uncertainty floor on normalized APD scale for
            APD-noise weighting.
        aggregate_mode
            Group-loss aggregation mode passed to
            compute_group_fit_metrics_with_noise(...).
        n_jobs
            Number of cores for parallel shot simulation within each replay.
            Default 1 (sequential). Use -1 for all cores.
        parallel_verbose
            Verbosity level for joblib parallel execution (0-10).
        eps
            Small positive number for numerical stability.

        Returns
        -------
        dict
            Keys: parameter_name, values, losses (MSE per sweep point),
            records, best_index, best_value, best_result, best_groups, best_fit,
            replay_kwargs, fit_mode ('omega_group').
        """
        if replay_kwargs is None:
            replay_kwargs = {}

        value_list = [float(value) for value in values]
        if len(value_list) == 0:
            raise ValueError("values must contain at least one entry.")

        records: List[Dict[str, object]] = []

        for value in value_list:
            kwargs = dict(replay_kwargs)
            kwargs[parameter_name] = float(value)
            kwargs["n_jobs"] = int(n_jobs)
            kwargs["parallel_verbose"] = int(parallel_verbose)

            result = self.replay_measured(**kwargs)

            # Per-omega-group fitting: naturally handles validation (1 group) and feedback (N groups)
            fit_metrics = self.compute_group_fit_metrics_with_noise(
                result,
                include_apd_noise=include_apd_noise,
                apd_noise_override_fraction=apd_noise_override_fraction,
                apd_noise_min_std=apd_noise_min_std,
                aggregate_mode=aggregate_mode,
                tolerance_rad_s=tolerance_rad_s,
                eps=eps,
            )
            groups = self.average_by_omega_group(
                result, use_stderr=True, tolerance_rad_s=tolerance_rad_s
            )

            records.append(
                {
                    parameter_name: float(value),
                    "result": result,
                    "groups": groups,
                    "fit": fit_metrics,
                }
            )

        losses = np.asarray([record["fit"]["overall_mse"] for record in records], dtype=float)
        if not np.isfinite(losses).any():
            raise RuntimeError(f"All sweep losses are non-finite for parameter {parameter_name!r}.")

        best_idx = int(np.nanargmin(losses))
        best_record = records[best_idx]

        return {
            "parameter_name": str(parameter_name),
            "values": np.asarray(value_list, dtype=float),
            "losses": losses,
            "records": records,
            "best_index": int(best_idx),
            "best_value": float(best_record[parameter_name]),
            "best_result": best_record["result"],
            "best_groups": best_record["groups"],
            "best_fit": best_record["fit"],
            "replay_kwargs": dict(replay_kwargs),
            "fit_mode": "omega_group",
            "include_apd_noise": include_apd_noise,
            "apd_noise_min_std": float(apd_noise_min_std),
            "aggregate_mode": str(aggregate_mode),
            "tolerance_rad_s": tolerance_rad_s,
        }

    def plot_sz_vs_apd(
        self,
        result: FeedbackReplayResult,
        *,
        grouped_average: bool = True,
        use_stderr: bool = True,
        ax=None,
    ) -> Tuple[plt.Figure, plt.Axes]:
        """Plot simulation s_z against normalized APD, grouped when appropriate."""
        if ax is None:
            fig, ax = plt.subplots(figsize=(7, 4))
        else:
            fig = ax.figure

        color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", ["C0"])

        if grouped_average:
            groups = self.average_by_omega_group(result, use_stderr=use_stderr)
            for gidx, group in enumerate(groups):
                t = group["t_s_z"]
                color = color_cycle[gidx % len(color_cycle)]
                ax.scatter(
                    t,
                    group["apd_norm_mean"],
                    s=18,
                    alpha=0.85,
                    color=color,
                    label=f"group {gidx} APD",
                )
                ax.plot(
                    t,
                    group["s_z_mean"],
                    "-",
                    lw=1.6,
                    alpha=0.95,
                    color=color,
                    label=f"group {gidx} sim",
                )
        else:
            n_repeat = result.s_z_rr.shape[0]
            for r in range(n_repeat):
                t = result.t_s_z_rr[r]
                color = color_cycle[r % len(color_cycle)]
                ax.scatter(t, result.apd_norm_rr[r], s=12, alpha=0.55, color=color)
                ax.plot(t, result.s_z_rr[r], "-", lw=1.3, alpha=0.8, color=color)

            ax.scatter([], [], s=18, label="normalized APD")
            ax.plot([], [], "-", label="simulated s_z")

        run_id = int(result.metadata.get("run_id", -1))
        ax.set_title(f"run {run_id}: normalized APD vs simulated s_z")
        ax.set_xlabel("time (s)")
        ax.set_ylabel("spin-like value")
        ax.grid(alpha=0.25)
        return fig, ax

    def plot_omega_feedback_comparison(
        self,
        result: FeedbackReplayResult,
        *,
        grouped_average: bool = True,
        control_lag_steps: int = 0,
        recomputed_lag_steps: int = 1,
        ax=None,
    ) -> Tuple[plt.Figure, plt.Axes]:
        """Compare control omega used in experiment vs recomputed omega on pulse index."""
        if ax is None:
            fig, ax = plt.subplots(figsize=(7, 4))
        else:
            fig = ax.figure

        color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", ["C0"])

        f0 = float(getattr(self.ad.p, "frequency_raman_transition", 0.0))
        f_rabi = 1.0 / (2.0 * float(self.ad.p.t_raman_pi_pulse))

        def _lag_xy(x: np.ndarray, y: np.ndarray, lag_steps: int) -> Tuple[np.ndarray, np.ndarray]:
            lag = int(lag_steps)
            if lag == 0:
                return x, y
            if abs(lag) >= len(x):
                return np.asarray([], dtype=float), np.asarray([], dtype=float)
            if lag > 0:
                return x[lag:], y[:-lag]
            return x[:lag], y[-lag:]

        if grouped_average:
            groups = self.average_by_omega_group(result, use_stderr=True)
            for gidx, group in enumerate(groups):
                pulse_idx = np.arange(len(group["omega_control_mean"]), dtype=float)
                ctrl = (group["omega_control_mean"] / (2.0 * np.pi) - f0) / f_rabi
                rec = (group["omega_recomputed_mean"] / (2.0 * np.pi) - f0) / f_rabi
                color = color_cycle[gidx % len(color_cycle)]
                x_ctrl, ctrl_plot = _lag_xy(pulse_idx, np.asarray(ctrl, dtype=float), int(control_lag_steps))
                x_rec, rec_plot = _lag_xy(pulse_idx, np.asarray(rec, dtype=float), int(recomputed_lag_steps))
                ax.scatter(x_ctrl, ctrl_plot, s=18, alpha=0.85, color=color)
                ax.plot(x_rec, rec_plot, "-", lw=1.6, alpha=0.95, color=color)
        else:
            n_repeat = result.omega_control_rr.shape[0]
            for r in range(n_repeat):
                pulse_idx = np.arange(result.omega_control_rr.shape[1], dtype=float)
                ctrl = (result.omega_control_rr[r] / (2.0 * np.pi) - f0) / f_rabi
                rec = (result.omega_recomputed_rr[r] / (2.0 * np.pi) - f0) / f_rabi
                color = color_cycle[r % len(color_cycle)]
                x_ctrl, ctrl_plot = _lag_xy(pulse_idx, np.asarray(ctrl, dtype=float), int(control_lag_steps))
                x_rec, rec_plot = _lag_xy(pulse_idx, np.asarray(rec, dtype=float), int(recomputed_lag_steps))
                ax.scatter(x_ctrl, ctrl_plot, s=12, alpha=0.55, color=color)
                ax.plot(x_rec, rec_plot, "-", lw=1.3, alpha=0.8, color=color)

        legend_handles = [
            plt.Line2D([], [], color="0.55", marker="o", linestyle="None", markersize=5, label="Experiment shot"),
            plt.Line2D([], [], color="0.20", linestyle="-", lw=1.8, label="Recomputed"),
        ]

        run_id = int(result.metadata.get("run_id", -1))
        ax.set_title(f"run {run_id}: omega control vs recomputed (pulse index, ctrl lag={control_lag_steps}, rec lag={recomputed_lag_steps})")
        ax.set_xlabel("pulse index")
        ax.set_ylabel("detuning / Omega")
        ax.grid(alpha=0.25)
        ax.legend(handles=legend_handles, loc="best")
        return fig, ax

    def plot_probability_comparison(
        self,
        result: FeedbackReplayResult,
        *,
        repeat_idx: int = 0,
        log_scale: bool = True,
        normalize_after: int = 0,
        cmap: str = "viridis",
    ) -> Tuple[plt.Figure, np.ndarray]:
        """Side-by-side 2D maps: experiment probabilities vs recomputed posterior."""
        if repeat_idx < 0 or repeat_idx >= result.P0_rr.shape[0]:
            raise ValueError(f"repeat_idx {repeat_idx} out of range for N_repeat={result.P0_rr.shape[0]}.")

        exp_probs = None
        exp_probs_label = "experiment probabilities reconstructed from measured APD"
        if hasattr(self.ad.p, "probabilities"):
            probs = np.asarray(self.ad.p.probabilities)
            if probs.ndim == 3:
                exp_probs = np.asarray(probs[repeat_idx], dtype=float).T
                exp_probs_label = "experiment ad.p.probabilities"
            elif probs.ndim == 2:
                exp_probs = np.asarray(probs, dtype=float).T
                exp_probs_label = "experiment ad.p.probabilities"
        if exp_probs is None:
            exp_probs = np.asarray(result.P0_rr[repeat_idx], dtype=float).T

        sim_probs = np.asarray(result.P0_rr[repeat_idx], dtype=float).T

        n_omega_bins = sim_probs.shape[0]
        n_pulses = sim_probs.shape[1]

        omega_guess_hz = np.asarray(result.omega_guess_list, dtype=float) / (2.0 * np.pi)
        detuning_hz = omega_guess_hz - float(self.ad.p.frequency_raman_transition)
        f_rabi = 1.0 / (2.0 * float(self.ad.p.t_raman_pi_pulse))
        detuning_over_omega = detuning_hz / f_rabi

        if len(detuning_over_omega) != n_omega_bins:
            n = min(len(detuning_over_omega), n_omega_bins)
            detuning_over_omega = detuning_over_omega[:n]
            sim_probs = sim_probs[:n]
            n_omega_bins = n
            if exp_probs is not None:
                exp_probs = exp_probs[:n, :]

        if n_omega_bins == 1:
            y_edges = np.array([detuning_over_omega[0] - 0.5, detuning_over_omega[0] + 0.5], dtype=float)
        else:
            y_mid = 0.5 * (detuning_over_omega[1:] + detuning_over_omega[:-1])
            y_first = detuning_over_omega[0] - (y_mid[0] - detuning_over_omega[0])
            y_last = detuning_over_omega[-1] + (detuning_over_omega[-1] - y_mid[-1])
            y_edges = np.concatenate(([y_first], y_mid, [y_last]))

        x_edges = np.arange(n_pulses + 1)

        norm_region_sim = sim_probs[:, normalize_after:] if n_pulses > normalize_after else sim_probs
        all_for_norm = norm_region_sim if exp_probs is None else np.concatenate(
            [
                norm_region_sim.ravel(),
                np.asarray(exp_probs[:, normalize_after:] if n_pulses > normalize_after else exp_probs).ravel(),
            ]
        )

        if log_scale:
            positive = all_for_norm[all_for_norm > 0]
            vmin = float(np.min(positive)) if positive.size > 0 else 1.0e-12
            vmax = float(np.max(all_for_norm)) if all_for_norm.size > 0 else vmin * 10.0
            if vmax <= vmin:
                vmax = vmin * 10.0
            norm = mcolors.LogNorm(vmin=vmin, vmax=vmax)
            cb_label = "probability (log)"
        else:
            vmin = float(np.nanmin(all_for_norm)) if all_for_norm.size > 0 else 0.0
            vmax = float(np.nanmax(all_for_norm)) if all_for_norm.size > 0 else 1.0
            if vmax <= vmin:
                vmax = vmin + 1.0
            norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
            cb_label = "probability"

        fig, axs = plt.subplots(1, 2, figsize=(12, 4), sharex=True, sharey=True, layout="constrained")

        if exp_probs is not None:
            axs[0].pcolormesh(x_edges, y_edges, exp_probs, shading="auto", cmap=cmap, norm=norm)
            axs[0].set_title(exp_probs_label)

        im1 = axs[1].pcolormesh(x_edges, y_edges, sim_probs, shading="auto", cmap=cmap, norm=norm)
        axs[1].set_title("recomputed replay posterior")

        for ax in axs:
            ax.axhline(0.0, color="red", linestyle="--", linewidth=1.0, alpha=0.7)
            if normalize_after > 0:
                ax.axvline(normalize_after, color="red", linestyle="--", linewidth=1.0, alpha=0.7)
            ax.set_xlabel("pulse index")

        axs[0].set_ylabel("detuning / Omega")

        run_id = int(result.metadata.get("run_id", -1))
        fig.suptitle(f"run {run_id}: probability comparison (repeat {repeat_idx})")
        cbar = fig.colorbar(im1, ax=axs, shrink=0.95)
        cbar.set_label(cb_label)

        return fig, axs
