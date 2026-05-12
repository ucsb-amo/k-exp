from artiq.experiment import kernel, portable, TInt64
import numpy as np
from numpy import int64
from kexp.calibrations.imaging import integrator_calibration, imaging_lightshift
from kexp.util.artiq.async_print import aprint

class _FeedbackParamStore:
    """Attribute bag used when Feedback is instantiated outside Base."""


class Feedback:
    kernel_invariants = {
        "m",
        "dt_eff",
        "dt_ideal",
        "dt_z",
        # "omega_z_lightshift",
        "omega_guess_start",
        "N_photons_per_shot",
        "std_n_photons_per_shot",
        "v_apd_all_up",
        "v_apd_all_down",
        "v_range",
        "omega_guess_list",
        "omega_sq_list",
        "feedback_measurement_midpoint_fraction",
        "feedback_measurement_midpoint_remap_enabled",
        "sin_lut",
        "lut_size",
        "lut_scale",
        "lut_mask",
        "lut_quarter",
        "two_pi",
        "pi_half",
        "inv_two_pi",
    }

    def __init__(
        self,
        t_raman_pulse=None,
        t_raman_pulse_ideal=None,
        dt_eff=None,
        dt_ideal=None,
        t_img_pulse=None,
        amp_imaging=None,
        t_raman_pi_pulse=None,
        frequency_resonance=None,
        frequency_z_lightshift=None,
        v_apd_all_up=None,
        v_apd_all_down=None,
        n_photons_per_shot=None,
        std_n_photons_per_shot=None,
        back_action_coherence=None,
        photon_count_scale=1.0,
        feedback_grid_size=21,
        m=None,
        fractional_grid_center_offset=2.0,
        fractional_initial_offset=-5.0,
        guess_span_Omega=5.0,
        feedback_measurement_midpoint_fraction=None,
        feedback_measurement_midpoint_remap_enabled=None,
        feedback_apd_map_enabled=None,
        feedback_apd_map_a=None,
        feedback_apd_map_b=None,
        feedback_apd_map_verbose=None,
        lut_size=4096):

        if not hasattr(self, "p"):
            self.p = _FeedbackParamStore()

        resolved_feedback_grid_size = feedback_grid_size if m is None else m

        self._initialize_timing(
            feedback_grid_size=resolved_feedback_grid_size,
            t_raman_pulse=t_raman_pulse,
            t_raman_pulse_ideal=t_raman_pulse_ideal,
            dt_eff=dt_eff,
            dt_ideal=dt_ideal,
            t_img_pulse=t_img_pulse,
            t_raman_pi_pulse=t_raman_pi_pulse,
        )
        self._initialize_lightshift(
            amp_imaging=amp_imaging,
            frequency_z_lightshift=frequency_z_lightshift,
            back_action_coherence=back_action_coherence
        )
        self._initialize_frequency_grid(
            frequency_resonance=frequency_resonance,
            fractional_grid_center_offset=fractional_grid_center_offset,
            fractional_initial_offset=fractional_initial_offset,
            guess_span_Omega=guess_span_Omega,
        )
        self._initialize_measurement_calibrations(
            amp_imaging=amp_imaging,
            t_img_pulse=t_img_pulse,
            n_photons_per_shot=n_photons_per_shot,
            std_n_photons_per_shot=std_n_photons_per_shot,
            v_apd_all_up=v_apd_all_up,
            v_apd_all_down=v_apd_all_down,
            photon_count_scale=photon_count_scale,
            feedback_measurement_midpoint_fraction=feedback_measurement_midpoint_fraction,
            feedback_measurement_midpoint_remap_enabled=feedback_measurement_midpoint_remap_enabled,
            feedback_apd_map_enabled=feedback_apd_map_enabled,
            feedback_apd_map_a=feedback_apd_map_a,
            feedback_apd_map_b=feedback_apd_map_b,
            feedback_apd_map_verbose=feedback_apd_map_verbose,
        )
        self._initialize_posterior_state()
        self._initialize_trig_lut(lut_size=lut_size)

    @portable(flags={"fast-math"})
    def convert_measurement(self, v_apd):
        return round(self.N_photons_per_shot * (v_apd - self.v_apd_all_down) / self.v_range)

    @portable(flags={"fast-math"})
    def expected_photon_fraction(self, hz):
        if not self.feedback_measurement_midpoint_remap_enabled:
            p1 = 0.5 * (1.0 + hz)
            if p1 < 0.0:
                return 0.0
            if p1 > 1.0:
                return 1.0
            return p1

        midpoint = self.feedback_measurement_midpoint_fraction
        p1 = 0.5 * (1.0 + hz) + (midpoint - 0.5) * (1.0 - hz * hz)
        if p1 < 0.0:
            return 0.0
        if p1 > 1.0:
            return 1.0
        return p1

    @portable(flags={"fast-math"})
    def measurement_photon_fraction_from_apd(self, v_apd):
        photon_fraction = (v_apd - self.v_apd_all_down) / self.v_range
        if photon_fraction < 0.0:
            return 0.0
        if photon_fraction > 1.0:
            return 1.0
        return photon_fraction

    @portable(flags={"fast-math"})
    def spin_value_from_photon_fraction(self, photon_fraction, feedback_measurement_midpoint_remap_enabled=None):
        if feedback_measurement_midpoint_remap_enabled is None:
            use_midpoint_remap = self.feedback_measurement_midpoint_remap_enabled
        else:
            use_midpoint_remap = bool(feedback_measurement_midpoint_remap_enabled)

        p1 = photon_fraction
        if p1 < 0.0:
            p1 = 0.0
        elif p1 > 1.0:
            p1 = 1.0

        if not use_midpoint_remap:
            return 2.0 * p1 - 1.0

        midpoint = self.feedback_measurement_midpoint_fraction
        delta = midpoint - 0.5
        if abs(delta) < 1.0e-15:
            return 2.0 * p1 - 1.0

        discriminant = 0.25 - 4.0 * delta * (p1 - midpoint)
        if discriminant < 0.0:
            discriminant = 0.0

        hz = (0.5 - np.sqrt(discriminant)) / (2.0 * delta)
        if hz < -1.0:
            return -1.0
        if hz > 1.0:
            return 1.0
        return hz

    @portable(flags={"fast-math"})
    def spin_value_from_apd(self, v_apd, feedback_measurement_midpoint_remap_enabled=None):
        photon_fraction = self.measurement_photon_fraction_from_apd(v_apd)
        return self.spin_value_from_photon_fraction(
            photon_fraction,
            feedback_measurement_midpoint_remap_enabled=feedback_measurement_midpoint_remap_enabled,
        )

    @portable(flags={"fast-math"})
    def generate_posterior(self,
                           k, t,
                           phase_raman_pulse_start=0.,
                           update_raman_frequency=1,
                           update_rabi_frequency=0,
                           include_photon_noise=1):
        P0_total = 0.0
        moment_2 = 0.0
        mn = 0.0

        omega_guess_list = self.omega_guess_list
        omega_sq_list = self.omega_sq_list
        state_x = self.state_x
        state_y = self.state_y
        state_z = self.state_z
        P0 = self.P0

        

        m = self.m
        n_photons = int(self.N_photons_per_shot)

        omega_raman = self.omega_raman
        Omega = self.Omega
        Omega_sq = Omega * Omega

        dt_eff = self.dt_eff
        dt_ideal = self.dt_ideal
        
        dt_z = self.dt_z

        if include_photon_noise:
            sigma = self.std_n_photons_per_shot
            sigma_sq = sigma * sigma
        else:
            sigma = 0.
            sigma_sq = 0.

        if m > 1:
            domega = omega_guess_list[1] - omega_guess_list[0]
        else:
            domega = 0.0

        omega0 = omega_guess_list[0]

        phi = phase_raman_pulse_start - omega0*t
        delta_omega0 = omega0 - omega_raman

        (sin_wt, cos_wt) = self.sincos_lut_interp(phi) # continuous mode
        # (sin_wt, cos_wt) = self.sincos_lut_interp(-delta_omega0 * t) # from tracking mode
        (sin_wt_step, cos_wt_step) = self.sincos_lut_interp(-domega * t)

        alpha_z_lightshift = self.omega_z_lightshift * dt_z
        alpha_z = dt_eff * delta_omega0 - alpha_z_lightshift # dt actual pulse time
        (sin_z, cos_z) = self.sincos_lut_interp(alpha_z)
        alpha_z_step = dt_eff * domega # dt actual pulse time
        (sin_z_step, cos_z_step) = self.sincos_lut_interp(alpha_z_step)

        k_int = int(k)
        if k_int < 0:
            k_int = 0
        if k_int > n_photons:
            k_int = n_photons
        nk_int = n_photons - k_int

        j = 0
        while j < m:
            omega = omega_guess_list[j]
            delta_omega = omega_raman - omega

            norm_H = np.sqrt(Omega_sq + delta_omega * delta_omega)
            if norm_H > 0.0:
                inv_norm_H = 1.0 / norm_H
                Omega_over_H = Omega * inv_norm_H
                u_z = delta_omega * inv_norm_H
                (sin_H, cos_H) = self.sincos_lut_interp(-dt_ideal * norm_H) # dt ideal pulse time
            else:
                Omega_over_H = 0.0
                u_z = 0.0
                sin_H = 0.0
                cos_H = 1.0

            sx = state_x[j]
            sy = state_y[j]
            sz = state_z[j]

            u_x = Omega_over_H * cos_wt
            u_y = Omega_over_H * sin_wt

            one_minus_cos = 1.0 - cos_H

            uxux = u_x * u_x
            uyuy = u_y * u_y
            uzuz = u_z * u_z
            uxuy = u_x * u_y
            uxuz = u_x * u_z
            uyuz = u_y * u_z

            hx = (cos_H + one_minus_cos * uxux) * sx
            hx += (one_minus_cos * uxuy - sin_H * u_z) * sy
            hx += (one_minus_cos * uxuz + sin_H * u_y) * sz

            hy = (one_minus_cos * uxuy + sin_H * u_z) * sx
            hy += (cos_H + one_minus_cos * uyuy) * sy
            hy += (one_minus_cos * uyuz - sin_H * u_x) * sz

            hz = (one_minus_cos * uxuz - sin_H * u_y) * sx
            hz += (one_minus_cos * uyuz + sin_H * u_x) * sy
            hz += (cos_H + one_minus_cos * uzuz) * sz

            nx = cos_z * hx + sin_z * hy
            ny = -sin_z * hx + cos_z * hy

            state_x[j] = nx * self.back_action_coherence
            state_y[j] = ny * self.back_action_coherence
            state_z[j] = hz

            p1 = self.expected_photon_fraction(hz)
            q = 1.0 - p1
            npq = n_photons * p1 * q + sigma_sq
            num = k - n_photons * p1
            if include_photon_noise:
                f = sigma / np.sqrt(npq) * np.exp(-num * num / (2.0 * npq))
                pj = P0[j] * f
            else:
                p1_pow = self.powi(p1, k_int)
                q_pow = self.powi(q, nk_int)
                pj = P0[j] * p1_pow * q_pow                

            P0_total += pj
            mn += pj * omega
            moment_2 += pj * omega_sq_list[j]

            P0[j] = pj

            next_sin_wt = sin_wt * cos_wt_step + cos_wt * sin_wt_step
            next_cos_wt = cos_wt * cos_wt_step - sin_wt * sin_wt_step
            sin_wt = next_sin_wt
            cos_wt = next_cos_wt

            next_sin_z = sin_z * cos_z_step + cos_z * sin_z_step
            next_cos_z = cos_z * cos_z_step - sin_z * sin_z_step
            sin_z = next_sin_z
            cos_z = next_cos_z

            j += 1

        if P0_total <= 0.0:
            return self.omega_raman, self.Omega

        mn = mn / P0_total
        moment_2 = moment_2 / P0_total

        i = 0
        while i < len(P0):
            P0[i] = P0[i] / P0_total
            i += 1

        total = 0.
        for i in range(len(P0)):
            total += P0[i]
        
        self.P0_total = P0_total
        var = moment_2 - mn * mn
        if var < 0.0:
            var = 0.0
        std = np.sqrt(var)

        if not update_raman_frequency:
            mn = self.omega_raman
        if not update_rabi_frequency:
            std = self.Omega

        return mn, std
    
    @portable(flags={"fast-math"})
    def compute_t_between_pulses_mu(
        self,
        t_calculation_slack_compensation_mu,
        t_raman_pulse,
        t_img_pulse,
        t_fifo_mu = int64(1000)
    ) -> TInt64:
        T_MIN_FIFO_MU = t_fifo_mu
        t_raman_pulse_mu = np.int64(t_raman_pulse * 1.0e9)
        t_img_pulse_mu = np.int64(t_img_pulse * 1.0e9)
        return (
            t_calculation_slack_compensation_mu
            + t_raman_pulse_mu
            + t_img_pulse_mu
            + T_MIN_FIFO_MU
        ) & ~7

    @kernel
    def initialize_feedback(self):
        """Warm up posterior runtime once, then reset state/P0 arrays."""

        n_test = int(round(self.N_photons_per_shot * self.expected_photon_fraction(0.0)))

        self.core.wait_until_mu(self.core.get_rtio_counter_mu())
        self.generate_posterior(n_test, 1.0e-6)
        self.core.break_realtime()

        t0 = self.core.get_rtio_counter_mu()
        self.core.wait_until_mu(t0)
        self.generate_posterior(n_test, 1.0e-6)
        self.t_posterior_mu = abs(t0 - self.core.get_rtio_counter_mu())
        self.core.break_realtime()
        aprint('calculation esimated slack consumption:', self.t_posterior_mu)
        
        self.reset_feedback_state()

    @portable(flags={"fast-math"})
    def reset_feedback_state(self):
        i = 0
        while i < self.m:
            self.state_x[i] = 0.0
            self.state_y[i] = 0.0
            self.state_z[i] = 1.0
            self.P0[i] = 1.0 / self.m
            i += 1
        self.P0_total = 1.0

    @portable(flags={"fast-math"})
    def reset_initial_omega_from_params(self):
        """Refresh initial control omega from current (possibly scanned) params."""
        self.omega_raman = (
            2.0 * np.pi * self.p.frequency_raman_transition
            + self.Omega * self.p.feedback_fractional_initial_offset
        )
        return self.omega_raman

    def _initialize_timing(
        self,
        feedback_grid_size,
        t_raman_pulse,
        t_raman_pulse_ideal,
        dt_eff,
        dt_ideal,
        t_img_pulse,
        t_raman_pi_pulse,
    ):
        self.p.feedback_grid_size = int(feedback_grid_size)
        self.m = self.p.feedback_grid_size
        self.Omega = np.pi / t_raman_pi_pulse

        # Accept either legacy t_raman_* names or explicit dt_* names.
        resolved_dt_eff = t_raman_pulse if t_raman_pulse is not None else dt_eff
        if resolved_dt_eff is None:
            raise ValueError("Missing t_raman_pulse/dt_eff required for feedback timing.")

        resolved_dt_ideal = t_raman_pulse_ideal if t_raman_pulse_ideal is not None else dt_ideal
        if resolved_dt_ideal is None:
            # Backward compatibility: if ideal timing is not provided, use effective timing.
            resolved_dt_ideal = resolved_dt_eff

        self.dt_eff = float(resolved_dt_eff)
        self.dt_ideal = float(resolved_dt_ideal)
        self.dt_z = float(t_img_pulse)

    def _initialize_lightshift(
        self,
        amp_imaging,
        frequency_z_lightshift,
        back_action_coherence=None
    ):
        self.p.frequency_lightshift = self._resolve_lightshift_calibration(
            amp_imaging=amp_imaging,
            frequency_z_lightshift=frequency_z_lightshift,
        )
        self.frequency_z_lightshift = self.p.frequency_lightshift
        self.omega_z_lightshift = 2.0 * np.pi * self.frequency_z_lightshift

        if back_action_coherence is not None:
            self.p.back_action_coherence = back_action_coherence
        self.back_action_coherence = self.p.back_action_coherence

    def _initialize_frequency_grid(
        self,
        frequency_resonance,
        fractional_grid_center_offset,
        fractional_initial_offset,
        guess_span_Omega,
    ):
        omega_resonance = 2.0 * np.pi * float(frequency_resonance)
        self.p.feedback_fractional_grid_center_offset_requested = float(fractional_grid_center_offset)
        self.p.feedback_fractional_initial_offset = float(fractional_initial_offset)
        self.p.feedback_guess_span_Omega_requested = float(guess_span_Omega)

        if self.m < 1:
            raise ValueError("feedback_grid_size must be >= 1.")
        if self.p.feedback_guess_span_Omega_requested < 0.0:
            raise ValueError("guess_span_Omega must be non-negative.")

        self.omega_guess_list, resonance_idx, span_effective = self._construct_span_adjusted_grid(
            omega_resonance=omega_resonance,
            fractional_grid_center_offset_requested=self.p.feedback_fractional_grid_center_offset_requested,
            guess_span_Omega_requested=self.p.feedback_guess_span_Omega_requested,
            fractional_initial_offset=self.p.feedback_fractional_initial_offset,
        )
        self.p.feedback_guess_span_Omega = float(span_effective)
        self.p.feedback_resonance_grid_index = int(resonance_idx)

        self.omega_grid_center = 0.5 * (self.omega_guess_list[0] + self.omega_guess_list[-1])
        if self.Omega != 0.0:
            self.p.feedback_fractional_grid_center_offset = float((self.omega_grid_center - omega_resonance) / self.Omega)
        else:
            self.p.feedback_fractional_grid_center_offset = 0.0

        if abs(self.p.feedback_guess_span_Omega - self.p.feedback_guess_span_Omega_requested) > 1.0e-12:
            print(
                "Feedback: adjusted guess_span_Omega to keep resonance on-grid. "
                f"requested={self.p.feedback_guess_span_Omega_requested:.6g}, "
                f"effective={self.p.feedback_guess_span_Omega:.6g}."
            )

        self.omega_guess_start = omega_resonance + self.Omega * self.p.feedback_fractional_initial_offset
        self._validate_resonance_in_grid(omega_resonance=omega_resonance)
        self._validate_initial_guess_in_grid()
        self.p.omega_guess_list = self.omega_guess_list
        self.omega_raman = self.omega_guess_start
        self.omega_sq_list = self.omega_guess_list * self.omega_guess_list

    def _construct_span_adjusted_grid(
        self,
        omega_resonance,
        fractional_grid_center_offset_requested,
        guess_span_Omega_requested,
        fractional_initial_offset,
    ):
        if self.m == 1:
            return np.asarray([float(omega_resonance)], dtype=np.float64), 0, 0.0

        if self.Omega == 0.0:
            raise ValueError("Omega is zero; cannot construct a feedback hypothesis grid.")

        c = float(fractional_grid_center_offset_requested)
        s_requested = float(guess_span_Omega_requested)
        o = float(fractional_initial_offset)
        mid = 0.5 * (self.m - 1)

        # Keep initial offset fixed: if center is fixed at c, minimum span for coverage is |o-c|/2.
        span_min_from_guess = abs(o - c) / 2.0
        candidates = []
        tiny = 1.0e-15
        for j in range(self.m):
            dj = float(j) - mid

            if abs(dj) <= tiny:
                if abs(c) <= tiny:
                    s_candidate = max(s_requested, span_min_from_guess)
                    candidates.append((j, s_candidate))
                continue

            s_candidate = -c * (self.m - 1) / (4.0 * dj)
            if s_candidate < -tiny:
                continue
            if s_candidate < 0.0:
                s_candidate = 0.0
            if s_candidate + tiny < span_min_from_guess:
                continue

            candidates.append((j, float(s_candidate)))

        if len(candidates) == 0:
            raise ValueError(
                "Cannot construct a uniform feedback grid that keeps fractional_initial_offset and "
                "feedback_grid_size fixed while including exact resonance. "
                f"fractional_initial_offset={o:.6g}, "
                f"fractional_grid_center_offset={c:.6g}, "
                f"feedback_grid_size={self.m}, "
                f"guess_span_Omega_requested={s_requested:.6g}."
            )

        resonance_idx, _ = min(
            candidates,
            key=lambda pair: (abs(pair[1] - s_requested), abs(pair[1]), abs(float(pair[0]) - mid)),
        )

        center_target = float(omega_resonance) + self.Omega * c
        dj_res = float(resonance_idx) - mid
        if abs(dj_res) <= tiny:
            domega = 4.0 * max(s_requested, span_min_from_guess) * self.Omega / (self.m - 1)
        else:
            domega = (float(omega_resonance) - center_target) / dj_res

        if domega < 0.0:
            domega = abs(domega)

        offsets = np.arange(self.m, dtype=np.float64) - float(resonance_idx)
        omega_guess = float(omega_resonance) + domega * offsets
        # Force exact resonance representation at the selected index.
        omega_guess[resonance_idx] = float(omega_resonance)

        span_effective = abs(domega) * (self.m - 1) / (4.0 * self.Omega)
        if span_effective + tiny < span_min_from_guess:
            raise ValueError(
                "Internal inconsistency while constructing feedback grid: computed span is too small "
                "to include the fixed initial offset."
            )
        return omega_guess, int(resonance_idx), float(span_effective)

    def _validate_resonance_in_grid(self, omega_resonance):
        idx = int(np.argmin(np.abs(self.omega_guess_list - omega_resonance)))
        if self.omega_guess_list[idx] != float(omega_resonance):
            raise ValueError(
                "Feedback grid does not include the exact resonance frequency. "
                f"nearest_idx={idx}, "
                f"nearest_value={self.omega_guess_list[idx]:.6e} rad/s, "
                f"omega_resonance={float(omega_resonance):.6e} rad/s, "
                f"delta={float(self.omega_guess_list[idx] - omega_resonance):.6e} rad/s."
            )

    def _validate_initial_guess_in_grid(self):
        omega_guess = np.asarray(self.omega_guess_list, dtype=float).ravel()
        if omega_guess.size == 0:
            raise ValueError("Feedback grid cannot be empty.")

        grid_min = float(np.min(omega_guess))
        grid_max = float(np.max(omega_guess))
        tol = 1.0e-12 * max(1.0, abs(grid_min), abs(grid_max))

        if self.omega_guess_start < (grid_min - tol) or self.omega_guess_start > (grid_max + tol):
            grid_center = 0.5 * (grid_min + grid_max)
            raise ValueError(
                "Feedback initial guess is outside the constructed hypothesis grid. "
                f"omega_guess_start={self.omega_guess_start:.6e} rad/s, "
                f"grid_min={grid_min:.6e} rad/s, "
                f"grid_max={grid_max:.6e} rad/s, "
                f"grid_center={grid_center:.6e} rad/s, "
                f"fractional_initial_offset={self.p.feedback_fractional_initial_offset:.6g}, "
                f"fractional_grid_center_offset={self.p.feedback_fractional_grid_center_offset:.6g}, "
                f"guess_span_Omega={self.p.feedback_guess_span_Omega:.6g}, "
                f"Omega={self.Omega:.6e} rad/s."
            )

    def _initialize_measurement_calibrations(
        self,
        amp_imaging,
        t_img_pulse,
        n_photons_per_shot,
        std_n_photons_per_shot,
        v_apd_all_up,
        v_apd_all_down,
        photon_count_scale,
        feedback_measurement_midpoint_fraction,
        feedback_measurement_midpoint_remap_enabled,
        feedback_apd_map_enabled,
        feedback_apd_map_a,
        feedback_apd_map_b,
        feedback_apd_map_verbose,
    ):
        (
            n_photons_per_shot,
            v_apd_all_up,
            v_apd_all_down,
            std_n_photons_per_shot,
        ) = self._resolve_measurement_calibration(
            amp_imaging=amp_imaging,
            t_img_pulse=t_img_pulse,
            n_photons_per_shot=n_photons_per_shot,
            std_n_photons_per_shot=std_n_photons_per_shot,
            v_apd_all_up=v_apd_all_up,
            v_apd_all_down=v_apd_all_down,
            photon_count_scale=photon_count_scale,
        )

        map_enabled, map_a, map_b, map_verbose = self._resolve_apd_affine_map_settings(
            feedback_apd_map_enabled=feedback_apd_map_enabled,
            feedback_apd_map_a=feedback_apd_map_a,
            feedback_apd_map_b=feedback_apd_map_b,
            feedback_apd_map_verbose=feedback_apd_map_verbose,
        )
        midpoint_remap_enabled = self._resolve_measurement_midpoint_remap_enabled(
            feedback_measurement_midpoint_remap_enabled=feedback_measurement_midpoint_remap_enabled,
        )
        midpoint_fraction = self._resolve_measurement_midpoint_fraction(
            feedback_measurement_midpoint_fraction=feedback_measurement_midpoint_fraction,
        )

        v_apd_all_up_ref = float(v_apd_all_up)
        v_apd_all_down_ref = float(v_apd_all_down)

        self.p.feedback_measurement_midpoint_remap_enabled = midpoint_remap_enabled
        self.p.feedback_measurement_midpoint_fraction = midpoint_fraction
        self.p.feedback_apd_map_enabled = map_enabled
        self.p.feedback_apd_map_a = map_a
        self.p.feedback_apd_map_b = map_b
        self.p.feedback_apd_map_verbose = map_verbose
        self.p.v_apd_all_up_reference = v_apd_all_up_ref
        self.p.v_apd_all_down_reference = v_apd_all_down_ref

        if map_enabled:
            v_apd_all_up, v_apd_all_down = self._apply_apd_affine_map_to_calibration(
                v_apd_all_up=v_apd_all_up_ref,
                v_apd_all_down=v_apd_all_down_ref,
                feedback_apd_map_a=map_a,
                feedback_apd_map_b=map_b,
                feedback_apd_map_verbose=map_verbose,
            )

        self.p.N_photons_per_shot = float(n_photons_per_shot)
        self.p.v_apd_all_up = float(v_apd_all_up)
        self.p.v_apd_all_down = float(v_apd_all_down)
        self.p.std_n_photons_per_shot = float(std_n_photons_per_shot)
        self.p.v_apd_all_up_feedback = self.p.v_apd_all_up
        self.p.v_apd_all_down_feedback = self.p.v_apd_all_down

        self.v_apd_all_up = self.p.v_apd_all_up
        self.v_apd_all_down = self.p.v_apd_all_down
        self.N_photons_per_shot = self.p.N_photons_per_shot
        self.std_n_photons_per_shot = self.p.std_n_photons_per_shot
        self.feedback_measurement_midpoint_remap_enabled = self.p.feedback_measurement_midpoint_remap_enabled
        self.feedback_measurement_midpoint_fraction = self.p.feedback_measurement_midpoint_fraction
        self.v_range = self.v_apd_all_up - self.v_apd_all_down
        if abs(self.v_range) < 1.0e-15:
            raise ValueError("APD calibration range is zero; cannot normalize APD.")

    def _resolve_measurement_midpoint_remap_enabled(
        self,
        feedback_measurement_midpoint_remap_enabled,
    ):
        midpoint_remap_enabled = (
            getattr(self.p, "feedback_measurement_midpoint_remap_enabled", True)
            if feedback_measurement_midpoint_remap_enabled is None
            else feedback_measurement_midpoint_remap_enabled
        )
        return bool(midpoint_remap_enabled)

    def _resolve_measurement_midpoint_fraction(
        self,
        feedback_measurement_midpoint_fraction,
    ):
        midpoint_fraction = (
            getattr(self.p, "feedback_measurement_midpoint_fraction", 0.5)
            if feedback_measurement_midpoint_fraction is None
            else feedback_measurement_midpoint_fraction
        )
        midpoint_fraction = float(midpoint_fraction)
        if not np.isfinite(midpoint_fraction):
            raise ValueError("feedback_measurement_midpoint_fraction must be finite.")
        if midpoint_fraction < 0.0 or midpoint_fraction > 1.0:
            raise ValueError(
                "feedback_measurement_midpoint_fraction must be between 0 and 1 inclusive."
            )
        return midpoint_fraction

    def _initialize_posterior_state(self):
        self.P0 = np.ones(self.m, dtype=np.float64)
        self.P0 = self.P0 / np.sum(self.P0)
        self.P0_total = 1.0

        self.state_x = np.zeros(self.m, dtype=np.float64)
        self.state_y = np.zeros(self.m, dtype=np.float64)
        self.state_z = np.ones(self.m, dtype=np.float64)
        self.t_posterior_mu = np.int64(0)

    def _initialize_trig_lut(self, lut_size):
        self.two_pi = 2.0 * np.pi
        self.pi_half = 0.5 * np.pi

        self.lut_size = int(lut_size)
        self.lut_scale = self.lut_size / self.two_pi
        self.lut_mask = self.lut_size - 1
        self.lut_quarter = self.lut_size // 4
        self.inv_two_pi = 1.0 / self.two_pi
        self.sin_lut = np.sin(self.two_pi * np.arange(self.lut_size) / self.lut_size)

    def _resolve_measurement_calibration(
        self,
        amp_imaging,
        t_img_pulse,
        n_photons_per_shot,
        std_n_photons_per_shot,
        v_apd_all_up,
        v_apd_all_down,
        photon_count_scale,
    ):
        missing_fields = []
        if n_photons_per_shot is None:
            missing_fields.append("n_photons_per_shot")
        if v_apd_all_up is None:
            missing_fields.append("v_apd_all_up")
        if v_apd_all_down is None:
            missing_fields.append("v_apd_all_down")
        if std_n_photons_per_shot is None:
            missing_fields.append("std_n_photons_per_shot")

        if len(missing_fields) == 0:
            # All calibration values provided directly
            return float(n_photons_per_shot), float(v_apd_all_up), float(v_apd_all_down), float(std_n_photons_per_shot)

        if amp_imaging is None or t_img_pulse is None:
            raise ValueError(
                "Missing calibration fields require amp_imaging and t_img_pulse for integrator_calibration fallback."
            )

        (n_cal, v_up_cal, v_down_cal, std_up_cal, std_down_cal) = integrator_calibration(
            amp_imaging=float(amp_imaging),
            t_imaging=float(t_img_pulse),
        )

        # Keep historical behavior for calibration-derived photon counts.
        n_cal = float(n_cal) * float(photon_count_scale)
        std_cal = 0.5 * (float(std_up_cal) + float(std_down_cal)) * float(photon_count_scale)

        used_n_photons = n_cal if n_photons_per_shot is None else n_photons_per_shot
        used_v_apd_all_up = v_up_cal if v_apd_all_up is None else v_apd_all_up
        used_v_apd_all_down = v_down_cal if v_apd_all_down is None else v_apd_all_down
        used_std_n_photons_per_shot = std_cal if std_n_photons_per_shot is None else std_n_photons_per_shot

        if n_photons_per_shot is None:
            n_photons_per_shot = n_cal
        if v_apd_all_up is None:
            v_apd_all_up = v_up_cal
        if v_apd_all_down is None:
            v_apd_all_down = v_down_cal
        if std_n_photons_per_shot is None:
            std_n_photons_per_shot = std_cal

        print(
            "\nFeedback: using integrator_calibration:\n"
            f"(amp_imaging={float(amp_imaging)}, t_img_pulse={float(t_img_pulse)} s) "
            f"for missing fields: {', '.join(missing_fields)}\n"
            f"  n_photons_per_shot = {used_n_photons}\n"
            f"  v_apd_all_up = {used_v_apd_all_up}\n"
            f"  v_apd_all_down = {used_v_apd_all_down}\n"
            f"  std_n_photons_per_shot = {used_std_n_photons_per_shot}\n"
        )

        return float(n_photons_per_shot), float(v_apd_all_up), float(v_apd_all_down), float(std_n_photons_per_shot)

    def _resolve_lightshift_calibration(
        self,
        amp_imaging,
        frequency_z_lightshift,
    ):
        if frequency_z_lightshift is not None:
            return float(frequency_z_lightshift)

        if amp_imaging is None:
            raise ValueError(
                "Missing frequency_z_lightshift requires amp_imaging for imaging_lightshift fallback."
            )

        frequency_z_lightshift = imaging_lightshift(float(amp_imaging))

        print(
            "\nFeedback: using imaging_lightshift calibration:\n"
            f"(amp_imaging={float(amp_imaging)}) for missing field: frequency_z_lightshift\n"
            f"  frequency_z_lightshift = {frequency_z_lightshift}"
        )

        return float(frequency_z_lightshift)

    def _resolve_apd_affine_map_settings(
        self,
        feedback_apd_map_enabled,
        feedback_apd_map_a,
        feedback_apd_map_b,
        feedback_apd_map_verbose,
    ):
        map_enabled = (
            getattr(self.p, "feedback_apd_map_enabled", False)
            if feedback_apd_map_enabled is None
            else feedback_apd_map_enabled
        )
        map_a = (
            getattr(self.p, "feedback_apd_map_a", 1.0)
            if feedback_apd_map_a is None
            else feedback_apd_map_a
        )
        map_b = (
            getattr(self.p, "feedback_apd_map_b", 0.0)
            if feedback_apd_map_b is None
            else feedback_apd_map_b
        )
        map_verbose = (
            getattr(self.p, "feedback_apd_map_verbose", True)
            if feedback_apd_map_verbose is None
            else feedback_apd_map_verbose
        )

        map_enabled = bool(map_enabled)
        map_a = float(map_a)
        map_b = float(map_b)
        map_verbose = bool(map_verbose)

        if not np.isfinite(map_a) or not np.isfinite(map_b):
            raise ValueError("feedback_apd_map_a and feedback_apd_map_b must be finite.")
        if map_enabled and abs(map_a) < 1.0e-12:
            raise ValueError("feedback_apd_map_a must be nonzero when feedback_apd_map_enabled is True.")

        return map_enabled, map_a, map_b, map_verbose

    def _apply_apd_affine_map_to_calibration(
        self,
        v_apd_all_up,
        v_apd_all_down,
        feedback_apd_map_a,
        feedback_apd_map_b,
        feedback_apd_map_verbose,
    ):
        v_up = float(v_apd_all_up)
        v_down = float(v_apd_all_down)

        if not np.isfinite(v_up) or not np.isfinite(v_down):
            raise ValueError("APD calibration values must be finite.")

        v_range = v_up - v_down
        if abs(v_range) < 1.0e-15:
            raise ValueError("APD calibration range is zero; cannot apply affine APD map.")

        a_coef = float(feedback_apd_map_a)
        b_coef = float(feedback_apd_map_b)

        v_down_mapped = v_down + v_range * (a_coef - b_coef - 1.0) / (2.0 * a_coef)
        v_up_mapped = v_down + v_range * (a_coef + 1.0 - b_coef) / (2.0 * a_coef)

        if bool(feedback_apd_map_verbose):
            print(
                "\nFeedback: applying APD affine mapping:\n"
                f"  y = {a_coef:.6g} * x + {b_coef:.6g}\n"
                f"  v_apd_all_up/down: ({v_up:.9g}, {v_down:.9g}) -> ({v_up_mapped:.9g}, {v_down_mapped:.9g})\n"
                "  note: this matches the linear (unclipped) affine map."
            )

        return float(v_up_mapped), float(v_down_mapped)

    @portable(flags={"fast-math"})
    def sincos_lut_interp(self, x):
        inv_two_pi = self.inv_two_pi
        two_pi = self.two_pi
        turns = int(x * inv_two_pi)
        x -= two_pi * turns
        if x < 0.0:
            x += two_pi

        y = x * self.lut_scale
        i0 = int(y)
        frac = y - i0

        lut_mask = self.lut_mask
        i1 = (i0 + 1) & lut_mask
        ic0 = (i0 + self.lut_quarter) & lut_mask
        ic1 = (i1 + self.lut_quarter) & lut_mask

        sin_lut = self.sin_lut
        s0 = sin_lut[i0]
        s1 = sin_lut[i1]
        c0 = sin_lut[ic0]
        c1 = sin_lut[ic1]

        sin_val = s0 + frac * (s1 - s0)
        cos_val = c0 + frac * (c1 - c0)
        return sin_val, cos_val

    @portable(flags={"fast-math"})
    def sin_lut_interp(self, x):
        (s, _) = self.sincos_lut_interp(x)
        return s

    @portable(flags={"fast-math"})
    def cos_lut_interp(self, x):
        (_, c) = self.sincos_lut_interp(x)
        return c

    @portable(flags={"fast-math"})
    def powi(self, base, exp):
        result = 1.0
        b = base
        e = exp
        while e > 0:
            if (e & 1) != 0:
                result *= b
            b *= b
            e = e // 2
        return result

    def _ensure_repeat_axis0(self, arr, name):
        x = np.asarray(arr)
        if x.ndim == 1:
            return x.reshape(1, -1)
        if x.ndim == 2:
            return x
        raise ValueError(f"{name} must be 1D or 2D with repeats on axis 0, got shape {x.shape}.")

    def rotation_axis_rotating_frame(
        self,
        omega_0,
        omega,
        t,
        phase_zero_time=None,
        Omega=None,
    ):
        """
        Return the unit rotation axis in the frame rotating at omega_0.

        Parameters
        ----------
        omega_0 : float
            Atom transition frequency (rad/s).
        omega : float
            Drive frequency (rad/s).
        t : float
            Evaluation time (s).
        phase_zero_time : float or None
            Time where the drive phase is defined to be zero. If None,
            it defaults to t, so the returned axis uses phase=0 at time t.
        Omega : float or None
            Rabi rate (rad/s). If None, uses self.Omega.

        Returns
        -------
        np.ndarray
            Unit axis [ux, uy, uz] as float64.
        """
        if phase_zero_time is None:
            phase_zero_time = t
        if Omega is None:
            Omega = self.Omega

        delta_omega = float(omega) - float(omega_0)
        phase = delta_omega * (float(t) - float(phase_zero_time))

        Omega = float(Omega)
        norm_H = np.sqrt(Omega * Omega + delta_omega * delta_omega)
        if norm_H <= 0.0:
            return np.array([0.0, 0.0, 0.0], dtype=np.float64)

        inv_norm_H = 1.0 / norm_H
        ux = (Omega * inv_norm_H) * np.cos(phase)
        uy = (Omega * inv_norm_H) * np.sin(phase)
        uz = delta_omega * inv_norm_H
        return np.array([ux, uy, uz], dtype=np.float64)

