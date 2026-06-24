from artiq.experiment import kernel, portable, TInt64, TTuple, TArray, TFloat
import numpy as np
from numpy import int64
from kexp.calibrations.imaging import integrator_calibration, imaging_lightshift
from kexp.util.artiq.async_print import aprint

dv = -1.

class _FeedbackParamStore:
    """Attribute bag used when Feedback is instantiated outside Base."""


class Feedback:
    kernel_invariants = {
        "m",
        "dt_eff",
        "dt_ideal",
        "dt_z",
        "N_photons_per_shot",
        "std_n_photons_per_shot",
        "v_apd_all_up",
        "v_apd_all_down",
        "v_range",
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

    def __init__(self, lut_size=4096, expt_params=None):
        if expt_params == None:
            from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams
            if not hasattr(self, "p"):
                self.p = ExptParams()
        else:
            self.p = expt_params

        self._preallocate_arrays()
        self._initialize_trig_lut(lut_size=lut_size)
        self._initialize_timing()
        self._initialize_lightshift()
        self._initialize_frequency_grid()
        self._initialize_measurement_calibrations()
        self._initialize_posterior_state()
        
        self._print_estimated_time = True

        self._remesh_counter = 0

    def omega_to_detuning(self, omega_raman):
        '''Returns the detuning in units of Omega, given the Raman drive frequency in rad/s.'''
        return (omega_raman - 2.0 * np.pi * self.p.frequency_raman_transition)/self.Omega

    def _preallocate_arrays(self):
        self.omega_guess_list = np.zeros(self.p.feedback_grid_size, dtype=np.float64)
        self.omega_sq_list = np.zeros(self.p.feedback_grid_size, dtype=np.float64)
        self.p.omega_guess_list = np.zeros(self.p.feedback_grid_size, dtype=np.float64)
        self.omega_original_min = 0.0
        self.omega_original_max = 0.0

    @portable(flags={"fast-math"})
    def convert_measurement(self, v_apd):
        return round(self.N_photons_per_shot * (v_apd - self.v_apd_all_down) / self.v_range)

    @portable(flags={"fast-math"})
    def expected_photon_fraction(self, hz):
        p1 = 0.5 * (1.0 + hz)
        
        if self.feedback_measurement_midpoint_remap_enabled:
            midpoint = self.feedback_measurement_midpoint_fraction
            p1 += + (midpoint - 0.5) * (1.0 - hz * hz)

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
            # npq = n_photons * p1 * q + sigma_sq
            npq = sigma_sq
            num = k - n_photons * p1
            if include_photon_noise:
                f = sigma / np.sqrt(npq) * np.exp(-num * num / (2.0 * npq))
            else:
                p1_pow = self.powi(p1, k_int)
                q_pow = self.powi(q, nk_int)
                f = p1_pow * q_pow
            pj = P0[j] * f            

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
            return self.omega_raman, self.omega_raman, self.Omega

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

        # Find the frequency at maximum posterior probability
        max_idx = 0
        max_prob = P0[0]
        i = 1
        while i < len(P0):
            if P0[i] > max_prob:
                max_prob = P0[i]
                max_idx = i
            i += 1
        omega_max = omega_guess_list[max_idx]

        # If distribution is nearly flat (max prob close to uniform), use mean instead of max
        uniform_prob = 1.0 / m
        if max_prob < 1.5 * uniform_prob:
            omega_raman_out = mn  # Distribution is flat, use mean
        else:
            omega_raman_out = omega_max  # Distribution has a peak, use max

        # Store the max frequency for diagnostics
        self.omega_max = omega_max

        # Store true posterior std before it may be overridden below
        self._posterior_std = std

        if not update_raman_frequency:
            omega_raman_out = self.omega_raman
        if not update_rabi_frequency:
            std = self.Omega

        return omega_raman_out, mn, std
    
    @portable(flags={"fast-math"})
    def compute_t_between_pulses_mu(
        self,
        t_calculation_slack_compensation_mu,
        t_raman_pulse,
        t_img_pulse,
        t_raman_pretrigger = 650,
        t_fifo_mu = int64(1000)
    ) -> TInt64:
        T_MIN_FIFO_MU = t_fifo_mu
        t_raman_pulse_mu = np.int64(t_raman_pulse * 1.0e9)
        t_img_pulse_mu = np.int64(t_img_pulse * 1.0e9)
        return (
            t_calculation_slack_compensation_mu
            + t_raman_pretrigger
            + t_raman_pulse_mu
            + t_img_pulse_mu
            + T_MIN_FIFO_MU
        ) & ~7

    @kernel
    def initialize_feedback(self):
        """Warm up posterior runtime once, then reset state/P0 arrays."""

        self.omega_raman = self.reset_initial_omega_from_params()

        self.p.t_between_pulses_mu = self.compute_t_between_pulses_mu(
            t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
            t_raman_pulse=self.p.t_raman_pulse,
            t_img_pulse=self.p.t_img_pulse,
            t_raman_pretrigger=self.p.t_raman_set_pretrigger_mu,
            t_fifo_mu=self.p.t_fifo_mu
        )

        n_test = int(round(self.N_photons_per_shot * self.expected_photon_fraction(0.0)))

        self.core.wait_until_mu(self.core.get_rtio_counter_mu())
        self.generate_posterior(n_test, 1.0e-6)
        self.core.break_realtime()

        t0 = self.core.get_rtio_counter_mu()
        self.core.wait_until_mu(t0)
        self.generate_posterior(n_test, 1.0e-6)
        self.t_posterior_mu = abs(t0 - self.core.get_rtio_counter_mu())
        self.core.break_realtime()
        
        if self._print_estimated_time:
            aprint('calculation esimated slack consumption:', self.t_posterior_mu)
            self._print_estimated_time = False
        
        # Reset the adaptive span to its original value each shot
        self.feedback_remesh_span_Omega = self.p.feedback_guess_span_Omega
        self.reset_feedback_state()

        self._initialize_frequency_grid()
        self.p.omega_guess_list = self.omega_guess_list
        # aprint((self.omega_guess_list/self.two_pi - self.p.frequency_raman_transition)/(self.Omega/(2*np.pi)))

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

    def _initialize_timing(self):
        self.p.feedback_grid_size = int(self.p.feedback_grid_size)
        self.m = self.p.feedback_grid_size
        self.Omega = np.pi / self.p.t_raman_pi_pulse
        self.dt_eff = float(self.p.t_raman_pulse)
        self.dt_ideal = float(self.p.t_raman_pulse_ideal)
        self.dt_z = float(self.p.t_img_pulse)
        # Remesh state (mutable per-shot; not kernel_invariants so they can be scanned)

    def _initialize_lightshift(self):
        self.p.frequency_lightshift = self._resolve_lightshift_calibration(self.p.amp_imaging, self.p.frequency_lightshift)
        self.frequency_z_lightshift = self.p.frequency_lightshift
        self.omega_z_lightshift = 2.0 * np.pi * self.frequency_z_lightshift
        self.p.back_action_coherence = float(self.p.back_action_coherence)
        self.back_action_coherence = self.p.back_action_coherence

    @portable(flags={"fast-math"})
    def _initialize_frequency_grid(self):
        """Kernel-safe loop-based grid initialisation (no numpy allocation)."""
        omega_resonance = self.two_pi * self.p.frequency_raman_transition
        self.p.feedback_fractional_initial_offset = self.p.feedback_fractional_initial_offset
        n_grid_offset = round(self.p.feedback_fractional_initial_offset)
        span = self.p.feedback_guess_span_Omega
        m = self.m
        Omega = self.Omega

        # Build grid: omega[i] = omega_res + Omega*(offset - span*linspace(-1,1,m)[i])
        # linspace(-1,1,m)[i] = -1 + i * 2/(m-1)
        scale = 2.0 / (m - 1)
        best_idx = 0
        best_dist = 1.0e12
        i = 0
        while i < m:
            t = -1.0 + i * scale
            omega = omega_resonance + Omega * (n_grid_offset - span * t)
            self.omega_guess_list[i] = omega
            dist = omega - omega_resonance
            if dist < 0.0:
                dist = -dist
            if dist < best_dist:
                best_dist = dist
                best_idx = i
            i += 1

        # Shift so the nearest grid point lands exactly on resonance
        omega_shift = omega_resonance - self.omega_guess_list[best_idx]
        i = 0
        while i < m:
            omega = self.omega_guess_list[i] + omega_shift
            self.omega_guess_list[i] = omega
            self.omega_sq_list[i] = omega * omega
            i += 1

        self.p.omega_guess_list = self.omega_guess_list
        self.p.feedback_resonance_grid_index = best_idx
        self.omega_raman = self.reset_initial_omega_from_params()

        self.feedback_remesh_threshold_omega = self.p.feedback_remesh_threshold_Omega * self.Omega
        self.feedback_remesh_span_Omega = float(self.p.feedback_guess_span_Omega)

        # Record the original grid bounds for remesh clamping
        omega_lo = self.omega_guess_list[0]
        omega_hi = self.omega_guess_list[m - 1]
        if omega_lo < omega_hi:
            self.omega_original_min = omega_lo
            self.omega_original_max = omega_hi
        else:
            self.omega_original_min = omega_hi
            self.omega_original_max = omega_lo

    @portable(flags={"fast-math"})
    def remesh_to_centered(self, omega_center, span_Omega, interpolate_posterior=1):
        """Re-grid in-place centred on omega_center with half-width span_Omega*Omega.

        Grid order (ascending/descending) is inherited from the existing grid.
        P0 is linearly interpolated (interpolate_posterior=1) or reset to
        uniform 1/m (=0).  Bloch state transferred by nearest-neighbour copy.
        No dynamic allocation; compatible with @portable fast-math."""
        interpolate_bool = bool(interpolate_posterior)
        m = self.m
        Omega = self.Omega

        if span_Omega < 0.0:
            span_Omega = -span_Omega

        # Capture old grid geometry before any writes
        old_start    = self.omega_guess_list[0]
        old_step     = self.omega_guess_list[1] - old_start if m > 1 else 1.0
        inv_old_step = 1.0 / old_step

        # New grid: same sign (order) as old grid, recentred with new span
        if old_step < 0.0:
            step_new = -(2.0 * span_Omega * Omega) / (m - 1)
        else:
            step_new = (2.0 * span_Omega * Omega) / (m - 1)

        # Clamp omega_center so the new grid stays within the original grid bounds
        half_width = step_new * (m - 1) * 0.5
        if half_width < 0.0:
            half_width = -half_width
        clamp_lo = self.omega_original_min + half_width
        clamp_hi = self.omega_original_max - half_width
        if clamp_lo > clamp_hi:
            # New grid is wider than the original (shouldn't happen in normal use);
            # fall back to centering on the original grid midpoint
            omega_center = (self.omega_original_min + self.omega_original_max) * 0.5
        elif omega_center < clamp_lo:
            omega_center = clamp_lo
        elif omega_center > clamp_hi:
            omega_center = clamp_hi

        new_start = omega_center - step_new * (m - 1) * 0.5

        # Precompute incremental fractional-index walk (avoids per-iter multiply)
        frac_0 = (new_start - old_start) * inv_old_step
        dfrac  = step_new * inv_old_step

        # ── Pass 1: interpolate P0 onto new grid; store in omega_sq_list scratch ──
        if interpolate_posterior:
            total = 0.0
            i     = 0
            frac  = frac_0
            while i < m:
                lo = int(frac)
                if lo < 0:
                    p = self.P0[0]
                elif lo >= m - 1:
                    p = self.P0[m - 1]
                else:
                    p = self.P0[lo] + (frac - lo) * (self.P0[lo + 1] - self.P0[lo])
                if p < 0.0:
                    p = 0.0
                self.omega_sq_list[i] = p
                total += p
                frac  += dfrac
                i     += 1
            inv_total = 1.0 / total if total > 0.0 else float(m)
        else:
            inv_total = 1.0 / m

        # ── Pass 2: write new omega grid, normalised P0, nearest-neighbour Bloch ──
        i     = 0
        frac  = frac_0
        omega = new_start
        while i < m:
            lo         = int(frac)
            lo_nearest = lo + 1 if frac - lo >= 0.5 else lo
            if lo_nearest < 0:
                lo_nearest = 0
            elif lo_nearest >= m:
                lo_nearest = m - 1
            p_new = self.omega_sq_list[i] * inv_total if interpolate_bool else inv_total
            self.omega_guess_list[i] = omega
            self.omega_sq_list[i]    = omega * omega
            self.P0[i]               = p_new
            self.state_x[i]          = self.state_x[lo_nearest]
            self.state_y[i]          = self.state_y[lo_nearest]
            self.state_z[i]          = self.state_z[lo_nearest]
            frac  += dfrac
            omega += step_new
            i     += 1
        self.P0_total = 1.0

    @portable(flags={"fast-math"})
    def maybe_remesh(self, posterior_std, omega_center):
        """Halve the grid span and re-centre on omega_center if posterior_std is below
        feedback_remesh_threshold_omega.  No-op when threshold is 0 (disabled).

        Args:
            posterior_std: the posterior standard deviation (rad/s); remesh fires if
                          posterior_std < feedback_remesh_threshold_omega.
            omega_center: the frequency to center the new grid on. If None, uses self.omega_raman.
        """
            
        if self.feedback_remesh_threshold_omega > 0.0:
            if posterior_std < (self.feedback_remesh_threshold_omega):
                self._remesh_counter += 1
            elif posterior_std > self.p.remesh_reset_counter_threshold_fraction * self.feedback_remesh_threshold_omega:
                self._remesh_counter = 0

            if self._remesh_counter > (self.p.remesh_after_n_good_shots-1):
                # aprint(posterior_std/self.Omega)
                self.feedback_remesh_threshold_omega *= self.p.remesh_threshold_scale_factor
                self.feedback_remesh_span_Omega = self.feedback_remesh_span_Omega * self.p.remesh_scale_factor
                interpolate_posterior = self.p.remesh_interpolate_posterior
                self.remesh_to_centered(omega_center, self.feedback_remesh_span_Omega, interpolate_posterior)
                self._remesh_counter = 0

    def _initialize_measurement_calibrations(self):
        (
            n_photons_per_shot,
            v_apd_all_up,
            v_apd_all_down,
            std_n_photons_per_shot,
        ) = self._resolve_measurement_calibration(
            amp_imaging=self.p.amp_imaging,
            t_img_pulse=self.p.t_img_pulse,
            n_photons_per_shot=self.p.n_photons_per_shot,
            std_n_photons_per_shot=self.p.std_n_photons_per_shot,
            v_apd_all_up=self.p.v_apd_all_up,
            v_apd_all_down=self.p.v_apd_all_down,
            photon_count_scale=getattr(self.p, "feedback_photon_count_scale", 1.0),
        )

        map_enabled, map_a, map_b, map_verbose = self._resolve_apd_affine_map_settings(
            feedback_apd_map_enabled=self.p.feedback_apd_map_enabled,
            feedback_apd_map_a=self.p.feedback_apd_map_a,
            feedback_apd_map_b=self.p.feedback_apd_map_b,
            feedback_apd_map_verbose=self.p.feedback_apd_map_verbose,
        )
        midpoint_remap_enabled = self._resolve_measurement_midpoint_remap_enabled(
            feedback_measurement_midpoint_remap_enabled=self.p.feedback_measurement_midpoint_remap_enabled,
        )
        midpoint_fraction = self._resolve_measurement_midpoint_fraction(
            feedback_measurement_midpoint_fraction=self.p.feedback_measurement_midpoint_fraction,
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

    def _resolve_measurement_midpoint_remap_enabled(self, feedback_measurement_midpoint_remap_enabled):
        return bool(feedback_measurement_midpoint_remap_enabled)

    def _resolve_measurement_midpoint_fraction(self, feedback_measurement_midpoint_fraction):
        midpoint_fraction = float(feedback_measurement_midpoint_fraction)
        if not np.isfinite(midpoint_fraction):
            raise ValueError("feedback_measurement_midpoint_fraction must be finite.")
        if midpoint_fraction < 0.0 or midpoint_fraction > 1.0:
            raise ValueError("feedback_measurement_midpoint_fraction must be between 0 and 1 inclusive.")
        return midpoint_fraction

    def _initialize_posterior_state(self):
        self.P0 = np.ones(self.m, dtype=np.float64)
        self.P0 = self.P0 / np.sum(self.P0)
        self.P0_total = 1.0

        self.state_x = np.zeros(self.m, dtype=np.float64)
        self.state_y = np.zeros(self.m, dtype=np.float64)
        self.state_z = np.ones(self.m, dtype=np.float64)
        self.t_posterior_mu = np.int64(0)
        self._posterior_std = 0.0  # side-channel: true posterior std before conditional override
        self.omega_max = 0.0  # frequency at maximum posterior probability

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
        self, feedback_apd_map_enabled, feedback_apd_map_a, feedback_apd_map_b, feedback_apd_map_verbose
    ):
        map_enabled = bool(feedback_apd_map_enabled)
        map_a = float(feedback_apd_map_a)
        map_b = float(feedback_apd_map_b)
        map_verbose = bool(feedback_apd_map_verbose)

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
        i0 = int(y) & self.lut_mask
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
        "t_raman_pulse": p.t_raman_pulse,
        "t_raman_pulse_ideal": p.t_raman_pulse_ideal,
        "t_img_pulse": p.t_img_pulse,
        "amp_imaging": p.amp_imaging,
        "t_raman_pi_pulse": p.t_raman_pi_pulse,
        "frequency_resonance": p.frequency_raman_transition,
        "frequency_z_lightshift": p.frequency_lightshift,
        "v_apd_all_up": p.v_apd_all_up,
        "v_apd_all_down": p.v_apd_all_down,
        "n_photons_per_shot": p.n_photons_per_shot,
        "std_n_photons_per_shot": p.std_n_photons_per_shot,
        "photon_count_scale": getattr(p, "feedback_photon_count_scale", 1.0),
        "feedback_measurement_midpoint_fraction": p.feedback_measurement_midpoint_fraction,
        "feedback_measurement_midpoint_remap_enabled": p.feedback_measurement_midpoint_remap_enabled,
        "feedback_grid_size": int(p.feedback_grid_size),
        "fractional_grid_center_offset": float(p.feedback_fractional_grid_center_offset) if hasattr(p, "feedback_fractional_grid_center_offset") else None,
        "fractional_initial_offset": p.feedback_fractional_initial_offset,
        "guess_span_Omega": float(p.feedback_guess_span_Omega),
        "feedback_apd_map_enabled": p.feedback_apd_map_enabled,
        "feedback_apd_map_a": p.feedback_apd_map_a,
        "feedback_apd_map_b": p.feedback_apd_map_b,
        "feedback_apd_map_verbose": p.feedback_apd_map_verbose,
    }