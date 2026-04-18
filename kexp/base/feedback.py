from artiq.experiment import kernel, portable
import numpy as np
from kexp.calibrations.imaging import integrator_calibration, imaging_lightshift


class Feedback:
    kernel_invariants = {
        "m",
        "dt",
        "dt_z",
        "Omega",
        "omega_z_lightshift",
        "omega_guess_start",
        "N_photons_per_shot",
        "n_photons_halfway",
        "v_apd_all_up",
        "v_apd_all_down",
        "v_range",
        "omega_guess_list",
        "omega_sq_list",
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
        t_img_pulse=None,
        amp_imaging=None,
        t_raman_pi_pulse=None,
        frequency_resonance=None,
        frequency_z_lightshift=None,
        v_apd_all_up=None,
        v_apd_all_down=None,
        n_photons_per_shot=None,
        photon_count_scale=0.1,
        m=21,
        fractional_initial_offset=-5.0,
        guess_span_Omega=5.0,
        lut_size=4096):
        self._initialize_timing(
            m=m,
            t_raman_pulse=t_raman_pulse,
            t_img_pulse=t_img_pulse,
            t_raman_pi_pulse=t_raman_pi_pulse,
        )
        self._initialize_lightshift(
            amp_imaging=amp_imaging,
            frequency_z_lightshift=frequency_z_lightshift,
        )
        self._initialize_frequency_grid(
            frequency_resonance=frequency_resonance,
            fractional_initial_offset=fractional_initial_offset,
            guess_span_Omega=guess_span_Omega,
        )
        self._initialize_measurement_state(
            amp_imaging=amp_imaging,
            t_img_pulse=t_img_pulse,
            n_photons_per_shot=n_photons_per_shot,
            v_apd_all_up=v_apd_all_up,
            v_apd_all_down=v_apd_all_down,
            photon_count_scale=photon_count_scale,
        )
        self._initialize_posterior_state()
        self._initialize_trig_lut(lut_size=lut_size)
        self.n_photons_halfway = self.convert_measurement((self.v_apd_all_up + self.v_apd_all_down) / 2.0)

    def _initialize_timing(
        self,
        m,
        t_raman_pulse,
        t_img_pulse,
        t_raman_pi_pulse,
    ):
        self.m = int(m)
        self.Omega = np.pi / t_raman_pi_pulse

        # dt and dt_z are always the Raman pulse and imaging pulse lengths
        self.dt = float(t_raman_pulse)
        self.dt_z = float(t_img_pulse)

    def _initialize_lightshift(
        self,
        amp_imaging,
        frequency_z_lightshift,
    ):
        self.p.frequency_lightshift = self._resolve_lightshift_calibration(
            amp_imaging=amp_imaging,
            frequency_z_lightshift=frequency_z_lightshift,
        )
        self.frequency_z_lightshift = self.p.frequency_lightshift
        self.omega_z_lightshift = 2.0 * np.pi * self.frequency_z_lightshift

    def _initialize_frequency_grid(
        self,
        frequency_resonance,
        fractional_initial_offset,
        guess_span_Omega,
    ):
        omega_resonance = 2.0 * np.pi * float(frequency_resonance)
        self.omega_guess_start = omega_resonance + self.Omega * float(fractional_initial_offset)
        self.omega_guess_list = omega_resonance + 2.0 * float(guess_span_Omega) * self.Omega * np.linspace(-1.0, 1.0, self.m)
        self.p.omega_guess_list = self.omega_guess_list
        self.omega_raman = self.omega_guess_start
        self.omega_sq_list = self.omega_guess_list * self.omega_guess_list

    def _initialize_measurement_state(
        self,
        amp_imaging,
        t_img_pulse,
        n_photons_per_shot,
        v_apd_all_up,
        v_apd_all_down,
        photon_count_scale,
    ):
        (
            self.p.N_photons_per_shot,
            self.p.v_apd_all_up,
            self.p.v_apd_all_down,
        ) = self._resolve_measurement_calibration(
            amp_imaging=amp_imaging,
            t_img_pulse=t_img_pulse,
            n_photons_per_shot=n_photons_per_shot,
            v_apd_all_up=v_apd_all_up,
            v_apd_all_down=v_apd_all_down,
            photon_count_scale=photon_count_scale,
        )
        self.v_apd_all_up = self.p.v_apd_all_up
        self.v_apd_all_down = self.p.v_apd_all_down
        self.N_photons_per_shot = self.p.N_photons_per_shot
        self.v_range = self.v_apd_all_up - self.v_apd_all_down

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

        if len(missing_fields) == 0:
            return float(n_photons_per_shot), float(v_apd_all_up), float(v_apd_all_down)

        if amp_imaging is None or t_img_pulse is None:
            raise ValueError(
                "Missing calibration fields require amp_imaging and t_img_pulse for integrator_calibration fallback."
            )

        (n_cal, v_up_cal, v_down_cal) = integrator_calibration(
            amp_imaging=float(amp_imaging),
            t_imaging=float(t_img_pulse),
        )

        # Keep historical behavior for calibration-derived photon counts.
        n_cal = float(n_cal) * float(photon_count_scale)

        if n_photons_per_shot is None:
            n_photons_per_shot = n_cal
        if v_apd_all_up is None:
            v_apd_all_up = v_up_cal
        if v_apd_all_down is None:
            v_apd_all_down = v_down_cal

        print(
            "Feedback: using integrator_calibration fallback "
            f"(amp_imaging={float(amp_imaging)}, t_img_pulse={float(t_img_pulse)} s) "
            f"for missing fields: {', '.join(missing_fields)}"
        )

        return float(n_photons_per_shot), float(v_apd_all_up), float(v_apd_all_down)

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
            "Feedback: using imaging_lightshift fallback "
            f"(amp_imaging={float(amp_imaging)}) for missing field: frequency_z_lightshift"
        )

        return float(frequency_z_lightshift)

    @staticmethod
    def compute_t_between_pulses_mu(
        t_calculation_slack_compensation_mu,
        t_raman_pulse,
        t_img_pulse,
        t_integrator_stop_settle_sample_mu=3600,
        t_set_raman_mu=1256,
    ):
        t_raman_pulse_mu = np.int64(t_raman_pulse * 1.0e9)
        t_img_pulse_mu = np.int64(t_img_pulse * 1.0e9)
        return int(
            int(t_calculation_slack_compensation_mu)
            + int(t_integrator_stop_settle_sample_mu)
            + int(t_set_raman_mu)
            + int(t_raman_pulse_mu)
            + int(t_img_pulse_mu)
        )

    @kernel
    def initialize_feedback(self):
        """Warm up posterior runtime once, then reset state/P0 arrays."""

        self.core.wait_until_mu(self.core.get_rtio_counter_mu())
        self.generate_posterior(self.n_photons_halfway, 1.0e-6, do_it=True)
        self.core.break_realtime()

        t0 = self.core.get_rtio_counter_mu()
        self.core.wait_until_mu(t0)
        self.generate_posterior(self.n_photons_halfway, 1.0e-6, do_it=True)
        self.t_posterior_mu = abs(t0 - self.core.get_rtio_counter_mu())
        self.core.break_realtime()
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
    def convert_measurement(self, v_apd):
        return round(self.N_photons_per_shot * (v_apd - self.v_apd_all_down) / self.v_range)

    @portable(flags={"fast-math"})
    def generate_posterior(self, k, t, do_it=True):
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
        dt = self.dt
        dt_z = self.dt_z

        if m > 1:
            domega = omega_guess_list[1] - omega_guess_list[0]
        else:
            domega = 0.0

        omega0 = omega_guess_list[0]

        (sin_wt, cos_wt) = self.sincos_lut_interp(-(omega0 - omega_raman) * t)
        (sin_wt_step, cos_wt_step) = self.sincos_lut_interp(-domega * t)

        alpha_z_lightshift = self.omega_z_lightshift * dt_z
        alpha_z = -dt * (omega_raman - omega0) - alpha_z_lightshift
        (sin_z, cos_z) = self.sincos_lut_interp(alpha_z)
        alpha_z_step = dt * domega
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
                (sin_H, cos_H) = self.sincos_lut_interp(dt * norm_H)
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
            if do_it:
                state_x[j] = nx
                state_y[j] = ny
                state_z[j] = hz

            p1 = (1.0 + hz) / 2.0
            q = 1.0 - p1
            p1_pow = self.powi(p1, k_int)
            q_pow = self.powi(q, nk_int)
            pj = P0[j] * p1_pow * q_pow

            P0_total += pj
            mn += pj * omega
            moment_2 += pj * omega_sq_list[j]

            if do_it:
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
            return self.omega_raman, 0.0

        mn = mn / P0_total
        moment_2 = moment_2 / P0_total

        if do_it:
            i = 0
            while i < len(P0):
                P0[i] = P0[i] / P0_total
                i += 1

        self.P0_total = P0_total
        var = moment_2 - mn * mn
        if var < 0.0:
            var = 0.0
        std = np.sqrt(var)
        return mn, std

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

    def _propagate_true_state(self, state, omega_ctrl, omega_true, t, Omega, dt, dt_z, omega_z_lightshift):
        sx = state[0]
        sy = state[1]
        sz = state[2]

        delta_omega = omega_ctrl - omega_true
        norm_H = np.sqrt(Omega * Omega + delta_omega * delta_omega)

        if norm_H > 0.0:
            inv_norm_H = 1.0 / norm_H
            ux = (Omega * inv_norm_H) * np.cos(delta_omega * t)
            uy = (Omega * inv_norm_H) * np.sin(delta_omega * t)
            uz = delta_omega * inv_norm_H
            alpha_H = dt * norm_H
            sin_H = np.sin(alpha_H)
            cos_H = np.cos(alpha_H)
        else:
            ux = 0.0
            uy = 0.0
            uz = 0.0
            sin_H = 0.0
            cos_H = 1.0

        one_minus_cos = 1.0 - cos_H

        uxux = ux * ux
        uyuy = uy * uy
        uzuz = uz * uz
        uxuy = ux * uy
        uxuz = ux * uz
        uyuz = uy * uz

        hx = (cos_H + one_minus_cos * uxux) * sx
        hx += (one_minus_cos * uxuy - sin_H * uz) * sy
        hx += (one_minus_cos * uxuz + sin_H * uy) * sz

        hy = (one_minus_cos * uxuy + sin_H * uz) * sx
        hy += (cos_H + one_minus_cos * uyuy) * sy
        hy += (one_minus_cos * uyuz - sin_H * ux) * sz

        hz = (one_minus_cos * uxuz - sin_H * uy) * sx
        hz += (one_minus_cos * uyuz + sin_H * ux) * sy
        hz += (cos_H + one_minus_cos * uzuz) * sz

        alpha_z = -dt * delta_omega - omega_z_lightshift * dt_z
        sin_z = np.sin(alpha_z)
        cos_z = np.cos(alpha_z)

        nx = cos_z * hx + sin_z * hy
        ny = -sin_z * hx + cos_z * hy
        return np.array([nx, ny, hz], dtype=np.float64)

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

    def simulate_from_atomdata(
        self,
        ad,
        frequency_true=None,
        pulse_times=None,
        frequency_raman=None,
        dt=None,
        dt_z=None,
        frequency_rabi=None,
        frequency_z_lightshift=None,
        N_photons_per_shot=None,
        v_apd_all_up=None,
        v_apd_all_down=None,
        n_photons_per_us_per_imgamp=431.77,
        photon_scale=0.1,
        sample_apd=True,
        rng_seed=None,
    ):
        if pulse_times is not None:
            t_arr = pulse_times
        elif hasattr(ad.data, "t"):
            t_arr = ad.data.t
        elif hasattr(ad.data, "t_s_z"):
            t_arr = ad.data.t_s_z
        else:
            raise ValueError("No time array found: expected ad.data.t or ad.data.t_s_z, or provide pulse_times override.")

        if frequency_raman is not None:
            frequency_arr = frequency_raman
        elif hasattr(ad.data, "frequency_raman"):
            frequency_arr = ad.data.frequency_raman
        elif hasattr(ad.data, "omega_raman"):
            frequency_arr = np.asarray(ad.data.omega_raman) / (2.0 * np.pi)
        else:
            raise ValueError("No Raman frequency array found: expected ad.data.frequency_raman or ad.data.omega_raman, or provide frequency_raman override.")

        apd_arr = ad.data.apd

        t_rr = self._ensure_repeat_axis0(t_arr, "pulse_times")
        frequency_rr = self._ensure_repeat_axis0(frequency_arr, "frequency_raman")
        apd_rr = self._ensure_repeat_axis0(apd_arr, "apd")

        if t_rr.shape != frequency_rr.shape:
            raise ValueError(f"time and frequency_raman must have same shape, got {t_rr.shape} and {frequency_rr.shape}.")
        if apd_rr.shape != t_rr.shape:
            raise ValueError(f"apd and time must have same shape, got {apd_rr.shape} and {t_rr.shape}.")

        N_repeat, N_step = t_rr.shape

        if frequency_true is None:
            frequency_true = ad.p.frequency_raman_transition
        if dt is None:
            dt = ad.p.t_raman_pulse
        if dt_z is None:
            dt_z = ad.p.t_img_pulse
        if frequency_rabi is None:
            frequency_rabi = 1.0 / (2.0 * ad.p.t_raman_pi_pulse)
        if frequency_z_lightshift is None:
            frequency_z_lightshift = ad.p.frequency_lightshift

        omega_true = 2.0 * np.pi * frequency_true
        Omega = 2.0 * np.pi * frequency_rabi
        omega_z_lightshift = 2.0 * np.pi * frequency_z_lightshift

        if N_photons_per_shot is None:
            if hasattr(ad.p, "N_photons_per_shot"):
                N_photons_per_shot = ad.p.N_photons_per_shot
            elif hasattr(ad.p, "amp_imaging") and hasattr(ad.p, "t_img_pulse"):
                N_photons_per_shot = (
                    n_photons_per_us_per_imgamp
                    * ad.p.amp_imaging
                    * ad.p.t_img_pulse
                    * 1.0e6
                    * photon_scale
                )
            else:
                N_photons_per_shot = self.N_photons_per_shot
        if v_apd_all_up is None:
            if not hasattr(ad.p, "v_apd_all_up"):
                raise ValueError("ad.p.v_apd_all_up is missing. Provide v_apd_all_up override.")
            v_apd_all_up = ad.p.v_apd_all_up
        if v_apd_all_down is None:
            if not hasattr(ad.p, "v_apd_all_down"):
                raise ValueError("ad.p.v_apd_all_down is missing. Provide v_apd_all_down override.")
            v_apd_all_down = ad.p.v_apd_all_down

        denom = (v_apd_all_up - v_apd_all_down)
        pop_meas_rr = (apd_rr - v_apd_all_down) / denom

        if N_photons_per_shot <= 0:
            raise ValueError("N_photons_per_shot must be positive.")

        rng = np.random.default_rng(rng_seed)
        repeat_results = []

        for r in range(N_repeat):
            tr = t_rr[r]
            fr = frequency_rr[r]

            pop_sim = np.zeros(N_step, dtype=np.float64)
            pop_sampled = np.zeros(N_step, dtype=np.float64)

            state = np.array([0.0, 0.0, 1.0], dtype=np.float64)
            pop_sim[0] = (1.0 + state[2]) / 2.0

            if sample_apd:
                k0 = rng.binomial(int(round(N_photons_per_shot)), pop_sim[0])
                pop_sampled[0] = k0 / float(N_photons_per_shot)
            else:
                pop_sampled[0] = pop_sim[0]

            i = 1
            while i < N_step:
                t_step = tr[i - 1]
                omega_ctrl = 2.0 * np.pi * fr[i - 1]
                state = self._propagate_true_state(
                    state,
                    omega_ctrl=omega_ctrl,
                    omega_true=omega_true,
                    t=t_step,
                    Omega=Omega,
                    dt=dt,
                    dt_z=dt_z,
                    omega_z_lightshift=omega_z_lightshift,
                )
                pop_sim[i] = (1.0 + state[2]) / 2.0
                if sample_apd:
                    ki = rng.binomial(int(round(N_photons_per_shot)), pop_sim[i])
                    pop_sampled[i] = ki / float(N_photons_per_shot)
                else:
                    pop_sampled[i] = pop_sim[i]
                i += 1

            repeat_results.append(
                {
                    "repeat_index": r,
                    "time_s": tr.copy(),
                    "frequency_raman_hz": fr.copy(),
                    "omega_raman_rad_s": 2.0 * np.pi * fr.copy(),
                    "pop_sim": pop_sim,
                    "pop_sim_sampled": pop_sampled,
                    "pop_meas": pop_meas_rr[r].copy(),
                }
            )

        frequency_equal = np.all(frequency_rr == frequency_rr[0:1, :])
        time_equal = np.all(t_rr == t_rr[0:1, :])
        has_identical_trajectories = bool(frequency_equal and time_equal)

        result = {
            "metadata": {
                "run_id": getattr(getattr(ad, "run_info", object()), "run_id", None),
                "N_repeat": int(N_repeat),
                "N_step": int(N_step),
                "trajectory_match_mode": "exact_per_step",
            },
            "params_used": {
                "frequency_true_hz": float(frequency_true),
                "omega_true_rad_s": float(omega_true),
                "dt_s": float(dt),
                "dt_z_s": float(dt_z),
                "frequency_rabi_hz": float(frequency_rabi),
                "Omega_rad_s": float(Omega),
                "frequency_z_lightshift_hz": float(frequency_z_lightshift),
                "omega_z_lightshift_rad_s": float(omega_z_lightshift),
                "N_photons_per_shot": float(N_photons_per_shot),
                "v_apd_all_up": float(v_apd_all_up),
                "v_apd_all_down": float(v_apd_all_down),
            },
            "repeat_results": repeat_results,
            "aggregate": {
                "has_identical_trajectories": has_identical_trajectories,
            },
        }

        if has_identical_trajectories:
            pop_sim_all = np.array([rr["pop_sim"] for rr in repeat_results])
            pop_meas_all = np.array([rr["pop_meas"] for rr in repeat_results])
            result["aggregate"]["time_s"] = t_rr[0].copy()
            result["aggregate"]["pop_sim_mean"] = np.mean(pop_sim_all, axis=0)
            result["aggregate"]["pop_meas_mean"] = np.mean(pop_meas_all, axis=0)
            result["aggregate"]["pop_meas_std"] = np.std(pop_meas_all, axis=0)

        return result

    def plot_simulation_result(
        self,
        result,
        use_sampled=False,
        ax=None,
        figsize=(7, 4),
        title=None,
        alpha_repeat=0.55,
        lw=1.5,
        marker="o",
        ms=3,
        capsize=3,
        show_legend=True,
    ):
        import matplotlib.pyplot as plt

        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        else:
            fig = ax.figure

        agg = result["aggregate"]
        same = agg["has_identical_trajectories"]

        if same:
            t = agg["time_s"]
            ax.plot(t, agg["pop_sim_mean"], label="sim mean", linewidth=lw)
            ax.errorbar(
                t,
                agg["pop_meas_mean"],
                yerr=agg["pop_meas_std"],
                fmt=marker,
                markersize=ms,
                capsize=capsize,
                label="meas mean +/- std",
            )
        else:
            for rr in result["repeat_results"]:
                t = rr["time_s"]
                y_sim = rr["pop_sim_sampled"] if use_sampled else rr["pop_sim"]
                idx = rr["repeat_index"]
                ax.plot(t, y_sim, linewidth=lw, alpha=alpha_repeat, label=f"sim r{idx}")
                ax.plot(t, rr["pop_meas"], marker=marker, markersize=ms, alpha=alpha_repeat, label=f"meas r{idx}")

        ax.set_xlabel("time (s)")
        ax.set_ylabel("normalized population")

        run_id = result["metadata"].get("run_id")
        if title is None:
            if run_id is None:
                title = "feedback simulation"
            else:
                title = f"run {run_id} | feedback simulation"
        ax.set_title(title)

        if show_legend:
            ax.legend()

        return fig, ax