def _as_repeat_axis0(arr, name):
    x = np.asarray(arr)
    if x.ndim == 1:
        return x.reshape(1, -1)
    if x.ndim == 2:
        return x
    raise ValueError(f"{name} must be 1D or 2D with repeats on axis 0, got shape {x.shape}.")


def _resolve_override_rr(arr, name, n_repeat, n_step):
    if arr is None:
        return None

    x = np.asarray(arr)
    if x.ndim == 1:
        if x.shape[0] != n_step:
            raise ValueError(f"{name} override length must match len(pulse_times)={n_step}, got {x.shape[0]}.")
        return np.tile(x.reshape(1, -1), (n_repeat, 1))

    if x.ndim == 2:
        if x.shape != (n_repeat, n_step):
            raise ValueError(
                f"{name} override must have shape ({n_repeat}, {n_step}), got {x.shape}."
            )
        return x

    raise ValueError(f"{name} override must be 1D or 2D, got shape {x.shape}.")


def _all_rows_equal(arr):
    if arr.shape[0] <= 1:
        return True
    return bool(np.allclose(arr, arr[0:1, :]))


def _require_atomdata_attr(obj, name, path_hint):
    if not hasattr(obj, name):
        raise ValueError(f"Missing {path_hint}.{name} required for replay.")
    return getattr(obj, name)


