from artiq.experiment import kernel, portable, rpc, TInt32, TInt64, TArray, TFloat
import numpy as np
from numpy import int64
from kexp.util.artiq.async_print import aprint

#: State-dependent read: the kernel adds d = READ_TWIST_SIGN * p.read_twist_per_sz * hz to its
#: z-rotation angle alpha_z (hz: the hypothesis' z after the pulse, at the read), the same sense as
#: the light-shift term. If mr0 finds hz = -s_z, or dphi in the opposite sense, flip this ONE
#: constant (every copy of the kernel reads it through Feedback).
READ_TWIST_SIGN = 1.0

#: Points within this fraction of the posterior maximum tie (p.feedback_map_tie_mean). Not exact
#: equality: mirror-image hypotheses came out 3e-14 apart on 2026-10-08, and picked by rounding.
MAP_TIE_REL_TOL = 1.e-9


class Feedback:
    kernel_invariants = {
        "m",
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
        "back_action_coherence",
        "read_twist", "read_twist_on",
        "read_coherence_slope", "read_coherence_slope_on",
        "read_alpha_lightshift", "read_alpha_lightshift_on",
        "map_tie_mean", "map_tie_floor",
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

        self._flat_prob_counter = 0

        # posterior collapses reset to uniform in generate_posterior; never reset, so a nonzero
        # value at the end of a run means updates were discarded
        self._degenerate_posterior_counter = 0

    def omega_to_detuning(self, omega_raman):
        '''Returns the detuning in units of Omega, given the Raman drive frequency in rad/s.'''
        return (omega_raman - 2.0 * np.pi * self.p.frequency_raman_transition)/self.Omega

    def _preallocate_arrays(self):
        self.p.feedback_grid_size = int(self.p.feedback_grid_size)
        self.omega_guess_list = np.zeros(self.p.feedback_grid_size, dtype=np.float64)
        self.omega_sq_list = np.zeros(self.p.feedback_grid_size, dtype=np.float64)
        self.p.omega_guess_list = np.zeros(self.p.feedback_grid_size, dtype=np.float64)
        self.omega_original_min = 0.0
        self.omega_original_max = 0.0
        self.state_x_scratch = np.zeros(self.p.feedback_grid_size, dtype=np.float64)
        self.state_y_scratch = np.zeros(self.p.feedback_grid_size, dtype=np.float64)
        self.state_z_scratch = np.zeros(self.p.feedback_grid_size, dtype=np.float64)
        self.max_idx = 0

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

        # the pulse being processed: randomized pulse-time lists set these per pulse
        dt_eff = self.t_raman_pulse_current
        dt_ideal = self.t_raman_pulse_ideal_current
        dt_z = self.p.t_img_pulse

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
        if self.read_alpha_lightshift_on:
            # the read's constant z angle set on its own (theta11: 1.432 rad); off: w_ls t_img
            alpha_z_lightshift = self.read_alpha_lightshift
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

            # State-dependent read (READ_TWIST_SIGN above): a twist d = read_twist * hz on the z
            # rotation (second order, not renormalised) and the coherence c0 + slope * hz, clipped.
            if self.read_twist_on:
                d_twist = self.read_twist * hz
                cos_d = 1.0 - d_twist * d_twist * 0.5
                nx_twisted = cos_d * nx + d_twist * ny
                ny = -d_twist * nx + cos_d * ny
                nx = nx_twisted
            coherence = self.back_action_coherence
            if self.read_coherence_slope_on:
                coherence = coherence + self.read_coherence_slope * hz
                if coherence < 0.0:
                    coherence = 0.0
                elif coherence > 1.0:
                    coherence = 1.0

            state_x[j] = nx * coherence
            state_y[j] = ny * coherence
            state_z[j] = hz

            p1 = self.expected_photon_fraction(hz)
            q = 1.0 - p1
            # Fixed sigma, INTENTIONALLY: the binomial term n_photons*p1*q is left out so the posterior
            # tolerates unmodelled excess noise. Do not restore it without re-deriving the calibration.
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
            # Every grid point underflowed to zero: reset to uniform, or every later update this shot
            # stays zero and the feedback freezes. This update is lost; the counter records it.
            uniform = 1.0 / m
            i = 0
            while i < len(P0):
                P0[i] = uniform
                i += 1
            self.P0_total = 1.0
            self._degenerate_posterior_counter += 1
            return self.omega_raman, self.omega_raman, self.Omega

        mn = mn / P0_total
        moment_2 = moment_2 / P0_total

        i = 0
        while i < len(P0):
            P0[i] = P0[i] / P0_total
            i += 1
        
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
        omega_max = self.map_frequency(max_idx, max_prob)
        self.max_idx = max_idx

        # If distribution is nearly flat (max prob close to uniform), use mean instead of max
        uniform_prob = 1.0 / m
        if max_prob < 1.15 * uniform_prob:
            omega_raman_out = mn  # Distribution is flat, use mean
            self._flat_prob_counter += 1
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
    def map_frequency(self, max_idx, max_prob):
        """The frequency of the posterior maximum P0[max_idx] = max_prob. With
        p.feedback_map_tie_mean, tied points (kept above map_tie_floor x max_prob) give
        the mean of their frequencies, so a tie is not settled by grid order, and the
        drive may land between grid points. Off (run files without the key): the first
        maximum, as those runs drove. max_idx stays the first maximum either way: it
        indexes a hypothesis' stored Bloch vector."""
        omega_guess_list = self.omega_guess_list
        if not self.map_tie_mean:
            return omega_guess_list[max_idx]
        P0 = self.P0
        floor = self.map_tie_floor * max_prob
        total = 0.0
        n_tied = 0
        i = 0
        while i < len(P0):
            if P0[i] >= floor:
                total += omega_guess_list[i]
                n_tied += 1
            i += 1
        return total / n_tied

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
        self._flat_prob_counter = 0
        # aprint((self.omega_guess_list/self.two_pi - self.p.frequency_raman_transition)/(self.Omega/(2*np.pi)))

    @portable(flags={"fast-math"})
    def reset_feedback_state(self):
        i = 0
        while i < self.m:
            self.state_x[i] = 0.0
            self.state_y[i] = 0.0
            self.state_z[i] = self.initial_sz
            self.P0[i] = 1.0 / self.m
            i += 1
        self.P0_total = 1.0

    @portable(flags={"fast-math"})
    def reset_initial_omega_from_params(self):
        """Refresh initial control omega from current (possibly scanned) params."""
        # initial drive - resonance in Omega: the base parameter itself in
        # convention 1, derived from it in convention 2 ('hypothesis grid' below)
        offset_Omega = self.p.feedback_fractional_initial_offset
        if self.grid_convention >= 2:
            offset_Omega = self.p.feedback_initial_offset_Omega
        self.omega_raman = (
            2.0 * np.pi * self.p.frequency_raman_transition
            + self.Omega * offset_Omega
        )
        return self.omega_raman

    def _initialize_timing(self):
        self.m = self.p.feedback_grid_size
        self.Omega = np.pi / self.p.t_raman_pi_pulse
        # 1: grid centred on the exact initial offset. 0 (and files without the key): on
        # round(offset), as every run before 2026-09-27
        self.grid_center_exact = int(getattr(self.p, "feedback_grid_center_exact_offset", 0))
        # 1 or 2 ('hypothesis grid', module level); 1 when the params do not say. The kernel reads the
        # Omega-unit offset of either convention, so both names must exist.
        self.grid_convention = feedback_grid_convention(self.p)
        # 1: a tie for the posterior maximum gives the mean of the tied points (map_frequency).
        # 0 (and files without the key): the first maximum, as every run before 2026-10-30
        self.map_tie_mean = int(np.ravel(getattr(self.p, "feedback_map_tie_mean", 0))[0])
        self.map_tie_floor = 1.0 - MAP_TIE_REL_TOL
        if not hasattr(self.p, "feedback_initial_offset_Omega"):
            self.p.feedback_initial_offset_Omega = float(
                np.ravel(self.p.feedback_fractional_initial_offset)[0])
        if not hasattr(self.p, "feedback_grid_shift"):
            self.p.feedback_grid_shift = 0.0
        self.p.feedback_resonance_grid_index_frac = 0.0
        # +1 (all up). Replay only: older run files with feedback_initial_sz = -1 prepared all down with
        # a pre-shot pi pulse (removed from FeedbackExpt 2026-10-30).
        self.initial_sz = float(np.ravel(getattr(self.p, "feedback_initial_sz", 1.0))[0])
        # the pulse being processed; randomized pulse-time lists overwrite these per pulse
        self.t_raman_pulse_current = float(getattr(self.p, "t_raman_pulse", 0.0))
        self.t_raman_pulse_ideal_current = float(
            getattr(self.p, "t_raman_pulse_ideal", self.t_raman_pulse_current))

    def _initialize_lightshift(self):
        self.p.frequency_lightshift = float(self.p.frequency_lightshift)
        self.frequency_z_lightshift = self.p.frequency_lightshift
        self.omega_z_lightshift = 2.0 * np.pi * self.frequency_z_lightshift
        self.p.back_action_coherence = float(self.p.back_action_coherence)
        self.back_action_coherence = self.p.back_action_coherence
        # state-dependent read (READ_TWIST_SIGN above); 0 = off; absent in older runs
        self.p.read_twist_per_sz = float(getattr(self.p, "read_twist_per_sz", 0.0))
        self.p.back_action_coherence_slope = float(getattr(self.p, "back_action_coherence_slope", 0.0))
        self.read_twist = READ_TWIST_SIGN * self.p.read_twist_per_sz
        self.read_twist_on = self.read_twist != 0.0
        self.read_coherence_slope = self.p.back_action_coherence_slope
        self.read_coherence_slope_on = self.read_coherence_slope != 0.0
        # the read's constant z angle (rad); NaN / absent = omega_z_lightshift * t_img
        a_ls = float(getattr(self.p, "read_alpha_lightshift", float("nan")))
        self.p.read_alpha_lightshift = a_ls
        self.read_alpha_lightshift_on = bool(np.isfinite(a_ls))
        self.read_alpha_lightshift = a_ls if self.read_alpha_lightshift_on else 0.0
        self._check_read_model_hooks()

    #: Text every posterior method in use must contain to implement the read model.
    READ_MODEL_TOKENS = ("self.read_twist", "self.read_alpha_lightshift", "self.read_coherence_slope")

    def _check_read_model_hooks(self):
        """With the read model on, refuse a class whose posterior methods do not implement it (e.g. a
        session copy made before the read model), checked from each method's source text."""
        on = self.read_twist_on or self.read_coherence_slope_on or self.read_alpha_lightshift_on
        if not on:
            return
        import inspect
        for name in ("generate_posterior", "propagate_hypotheses"):
            fn = getattr(type(self), name, None)
            if fn is None:
                continue
            fn = getattr(fn, "__func__", fn)
            try:
                src = inspect.getsource(fn)
                where = inspect.getsourcefile(fn)
            except (OSError, TypeError) as exc:
                raise RuntimeError(
                    f"read model on, but the source of {type(self).__name__}.{name} cannot be read "
                    f"to check that it implements it ({exc})") from exc
            missing = [t for t in self.READ_MODEL_TOKENS if t not in src]
            if missing:
                raise RuntimeError(
                    f"read model on (read_twist_per_sz / read_alpha_lightshift / "
                    f"back_action_coherence_slope), but "
                    f"{type(self).__name__}.{name} in {where} does not implement it (no "
                    f"{', '.join(missing)}): an older or session copy of the posterior. It would "
                    f"run without the read model, silently. Use the repo's class, or port the "
                    f"read model into this copy.")

    @portable
    def re_initalize_spin_vector(self):
        xyproj = np.sqrt(self.state_x[self.max_idx]*self.state_x[self.max_idx] + self.state_y[self.max_idx]*self.state_y[self.max_idx])

        theta = np.arctan2(-self.state_x[self.max_idx], self.state_y[self.max_idx])
        phi = np.arctan2( xyproj, self.state_z[self.max_idx])

        # theta = np.pi + theta

        self.raman.set(relative_phase = theta)
        self.raman.pulse(phi*self.p.t_raman_pi_pulse/np.pi)





    @portable(flags={"fast-math"})
    def _initialize_frequency_grid(self):
        """Kernel-safe loop-based grid initialisation (no numpy allocation)."""
        omega_resonance = self.two_pi * self.p.frequency_raman_transition
        # Grid centre, in Omega from resonance. reset_initial_omega_from_params
        # starts the drive at the exact offset, so the grid is centred there too
        # (grid_center_exact = 1): any real offset works, and the snap below
        # moves the grid by at most half a step. grid_center_exact = 0 is the
        # old placement on round(offset) (half-to-even), kept only so runs taken
        # with it replay as they ran: for a fractional offset it left the grid
        # centre away from the initial drive (0.5 -> 0).
        # Convention 2 ('hypothesis grid', module level) always centres on the
        # exact (derived) offset, breaks an exact tie toward the grid centre so
        # resonance stays off the edge points, and then moves the whole grid by
        # p.feedback_grid_shift steps. feedback_hypothesis_grid is the host copy.
        convention = self.grid_convention
        if convention >= 2:
            grid_center = self.p.feedback_initial_offset_Omega
        else:
            grid_center = float(self.p.feedback_fractional_initial_offset)
            if self.grid_center_exact == 0:
                grid_center = float(round(self.p.feedback_fractional_initial_offset))
        span = self.p.feedback_guess_span_Omega
        m = self.m
        Omega = self.Omega

        # Build grid: omega[i] = omega_res + Omega*(center - span*linspace(-1,1,m)[i])
        # linspace(-1,1,m)[i] = -1 + i * 2/(m-1)
        scale = 2.0 / (m - 1)
        step = Omega * span * scale
        tie_tol = 1.0e-6 * step
        centre_idx = 0.5 * (m - 1)
        best_idx = 0
        best_dist = 1.0e12
        i = 0
        while i < m:
            t = -1.0 + i * scale
            omega = omega_resonance + Omega * (grid_center - span * t)
            self.omega_guess_list[i] = omega
            dist = omega - omega_resonance
            if dist < 0.0:
                dist = -dist
            if convention >= 2:
                if dist < best_dist - tie_tol:
                    best_dist = dist
                    best_idx = i
                elif dist <= best_dist + tie_tol:
                    if abs(float(i) - centre_idx) < abs(float(best_idx) - centre_idx):
                        best_dist = dist
                        best_idx = i
            elif dist < best_dist:
                best_dist = dist
                best_idx = i
            i += 1

        # Shift so the nearest grid point lands exactly on resonance (and, in
        # convention 2, then by feedback_grid_shift steps: up in frequency for
        # > 0, which moves resonance to fractional index best_idx + shift)
        omega_shift = omega_resonance - self.omega_guess_list[best_idx]
        resonance_index = float(best_idx)
        if convention >= 2:
            omega_shift = omega_shift + self.p.feedback_grid_shift * step
            resonance_index = resonance_index + self.p.feedback_grid_shift
        i = 0
        while i < m:
            omega = self.omega_guess_list[i] + omega_shift
            self.omega_guess_list[i] = omega
            self.omega_sq_list[i] = omega * omega
            i += 1

        self.p.omega_guess_list = self.omega_guess_list
        self.p.feedback_resonance_grid_index = best_idx
        self.p.feedback_resonance_grid_index_frac = resonance_index
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
    def remesh_to_centered(self, omega_center, span_Omega,
                            interpolate_posterior=1,
                            interpolate_states=0,
                            expand_clipped_grid_to_requested_size=1):
        """Re-grid in-place centred on omega_center with half-width span_Omega*Omega.

        Grid order (ascending/descending) is inherited from the existing grid.
        P0 is linearly interpolated (interpolate_posterior=1) or reset to
        uniform 1/m (=0).  Bloch state transferred by nearest-neighbour copy
        (interpolate_states=0) or linear interpolation (interpolate_states=1).

        expand_clipped_grid_to_requested_size (1/0):
          1 — shift omega_center toward the interior so the full requested span
              always fits; grid width is preserved, center may move.
          0 — keep omega_center as-is; symmetrically reduce the span to the
              largest value that fits within the original bounds.  Writes the
              actual span back to self.feedback_remesh_span_Omega.

        No dynamic allocation; compatible with @portable fast-math."""
        interpolate_bool = bool(interpolate_posterior)
        interpolate_states_bool = bool(interpolate_states)
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

        # Clamp so the new grid stays within the original grid bounds.
        # Two modes controlled by expand_clipped_grid_to_requested_size:
        #   1 (expand): shift center toward interior, preserve full span.
        #   0 (clip):   keep center, reduce span symmetrically to fit.
        half_width = step_new * (m - 1) * 0.5
        if half_width < 0.0:
            half_width = -half_width
        clamp_lo = self.omega_original_min + half_width
        clamp_hi = self.omega_original_max - half_width
        if clamp_lo > clamp_hi:
            # Requested span exceeds original grid entirely; center on midpoint.
            omega_center = (self.omega_original_min + self.omega_original_max) * 0.5
            if not expand_clipped_grid_to_requested_size:
                # Shrink span to the largest symmetric fit.
                max_hw = (self.omega_original_max - self.omega_original_min) * 0.5
                if max_hw < 0.0:
                    max_hw = 0.0
                new_span = max_hw / Omega if Omega > 0.0 else span_Omega
                if new_span < span_Omega:
                    span_Omega = new_span
                    if old_step < 0.0:
                        step_new = -(2.0 * span_Omega * Omega) / (m - 1)
                    else:
                        step_new = (2.0 * span_Omega * Omega) / (m - 1)
                    self.feedback_remesh_span_Omega = span_Omega
        elif expand_clipped_grid_to_requested_size:
            # Shift center so the full span fits inside the original bounds.
            if omega_center < clamp_lo:
                omega_center = clamp_lo
            elif omega_center > clamp_hi:
                omega_center = clamp_hi
        else:
            # Keep center; reduce span symmetrically when the grid would overflow.
            if omega_center < clamp_lo or omega_center > clamp_hi:
                dist_lo = omega_center - self.omega_original_min
                dist_hi = self.omega_original_max - omega_center
                if dist_lo < 0.0:
                    dist_lo = 0.0
                if dist_hi < 0.0:
                    dist_hi = 0.0
                max_hw = dist_lo if dist_lo < dist_hi else dist_hi
                new_span = max_hw / Omega if Omega > 0.0 else span_Omega
                if new_span < span_Omega:
                    span_Omega = new_span
                    if old_step < 0.0:
                        step_new = -(2.0 * span_Omega * Omega) / (m - 1)
                    else:
                        step_new = (2.0 * span_Omega * Omega) / (m - 1)
                    self.feedback_remesh_span_Omega = span_Omega

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

        # ── Pass 1.5: compute state transfer into scratch to avoid in-place corruption ──
        # Writing state_x[i] while reading state_x[lo] / state_x[lo+1] is unsafe when
        # lo < i (happens for i > m/2 in a centred shrink), so we stage into scratch first.
        i    = 0
        frac = frac_0
        while i < m:
            lo = int(frac)
            if interpolate_states_bool:
                t_frac = frac - lo
                if lo < 0:
                    self.state_x_scratch[i] = self.state_x[0]
                    self.state_y_scratch[i] = self.state_y[0]
                    self.state_z_scratch[i] = self.state_z[0]
                elif lo >= m - 1:
                    self.state_x_scratch[i] = self.state_x[m - 1]
                    self.state_y_scratch[i] = self.state_y[m - 1]
                    self.state_z_scratch[i] = self.state_z[m - 1]
                else:
                    self.state_x_scratch[i] = self.state_x[lo] + t_frac * (self.state_x[lo + 1] - self.state_x[lo])
                    self.state_y_scratch[i] = self.state_y[lo] + t_frac * (self.state_y[lo + 1] - self.state_y[lo])
                    self.state_z_scratch[i] = self.state_z[lo] + t_frac * (self.state_z[lo + 1] - self.state_z[lo])
            else:
                lo_nearest = lo + 1 if frac - lo >= 0.5 else lo
                if lo_nearest < 0:
                    lo_nearest = 0
                elif lo_nearest >= m:
                    lo_nearest = m - 1
                self.state_x_scratch[i] = self.state_x[lo_nearest]
                self.state_y_scratch[i] = self.state_y[lo_nearest]
                self.state_z_scratch[i] = self.state_z[lo_nearest]
            frac += dfrac
            i    += 1

        # ── Pass 2: write new omega grid, normalised P0, and committed Bloch state ──
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
            self.omega_guess_list[i] = omega # write the new frequency mesh
            self.omega_sq_list[i]    = omega * omega
            self.P0[i]               = p_new # write the interpolated probabilities
            self.state_x[i]          = self.state_x_scratch[i] # write state
            self.state_y[i]          = self.state_y_scratch[i] # write state
            self.state_z[i]          = self.state_z_scratch[i] # write state
            frac  += dfrac
            omega += step_new
            i     += 1
        self.P0_total = 1.0

    @portable(flags={"fast-math"})
    def maybe_remesh(self, posterior_std, omega_center):
        """Narrow the grid and re-centre on omega_center once posterior_std has stayed below
        feedback_remesh_threshold_omega (rad/s). No-op when the threshold is 0. @portable: pass
        omega_center explicitly."""
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
                interpolate_states = self.p.remesh_interpolate_states
                expand_clipped = self.p.remesh_expand_clipped_grid_to_requested_size
                self.remesh_to_centered(omega_center, self.feedback_remesh_span_Omega,
                                        interpolate_posterior, interpolate_states,
                                        expand_clipped)

    def _initialize_measurement_calibrations(self):
        p = self.p
        if np.any(np.ravel(getattr(p, "feedback_apd_map_enabled", False))):
            # no committed experiment ever set this; a file that did must not replay on raw endpoints
            raise ValueError("this run file used the APD affine map, removed 2026-10-30: "
                             "replay it with k-exp 8f98b26e.")
        p.feedback_measurement_midpoint_remap_enabled = bool(p.feedback_measurement_midpoint_remap_enabled)
        p.feedback_measurement_midpoint_fraction = self._resolve_measurement_midpoint_fraction(
            feedback_measurement_midpoint_fraction=p.feedback_measurement_midpoint_fraction,
        )
        p.N_photons_per_shot = float(p.n_photons_per_shot)
        p.v_apd_all_up = float(p.v_apd_all_up)
        p.v_apd_all_down = float(p.v_apd_all_down)
        p.std_n_photons_per_shot = float(p.std_n_photons_per_shot)

        self.v_apd_all_up = p.v_apd_all_up
        self.v_apd_all_down = p.v_apd_all_down
        self.N_photons_per_shot = p.N_photons_per_shot
        self.std_n_photons_per_shot = p.std_n_photons_per_shot
        self.feedback_measurement_midpoint_remap_enabled = p.feedback_measurement_midpoint_remap_enabled
        self.feedback_measurement_midpoint_fraction = p.feedback_measurement_midpoint_fraction
        self.v_range = self.v_apd_all_up - self.v_apd_all_down
        if abs(self.v_range) < 1.0e-15:
            raise ValueError("APD calibration range is zero; cannot normalize APD.")
        # Replay of older per-shot-endpoint runs (data.preshot_endpoints) puts these
        # back after the last shot.
        self.v_apd_all_up_cal = self.v_apd_all_up
        self.v_apd_all_down_cal = self.v_apd_all_down
        self.v_range_cal = self.v_range
        self.N_photons_per_shot_cal = self.N_photons_per_shot
        # sigma <= 0 turns every likelihood into NaN, silently, and @portable never raises: fail here
        if not (self.std_n_photons_per_shot > 0.0):
            raise ValueError(
                "std_n_photons_per_shot must be positive; got "
                f"{self.std_n_photons_per_shot}."
            )

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

### hypothesis grid (p.feedback_grid_convention)
#
# Convention 1 -- every run before 2026-10-28, and any run file without
# feedback_grid_convention: the base parameters are feedback_guess_span_Omega
# (the grid HALF-width, in Omega = pi / t_pi) and feedback_fractional_initial_offset
# (initial drive - resonance, in Omega).
#
# Convention 2 (2026-10-28, user) -- the base parameters are
#   frequency_feedback_grid_full_span  F (Hz): the full grid width; step d = F / (m - 1)
#   feedback_fractional_initial_offset u in [-1, 1]: initial drive - resonance
#       = u * (F/2 - d/2) (> 0: drive above resonance). F/2 - d/2 is the largest
#       offset that keeps resonance off the two edge points, so the shift below
#       can never push it off the grid.
#   feedback_grid_shift s in [-1/2, 1/2]: the grid is first centred as near the
#       initial drive as it can be with one point exactly on resonance (an exact
#       tie goes to the point nearer the grid centre), then moved by s * d (up in
#       frequency for s > 0). Resonance then sits at fractional grid index j0 + s.
# Both conventions feed the kernel the same two Omega-unit numbers,
# feedback_guess_span_Omega and feedback_initial_offset_Omega; under convention 2
# they are derived (ExptParams.compute_feedback_grid in expt_params_feedback) and
# setting them by hand is refused (check_feedback_grid_params).

def map_estimate(P, grid, rel_tol=MAP_TIE_REL_TOL):
    """The posterior maximum of each row of P (..., m), on grid (m,) or (..., m): the grid value,
    or the mean over points tied within rel_tol (the rule of Feedback.map_frequency), for
    scoring a posterior. np.argmax alone settles a tie by grid order."""
    P = np.asarray(P, dtype=float)
    grid = np.broadcast_to(np.asarray(grid, dtype=float), P.shape)
    tied = P >= (1.0 - rel_tol) * P.max(axis=-1, keepdims=True)
    return (grid * tied).sum(axis=-1) / tied.sum(axis=-1)


def feedback_grid_convention(p):
    """The run's grid convention: 1 when the params do not say (older runs)."""
    return int(np.ravel(getattr(p, "feedback_grid_convention", 1))[0])


def feedback_grid_derived(full_span_hz, grid_size, t_raman_pi_pulse, initial_offset_frac):
    """Convention 2 -> (feedback_guess_span_Omega, feedback_initial_offset_Omega).

    Omega in Hz is 1 / (2 t_pi), so the half-width F/2 is F t_pi in Omega, and
    the initial offset u (F/2 - d/2) = u (F/2) (m - 2) / (m - 1) is
    u F t_pi (m - 2) / (m - 1) in Omega. Elementwise on arrays (scanned values);
    scalars in, floats out.
    """
    m = int(grid_size)
    span_Omega = np.asarray(full_span_hz, dtype=float) * np.asarray(t_raman_pi_pulse, dtype=float)
    offset_Omega = np.asarray(initial_offset_frac, dtype=float) * span_Omega * (m - 2) / (m - 1)
    if np.ndim(span_Omega) == 0:
        span_Omega = float(span_Omega)
    if np.ndim(offset_Omega) == 0:
        offset_Omega = float(offset_Omega)
    return span_Omega, offset_Omega


def feedback_offset_frac(steps, grid_size):
    """Convention 2: feedback_fractional_initial_offset for an initial drive `steps`
    grid steps above resonance (< 0: below). The largest allowed is (m - 2) / 2
    steps (= full span / 2 - half a step), u = +-1."""
    return np.asarray(steps, dtype=float) / ((int(grid_size) - 2) / 2.0)


def feedback_hypothesis_grid(omega_resonance, Omega, span_Omega, grid_size, center_Omega,
                             grid_shift=0.0, convention=1, center_exact=1):
    """The grid Feedback._initialize_frequency_grid builds, on the host.

    Returns (omega_grid, best_idx, resonance_index): the grid (rad/s, DESCENDING
    in frequency, as the kernel stores it), the index snapped onto resonance
    before any shift, and resonance's fractional index after it (best_idx +
    grid_shift; = best_idx in convention 1). Convention 1 is exactly what replay
    has done since 2026-09-27, including np.round (half to even) for a centre
    on round(offset) -- the kernel rounds half away from zero, a known
    difference at half-integer offsets of convention-1 runs that predate
    feedback_grid_center_exact_offset.
    """
    m = int(grid_size)
    center = float(center_Omega)
    if convention < 2 and not int(center_exact):
        center = float(np.round(center))
    grid = omega_resonance + Omega * (center - span_Omega * np.linspace(-1.0, 1.0, m))
    dist = np.abs(grid - omega_resonance)
    if convention < 2:
        best_idx = int(np.argmin(dist))
    else:
        # the kernel's loop: a nearer point wins; within tie_tol, the one nearer the centre
        step = abs(Omega * span_Omega * 2.0 / (m - 1))
        tie_tol = 1.0e-6 * step
        centre_idx = 0.5 * (m - 1)
        best_idx, best_dist = 0, 1.0e12
        for i in range(m):
            if dist[i] < best_dist - tie_tol:
                best_idx, best_dist = i, dist[i]
            elif dist[i] <= best_dist + tie_tol and abs(i - centre_idx) < abs(best_idx - centre_idx):
                best_idx, best_dist = i, dist[i]
    grid = grid + (omega_resonance - grid[best_idx])
    resonance_index = float(best_idx)
    if convention >= 2:
        grid = grid + float(grid_shift) * Omega * span_Omega * 2.0 / (m - 1)
        resonance_index += float(grid_shift)
    return grid, best_idx, resonance_index


def check_feedback_grid_params(p, xvars=()):
    """Refuse (ValueError) a hypothesis grid that is out of range or set the
    wrong way, before a run id is used. ``xvars``: the scan's xvar objects; a
    scanned parameter is checked at every one of its values."""
    scanned = {str(x.key): np.ravel(np.asarray(x.values, dtype=float)) for x in xvars}

    def values(key, default):
        if key in scanned:
            return scanned[key]
        return np.ravel(np.asarray(getattr(p, key, default), dtype=float))

    conv = values("feedback_grid_convention", 1.)
    if conv.size != 1 or conv[0] not in (1., 2.):
        raise ValueError(f"feedback_grid_convention must be one fixed value, 1 or 2; got {conv}")
    shift = values("feedback_grid_shift", 0.)
    if int(conv[0]) < 2:
        if np.any(shift != 0.):
            raise ValueError("feedback_grid_shift is a feedback_grid_convention 2 parameter; "
                             f"convention 1 has no grid shift (got {shift})")
        return
    problems = []
    m = values("feedback_grid_size", 0.)
    if m.size != 1 or m[0] < 3:
        problems.append(f"feedback_grid_size must be one fixed value >= 3 (got {m}): with fewer "
                        "points resonance would sit on an edge point")
    span = values("frequency_feedback_grid_full_span", np.nan)
    if not (np.all(np.isfinite(span)) and np.all(span > 0.)):
        problems.append(f"frequency_feedback_grid_full_span must be finite and > 0 Hz (got {span})")
    u = values("feedback_fractional_initial_offset", np.nan)
    if not (np.all(np.isfinite(u)) and np.all(np.abs(u) <= 1. + 1.e-12)):
        problems.append("feedback_fractional_initial_offset is the fraction of the largest allowed "
                        f"initial offset (full span / 2 - one half step) and must lie in [-1, 1] (got {u})")
    if not (np.all(np.isfinite(shift)) and np.all(np.abs(shift) <= 0.5 + 1.e-12)):
        problems.append(f"feedback_grid_shift is in grid steps and must lie in [-1/2, 1/2] (got {shift})")
    if "feedback_guess_span_Omega" in scanned or "feedback_initial_offset_Omega" in scanned:
        problems.append("feedback_guess_span_Omega / feedback_initial_offset_Omega are derived under "
                        "feedback_grid_convention 2; scan frequency_feedback_grid_full_span / "
                        "feedback_fractional_initial_offset instead")
    derived = getattr(p, "_feedback_guess_span_Omega_derived", None)
    if derived is not None and np.any(np.ravel(p.feedback_guess_span_Omega) != np.ravel(derived)):
        problems.append(
            f"feedback_guess_span_Omega was set by hand ({p.feedback_guess_span_Omega}), but under "
            "feedback_grid_convention 2 it is derived from frequency_feedback_grid_full_span (Hz) and "
            "would be overwritten. Set the full span in Hz, or set feedback_grid_convention = 1 for "
            "the old meaning of feedback_guess_span_Omega and feedback_fractional_initial_offset (Omega)")
    if problems:
        raise ValueError("hypothesis grid (feedback_grid_convention 2) refused:\n  - "
                         + "\n  - ".join(problems))

### randomized raman pulse times
#
# One place where a shot's list of raman pulse times is drawn, so the live
# feedback loop (base_expt_feedback.FeedbackExpt), the rabi-posterior pulse
# train (rabi_posterior_pulse_train) and the host-side analyses
# (kexp.analysis.feedback, kexp.analysis.rabi_posterior) all agree
# bit-for-bit.


def new_t_raman_pulse_seed(t_raman_pulse_seed):
    """Seed for one shot's raman pulse-time list.

    Returns `t_raman_pulse_seed` when it is nonzero (so a seed can be pinned or
    scanned); otherwise draws a fresh one from entropy, which is what gives
    every shot of a repeat-averaged run its own pulse sequence. Kept to 31 bits
    and nonzero so it stays int32-typed on the kernel.
    """
    seed = int(t_raman_pulse_seed)
    if seed == 0:
        seed = int(np.random.SeedSequence().generate_state(1)[0] >> 1)
        if seed == 0:
            seed = 1
    return seed


def draw_t_raman_pulse_list(seed, N_pulses, t_raman_pi_pulse,
                            t_raman_pulse_min_frac_pi,
                            t_raman_pulse_max_frac_pi):
    """Raman pulse times for one shot, as a pure function of `seed`.

    Each pulse is drawn independently, uniform in
    [min_frac_pi, max_frac_pi] * t_raman_pi_pulse, then rounded to whole ns so
    that kernel delays and the mu conversion in compute_t_between_pulses_mu
    agree exactly with the values saved to data.t_raman_pulse. Equal seeds give
    identical lists, so repeating (or scanning) a seed replays the same pulse
    sequence.
    """
    t_pi = float(t_raman_pi_pulse)
    rng = np.random.default_rng(int(seed))
    t_list = rng.uniform(float(t_raman_pulse_min_frac_pi) * t_pi,
                         float(t_raman_pulse_max_frac_pi) * t_pi,
                         int(N_pulses))
    return np.round(t_list * 1.e9) * 1.e-9


def draw_t_raman_pulse_list_blocks(seed, N_pulses, t_raman_pi_pulse,
                                   t_raman_pulse_min_frac_pi,
                                   t_raman_pulse_max_frac_pi,
                                   n_random_per_block, n_const_per_block,
                                   const_frac_pi):
    """Alternating random / constant pulse-time schedule, one shot.

    Repeats [n_random_per_block random pulses, n_const_per_block constant
    pulses at const_frac_pi*t_pi] until N_pulses is filled. Like
    draw_t_raman_pulse_list this is a pure function of `seed` and rounds to
    whole ns, so a shot replays exactly.

    Constant pulses sharpen (the angle accumulates) but alias; random pulses break the aliases, and
    come first because back-action favours early pulses. Best measured: R3 C7 x2, RMSE 73.5 Hz against
    117.1 Hz all random (N_pulses 20, N_repeats 20, 20-200 kHz grid).

    NOT SAFE AT LOW N_repeats: at N_repeats = 1 every hybrid failed (> 5 kHz) on 0.8-6.7 % of shots
    where all-random failed on 0 %. Below N_repeats ~ 10, set t_raman_pulse_block_bool = 0.
    """
    t_pi = float(t_raman_pi_pulse)
    n_r = max(int(n_random_per_block), 0)
    n_c = max(int(n_const_per_block), 0)
    N = int(N_pulses)
    if n_r + n_c <= 0:
        raise ValueError("block must contain at least one pulse")

    rng = np.random.default_rng(int(seed))
    lo = float(t_raman_pulse_min_frac_pi) * t_pi
    hi = float(t_raman_pulse_max_frac_pi) * t_pi
    t_const = float(const_frac_pi) * t_pi

    out = np.empty(N, dtype=float)
    i = 0
    while i < N:
        for _ in range(n_r):
            if i >= N:
                break
            out[i] = rng.uniform(lo, hi)
            i += 1
        for _ in range(n_c):
            if i >= N:
                break
            out[i] = t_const
            i += 1
    return np.round(out * 1.e9) * 1.e-9


class RandomRamanPulseTimes:
    """Mixin giving an experiment a per-shot randomized raman pulse-time list.

    Expects self.p to carry N_pulses, t_raman_pulse, t_raman_pi_pulse,
    t_raman_pulse_random_bool, t_raman_pulse_seed, t_raman_pulse_min_frac_pi
    and t_raman_pulse_max_frac_pi (all declared in expt_params_feedback.py).

    Both methods are RPCs, so a kernel calls them with slack in hand
    (core.wait_until_mu(now_mu()) ... core.break_realtime()). Draw the list at
    the top of scan_kernel and save the seed alongside the drawn times, so the
    shot can be replayed exactly.
    """

    @rpc
    def resolve_t_raman_pulse_seed(self) -> TInt32:
        """Seed for this shot's pulse-time list.

        Returns p.t_raman_pulse_seed (possibly scanned via xvar) when nonzero;
        otherwise a fresh seed drawn from entropy.
        """
        return new_t_raman_pulse_seed(self.p.t_raman_pulse_seed)

    @rpc
    def get_new_t_raman_pulse_list(self, seed=0) -> TArray(TFloat):
        """This shot's raman pulse times, as a pure function of `seed`.

        With t_raman_pulse_random_bool = 0, returns a constant list at the
        scalar p.t_raman_pulse (the pre-randomization behavior).
        """
        if not self.p.t_raman_pulse_random_bool:
            self.p.t_raman_pulse_list = np.full(self.p.N_pulses,
                                                self.p.t_raman_pulse)
            return self.p.t_raman_pulse_list
        # off unless a params file opts in; see draw_t_raman_pulse_list_blocks
        if getattr(self.p, "t_raman_pulse_block_bool", 0):
            self.p.t_raman_pulse_list = draw_t_raman_pulse_list_blocks(
                seed=seed,
                N_pulses=self.p.N_pulses,
                t_raman_pi_pulse=self.p.t_raman_pi_pulse,
                t_raman_pulse_min_frac_pi=self.p.t_raman_pulse_min_frac_pi,
                t_raman_pulse_max_frac_pi=self.p.t_raman_pulse_max_frac_pi,
                n_random_per_block=self.p.t_raman_pulse_n_random_per_block,
                n_const_per_block=self.p.t_raman_pulse_n_const_per_block,
                const_frac_pi=self.p.t_raman_pulse_const_frac_pi)
            return self.p.t_raman_pulse_list
        self.p.t_raman_pulse_list = draw_t_raman_pulse_list(
            seed=seed,
            N_pulses=self.p.N_pulses,
            t_raman_pi_pulse=self.p.t_raman_pi_pulse,
            t_raman_pulse_min_frac_pi=self.p.t_raman_pulse_min_frac_pi,
            t_raman_pulse_max_frac_pi=self.p.t_raman_pulse_max_frac_pi)
        return self.p.t_raman_pulse_list


def _feedback_kwargs_from_atomdata(ad):
    p = getattr(ad, "p", None)
    if p is None:
        return {}

    return {
        "t_raman_pulse": p.t_raman_pulse,
        # datasets predating the turn-on-delay param used the same time for
        # both effective and ideal pulse
        "t_raman_pulse_ideal": getattr(p, "t_raman_pulse_ideal", p.t_raman_pulse),
        # None: the dataset predates the parameter; replay falls back to t_raman_pulse_ideal
        "t_raman_pulse_offset": getattr(p, "t_raman_pulse_offset", None),
        "t_img_pulse": p.t_img_pulse,
        "amp_imaging": p.amp_imaging,
        "t_raman_pi_pulse": p.t_raman_pi_pulse,
        "frequency_resonance": p.frequency_raman_transition,
        "frequency_z_lightshift": p.frequency_lightshift,
        "v_apd_all_up": p.v_apd_all_up,
        "v_apd_all_down": p.v_apd_all_down,
        "n_photons_per_shot": p.n_photons_per_shot,
        "std_n_photons_per_shot": p.std_n_photons_per_shot,
        "feedback_measurement_midpoint_fraction": p.feedback_measurement_midpoint_fraction,
        "feedback_measurement_midpoint_remap_enabled": p.feedback_measurement_midpoint_remap_enabled,
        "feedback_grid_size": int(p.feedback_grid_size),
        "fractional_grid_center_offset": float(p.feedback_fractional_grid_center_offset) if hasattr(p, "feedback_fractional_grid_center_offset") else None,
        "fractional_initial_offset": p.feedback_fractional_initial_offset,
        "guess_span_Omega": float(p.feedback_guess_span_Omega),
        # the state-dependent read model (absent before 2026-10-11: 0 = off)
        "read_twist_per_sz": float(getattr(p, "read_twist_per_sz", 0.0)),
        "back_action_coherence_slope": float(getattr(p, "back_action_coherence_slope", 0.0)),
        "read_alpha_lightshift": float(getattr(p, "read_alpha_lightshift", float("nan"))),
    }