def _feedback_kwargs_from_atomdata(ad):
    p = getattr(ad, "p", None)
    if p is None:
        return {}

    return {
        "t_raman_pulse": getattr(p, "t_raman_pulse", getattr(p, "dt_eff", None)),
        "t_raman_pulse_ideal": getattr(p, "t_raman_pulse_ideal", getattr(p, "dt_ideal", None)),
        "dt_eff": getattr(p, "dt_eff", None),
        "dt_ideal": getattr(p, "dt_ideal", None),
        "t_img_pulse": getattr(p, "t_img_pulse", None),
        "amp_imaging": getattr(p, "amp_imaging", None),
        "t_raman_pi_pulse": getattr(p, "t_raman_pi_pulse", None),
        "frequency_resonance": getattr(p, "frequency_raman_transition", None),
        "frequency_z_lightshift": getattr(p, "frequency_lightshift", None),
        "v_apd_all_up": getattr(p, "v_apd_all_up", None),
        "v_apd_all_down": getattr(p, "v_apd_all_down", None),
        "n_photons_per_shot": getattr(p, "n_photons_per_shot", getattr(p, "N_photons_per_shot", None)),
        "std_n_photons_per_shot": getattr(p, "std_n_photons_per_shot", None),
        "photon_count_scale": getattr(p, "feedback_photon_count_scale", 1.0),
        "feedback_measurement_midpoint_fraction": getattr(p, "feedback_measurement_midpoint_fraction", None),
        "feedback_measurement_midpoint_remap_enabled": getattr(p, "feedback_measurement_midpoint_remap_enabled", None),
        "feedback_grid_size": int(getattr(p, "feedback_grid_size", 21)),
        "fractional_grid_center_offset": float(getattr(p, "feedback_fractional_grid_center_offset", 2.0)),
        "fractional_initial_offset": getattr(p, "feedback_fractional_initial_offset", -5.0),
        "guess_span_Omega": float(getattr(p, "feedback_guess_span_Omega", 5.0)),
        "feedback_apd_map_enabled": getattr(p, "feedback_apd_map_enabled", None),
        "feedback_apd_map_a": getattr(p, "feedback_apd_map_a", None),
        "feedback_apd_map_b": getattr(p, "feedback_apd_map_b", None),
        "feedback_apd_map_verbose": getattr(p, "feedback_apd_map_verbose", None),
    }