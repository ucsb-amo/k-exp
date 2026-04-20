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
        "dt",
        "dt_z",
        "omega_z_lightshift",
        "omega_guess_start",
        "N_photons_per_shot",
        "std_n_photons_per_shot",
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
        std_n_photons_per_shot=None,
        photon_count_scale=1.0,
        m=21,
        fractional_initial_offset=-5.0,
        guess_span_Omega=5.0,
        lut_size=4096):

        if not hasattr(self, "p"):
            self.p = _FeedbackParamStore()

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
        self._initialize_measurement_calibrations(
            amp_imaging=amp_imaging,
            t_img_pulse=t_img_pulse,
            n_photons_per_shot=n_photons_per_shot,
            std_n_photons_per_shot=std_n_photons_per_shot,
            v_apd_all_up=v_apd_all_up,
            v_apd_all_down=v_apd_all_down,
            photon_count_scale=photon_count_scale
        )
        self._initialize_posterior_state()
        self._initialize_trig_lut(lut_size=lut_size)

    @portable(flags={"fast-math"})
    def convert_measurement(self, v_apd):
        return round(self.N_photons_per_shot * (v_apd - self.v_apd_all_down) / self.v_range)

    @portable(flags={"fast-math"})
    def generate_posterior(self, k, t,
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
        dt = self.dt
        dt_z = self.dt_z

        if include_photon_noise:
            sigma = self.std_n_photons_per_shot
            sigma_sq = sigma * sigma
            n_sq = n_photons * n_photons
        else:
            sigma = 0.
            sigma_sq = 0.
            n_sq = 0

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

            state_x[j] = nx
            state_y[j] = ny
            state_z[j] = hz

            p1 = (1.0 + hz) / 2.0
            q = 1.0 - p1
            npq = n_photons * p1 * q + sigma_sq
            num = k - n_photons * p1
            if include_photon_noise:
                pj = P0[j] * sigma / np.sqrt(npq) * np.exp(-num * num / (2.0 * npq))
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
        )

    @kernel
    def initialize_feedback(self):
        """Warm up posterior runtime once, then reset state/P0 arrays."""

        n_test = int(self.N_photons_per_shot / 2)

        self.core.wait_until_mu(self.core.get_rtio_counter_mu())
        self.generate_posterior(n_test, 1.0e-6)
        self.core.break_realtime()

        t0 = self.core.get_rtio_counter_mu()
        self.core.wait_until_mu(t0)
        self.generate_posterior(n_test, 1.0e-6)
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

    def _initialize_measurement_calibrations(
        self,
        amp_imaging,
        t_img_pulse,
        n_photons_per_shot,
        std_n_photons_per_shot,
        v_apd_all_up,
        v_apd_all_down,
        photon_count_scale,
    ):
        (
            self.p.N_photons_per_shot,
            self.p.v_apd_all_up,
            self.p.v_apd_all_down,
            self.p.std_n_photons_per_shot,
        ) = self._resolve_measurement_calibration(
            amp_imaging=amp_imaging,
            t_img_pulse=t_img_pulse,
            n_photons_per_shot=n_photons_per_shot,
            std_n_photons_per_shot=std_n_photons_per_shot,
            v_apd_all_up=v_apd_all_up,
            v_apd_all_down=v_apd_all_down,
            photon_count_scale=photon_count_scale,
        )
        self.v_apd_all_up = self.p.v_apd_all_up
        self.v_apd_all_down = self.p.v_apd_all_down
        self.N_photons_per_shot = self.p.N_photons_per_shot
        self.std_n_photons_per_shot = self.p.std_n_photons_per_shot
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
            "Feedback: using integrator_calibration:\n"
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
            "Feedback: using imaging_lightshift fallback "
            f"(amp_imaging={float(amp_imaging)}) for missing field: frequency_z_lightshift\n"
            f"  frequency_z_lightshift = {frequency_z_lightshift}"
        )

        return float(frequency_z_lightshift)

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
        "t_raman_pulse": getattr(p, "t_raman_pulse", None),
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
        "m": int(getattr(p, "feedback_grid_size", 21)),
        "fractional_initial_offset": float(getattr(p, "feedback_fractional_initial_offset", -5.0)),
        "guess_span_Omega": float(getattr(p, "feedback_guess_span_Omega", 5.0)),
    }


class FeedbackReplayResult:
    """Structured replay result with natural attributes for notebook use."""

    def __init__(self):
        self.metadata = {}
        self.params = {}

        self.t = None
        self.apd = None
        self.k = None
        self.s_z = None
        self.state = None
        self.omega_raman = None
        self.omega_raman_computed = None
        self.Omega = None
        self.Omega_computed = None

        self.t_rr = None
        self.apd_rr = None
        self.k_rr = None
        self.s_z_rr = None
        self.state_rr = None
        self.omega_raman_rr = None
        self.omega_raman_computed_rr = None
        self.Omega_rr = None
        self.Omega_computed_rr = None
        self.P0_total_rr = None

    def to_dict(self):
        repeat_results = []
        n_repeat = int(self.metadata.get("N_repeat", 0))
        for r in range(n_repeat):
            repeat_results.append(
                {
                    "repeat_index": int(r),
                    "time_s": self.t_rr[r].copy(),
                    "apd_v": self.apd_rr[r].copy(),
                    "k_photons": self.k_rr[r].copy(),
                    "state": self.state_rr[r].copy(),
                    "state_z_center": self.s_z_rr[r].copy(),
                    "omega_raman_used_rad_s": self.omega_raman_rr[r].copy(),
                    "omega_raman_computed_rad_s": self.omega_raman_computed_rr[r].copy(),
                    "Omega_used_rad_s": self.Omega_rr[r].copy(),
                    "Omega_computed_rad_s": self.Omega_computed_rr[r].copy(),
                    "P0_total": float(self.P0_total_rr[r]),
                }
            )

        aggregate = {
            "has_identical_times": _all_rows_equal(self.t_rr),
            "has_identical_k": _all_rows_equal(self.k_rr.astype(np.float64)),
            "has_identical_omega_used": _all_rows_equal(self.omega_raman_rr),
            "has_identical_Omega_used": _all_rows_equal(self.Omega_rr),
            "time_s": self.t.copy(),
            "k_mean": np.mean(self.k_rr, axis=0),
            "k_std": np.std(self.k_rr, axis=0),
            "s_z_mean": np.mean(self.s_z_rr, axis=0),
            "s_z_std": np.std(self.s_z_rr, axis=0),
            "omega_raman_used_mean_rad_s": np.mean(self.omega_raman_rr, axis=0),
            "omega_raman_used_std_rad_s": np.std(self.omega_raman_rr, axis=0),
            "Omega_used_mean_rad_s": np.mean(self.Omega_rr, axis=0),
            "Omega_used_std_rad_s": np.std(self.Omega_rr, axis=0),
        }

        return {
            "metadata": dict(self.metadata),
            "params_used": dict(self.params),
            "repeat_results": repeat_results,
            "aggregate": aggregate,
        }


class FeedbackReplay:
    """Replay framework with explicit configuration and overlay tools."""

    def __init__(
        self,
        ad,
        t_raman_pulse=None,
        t_img_pulse=None,
        amp_imaging=None,
        t_raman_pi_pulse=None,
        frequency_resonance=None,
        frequency_z_lightshift=None,
        v_apd_all_up=None,
        v_apd_all_down=None,
        n_photons_per_shot=None,
        std_n_photons_per_shot=None,
        photon_count_scale=None,
        m=None,
        fractional_initial_offset=None,
        guess_span_Omega=None,
        lut_size=4096,
        measurement_index_offset=None,
        reset_each_repeat=True,
    ):
        self.ad = ad

        self.t_raman_pulse = t_raman_pulse
        self.t_img_pulse = t_img_pulse
        self.amp_imaging = amp_imaging
        self.t_raman_pi_pulse = t_raman_pi_pulse
        self.frequency_resonance = frequency_resonance
        self.frequency_z_lightshift = frequency_z_lightshift
        self.v_apd_all_up = v_apd_all_up
        self.v_apd_all_down = v_apd_all_down
        self.n_photons_per_shot = n_photons_per_shot
        self.std_n_photons_per_shot = std_n_photons_per_shot
        self.photon_count_scale = photon_count_scale
        self.m = m
        self.fractional_initial_offset = fractional_initial_offset
        self.guess_span_Omega = guess_span_Omega
        self.lut_size = lut_size

        self.default_measurement_index_offset = measurement_index_offset
        self.default_reset_each_repeat = bool(reset_each_repeat)

        self.result = None
        self.results = None

    def _resolve_replay_time_axes(
        self,
        pulse_times_1d,
        apd_rr,
        measurement_index_offset,
        fb,
    ):
        pulse_times_1d = np.asarray(pulse_times_1d, dtype=np.float64)
        n_step_in = int(pulse_times_1d.size)
        n_apd = int(apd_rr.shape[1])

        if measurement_index_offset is None:
            if n_apd == n_step_in + 1:
                measurement_index_offset = 1
            elif n_apd == n_step_in:
                measurement_index_offset = 0
            else:
                raise ValueError(
                    "Could not infer APD alignment: len(pulse_times)={} but ad.data.apd has {} samples per repeat. "
                    "Set measurement_index_offset explicitly.".format(n_step_in, n_apd)
                )

        measurement_index_offset = int(measurement_index_offset)
        pulse_time_offset = float(fb.dt + fb.dt_z)
        time_tol = max(1.0e-12, 1.0e-6 * max(abs(pulse_time_offset), 1.0))

        has_leading_dummy = (
            measurement_index_offset == 0
            and n_step_in == n_apd
            and n_step_in >= 2
            and abs(pulse_times_1d[0]) <= time_tol
            and abs(pulse_times_1d[1] - pulse_time_offset) <= time_tol
            and abs(float(apd_rr[0, 0]) - float(fb.v_apd_all_up)) <= max(1.0e-9, 1.0e-6 * max(abs(fb.v_range), 1.0))
        )

        if has_leading_dummy:
            measurement_index_offset = 1
            public_times_1d = pulse_times_1d.copy()
            display_times_1d = pulse_times_1d[1:].copy()
        else:
            public_times_1d = pulse_times_1d.copy()
            display_times_1d = pulse_times_1d.copy()

        uses_post_measurement_times = (
            display_times_1d.size > 0
            and measurement_index_offset >= 1
            and abs(display_times_1d[0] - pulse_time_offset) <= time_tol
        )

        if uses_post_measurement_times:
            replay_times_1d = display_times_1d - pulse_time_offset
            time_reference = "post-measurement"
        else:
            replay_times_1d = display_times_1d.copy()
            time_reference = "pulse-start"

        return public_times_1d, display_times_1d, replay_times_1d, measurement_index_offset, time_reference, pulse_time_offset, has_leading_dummy

    def _build_feedback_init_kwargs(self):
        base = _feedback_kwargs_from_atomdata(self.ad)
        kwargs = {
            "t_raman_pulse": self.t_raman_pulse if self.t_raman_pulse is not None else base.get("t_raman_pulse"),
            "t_img_pulse": self.t_img_pulse if self.t_img_pulse is not None else base.get("t_img_pulse"),
            "amp_imaging": self.amp_imaging if self.amp_imaging is not None else base.get("amp_imaging"),
            "t_raman_pi_pulse": self.t_raman_pi_pulse if self.t_raman_pi_pulse is not None else base.get("t_raman_pi_pulse"),
            "frequency_resonance": self.frequency_resonance if self.frequency_resonance is not None else base.get("frequency_resonance"),
            "frequency_z_lightshift": self.frequency_z_lightshift if self.frequency_z_lightshift is not None else base.get("frequency_z_lightshift"),
            "v_apd_all_up": self.v_apd_all_up if self.v_apd_all_up is not None else base.get("v_apd_all_up"),
            "v_apd_all_down": self.v_apd_all_down if self.v_apd_all_down is not None else base.get("v_apd_all_down"),
            "n_photons_per_shot": self.n_photons_per_shot if self.n_photons_per_shot is not None else base.get("n_photons_per_shot"),
            "std_n_photons_per_shot": self.std_n_photons_per_shot if self.std_n_photons_per_shot is not None else base.get("std_n_photons_per_shot"),
            "photon_count_scale": self.photon_count_scale if self.photon_count_scale is not None else base.get("photon_count_scale", 1.0),
            "m": self.m if self.m is not None else base.get("m", 21),
            "fractional_initial_offset": self.fractional_initial_offset if self.fractional_initial_offset is not None else base.get("fractional_initial_offset", -5.0),
            "guess_span_Omega": self.guess_span_Omega if self.guess_span_Omega is not None else base.get("guess_span_Omega", 5.0),
            "lut_size": int(self.lut_size),
        }

        required = [
            "t_raman_pulse",
            "t_img_pulse",
            "t_raman_pi_pulse",
            "frequency_resonance",
        ]
        missing = [k for k in required if kwargs.get(k) is None]
        if missing:
            raise ValueError(
                "Missing required replay init fields: {}. Provide explicitly to FeedbackReplayFramework "
                "or ensure they exist in ad.p.".format(", ".join(missing))
            )

        return kwargs

    def _resolve_apd_rr(self, apd_measurements=None):
        if apd_measurements is None:
            apd = _require_atomdata_attr(_require_atomdata_attr(self.ad, "data", "ad"), "apd", "ad.data")
            return _as_repeat_axis0(apd, "ad.data.apd"), "ad.data.apd"

        return _as_repeat_axis0(apd_measurements, "apd_measurements"), "apd_measurements"

    def _resolve_run_override_rr(self, source_name, n_repeat, n_step, measurement_index_offset):
        if not hasattr(self.ad, "data") or not hasattr(self.ad.data, source_name):
            return None

        arr_rr = _as_repeat_axis0(getattr(self.ad.data, source_name), f"ad.data.{source_name}")
        if arr_rr.shape[0] == 1 and n_repeat > 1:
            arr_rr = np.tile(arr_rr, (n_repeat, 1))
        elif arr_rr.shape[0] != n_repeat:
            raise ValueError(
                f"ad.data.{source_name} has {arr_rr.shape[0]} repeats but replay expects {n_repeat}."
            )

        if arr_rr.shape[1] == n_step:
            return np.asarray(arr_rr, dtype=np.float64)

        start = int(measurement_index_offset)
        end = start + n_step
        if start >= 0 and end <= arr_rr.shape[1]:
            return np.asarray(arr_rr[:, start:end], dtype=np.float64)

        raise ValueError(
            f"Cannot align ad.data.{source_name} with n_step={n_step} and measurement_index_offset={measurement_index_offset}."
        )

    def _resolve_default_experiment_omega_override_rr(self, pulse_times, apd_rr, measurement_index_offset):
        pulse_times_1d = np.asarray(pulse_times)
        if pulse_times_1d.ndim != 1:
            raise ValueError(f"pulse_times must be 1D, got shape {pulse_times_1d.shape}.")
        if pulse_times_1d.size == 0:
            raise ValueError("pulse_times must contain at least one entry.")

        fb = Feedback(**self._build_feedback_init_kwargs())
        _, _, replay_times_1d, measurement_index_offset, _, _, _ = self._resolve_replay_time_axes(
            pulse_times_1d=pulse_times_1d,
            apd_rr=apd_rr,
            measurement_index_offset=measurement_index_offset,
            fb=fb,
        )

        n_repeat = int(apd_rr.shape[0])
        n_step = int(replay_times_1d.size)
        return self._resolve_run_override_rr(
            source_name="omega_raman",
            n_repeat=n_repeat,
            n_step=n_step,
            measurement_index_offset=measurement_index_offset,
        )

    def replay(
        self,
        pulse_times,
        apd_measurements=None,
        update_raman_frequency=True,
        update_rabi_frequency=False,
        include_photon_noise=True,
        omega_raman_override=None,
        Omega_override=None,
        measurement_index_offset=None,
        reset_each_repeat=None,
    ):
        apd_rr, _ = self._resolve_apd_rr(apd_measurements=apd_measurements)
        omega_raman_source = "user override" if omega_raman_override is not None else "computed"

        if omega_raman_override is None:
            omega_raman_override = self._resolve_default_experiment_omega_override_rr(
                pulse_times=pulse_times,
                apd_rr=apd_rr,
                measurement_index_offset=measurement_index_offset,
            )
            if omega_raman_override is not None:
                omega_raman_source = "ad.data.omega_raman"

        res = self.simulate(
            pulse_times=pulse_times,
            apd_measurements=apd_measurements,
            update_raman_frequency=update_raman_frequency,
            update_rabi_frequency=update_rabi_frequency,
            include_photon_noise=include_photon_noise,
            omega_raman_override=omega_raman_override,
            Omega_override=Omega_override,
            measurement_index_offset=measurement_index_offset,
            reset_each_repeat=reset_each_repeat,
        )
        res.params["omega_raman_source"] = omega_raman_source
        return res

    def simulate(
        self,
        pulse_times,
        apd_measurements=None,
        update_raman_frequency=True,
        update_rabi_frequency=False,
        include_photon_noise=True,
        omega_raman_override=None,
        Omega_override=None,
        measurement_index_offset=None,
        reset_each_repeat=None,
    ):
        pulse_times_1d = np.asarray(pulse_times)
        if pulse_times_1d.ndim != 1:
            raise ValueError(f"pulse_times must be 1D, got shape {pulse_times_1d.shape}.")
        if pulse_times_1d.size == 0:
            raise ValueError("pulse_times must contain at least one entry.")

        apd_rr, apd_source = self._resolve_apd_rr(apd_measurements=apd_measurements)
        n_repeat, n_apd = apd_rr.shape

        fb = Feedback(**self._build_feedback_init_kwargs())

        if measurement_index_offset is None:
            measurement_index_offset = self.default_measurement_index_offset
        if reset_each_repeat is None:
            reset_each_repeat = self.default_reset_each_repeat

        public_times_1d, display_times_1d, replay_times_1d, measurement_index_offset, time_reference, pulse_time_offset, has_initial_state = self._resolve_replay_time_axes(
            pulse_times_1d=pulse_times_1d,
            apd_rr=apd_rr,
            measurement_index_offset=measurement_index_offset,
            fb=fb,
        )

        n_step = int(replay_times_1d.size)

        measurement_index_offset = int(measurement_index_offset)
        idx_end = measurement_index_offset + n_step
        if measurement_index_offset < 0 or idx_end > n_apd:
            raise ValueError(
                "Invalid measurement_index_offset={} for apd length {} and len(pulse_times)={}."
                .format(measurement_index_offset, n_apd, n_step)
            )

        times_rr = np.tile(display_times_1d.reshape(1, -1), (n_repeat, 1))
        replay_times_rr = np.tile(replay_times_1d.reshape(1, -1), (n_repeat, 1))
        omega_override_rr = _resolve_override_rr(omega_raman_override, "omega_raman", n_repeat, n_step)
        Omega_override_rr = _resolve_override_rr(Omega_override, "Omega", n_repeat, n_step)

        if omega_override_rr is not None:
            fb.omega_raman = float(omega_override_rr[0, 0])

        omega_init = float(fb.omega_raman)
        Omega_init = float(fb.Omega)

        k_rr = np.zeros((n_repeat, n_step), dtype=np.int64)
        s_z_rr = np.zeros((n_repeat, n_step), dtype=np.float64)
        state_rr = np.zeros((n_repeat, n_step, 3), dtype=np.float64)
        omega_used_rr = np.zeros((n_repeat, n_step), dtype=np.float64)
        omega_computed_rr = np.zeros((n_repeat, n_step), dtype=np.float64)
        Omega_used_rr = np.zeros((n_repeat, n_step), dtype=np.float64)
        Omega_computed_rr = np.zeros((n_repeat, n_step), dtype=np.float64)
        P0_total_rr = np.zeros(n_repeat, dtype=np.float64)

        for r in range(n_repeat):
            if reset_each_repeat or r == 0:
                fb.reset_feedback_state()
                fb.omega_raman = omega_init
                fb.Omega = Omega_init

            apd_trace = apd_rr[r, measurement_index_offset:idx_end]
            zidx = len(fb.omega_guess_list) // 2

            for i in range(n_step):
                t_i = float(replay_times_rr[r, i])
                k_i = int(fb.convert_measurement(float(apd_trace[i])))
                k_rr[r, i] = k_i

                omega_calc, Omega_calc = fb.generate_posterior(
                    k_i,
                    t_i,
                    update_raman_frequency=1 if update_raman_frequency else 0,
                    update_rabi_frequency=1 if update_rabi_frequency else 0,
                    include_photon_noise=1 if include_photon_noise else 0,
                )

                omega_computed_rr[r, i] = float(omega_calc)
                Omega_computed_rr[r, i] = float(Omega_calc)

                if omega_override_rr is not None:
                    fb.omega_raman = float(omega_override_rr[r, i])
                else:
                    fb.omega_raman = float(omega_calc)

                if Omega_override_rr is not None:
                    fb.Omega = float(Omega_override_rr[r, i])
                else:
                    fb.Omega = float(Omega_calc)

                omega_used_rr[r, i] = float(fb.omega_raman)
                Omega_used_rr[r, i] = float(fb.Omega)

                sx = float(fb.state_x[zidx])
                sy = float(fb.state_y[zidx])
                sz = float(fb.state_z[zidx])
                state_rr[r, i, 0] = sx
                state_rr[r, i, 1] = sy
                state_rr[r, i, 2] = sz
                s_z_rr[r, i] = sz

            P0_total_rr[r] = float(fb.P0_total)

        public_len = int(public_times_1d.size)
        if has_initial_state:
            t_rr_public = np.tile(public_times_1d.reshape(1, -1), (n_repeat, 1))
            apd_rr_public = apd_rr[:, :public_len].copy()
            k_rr_public = np.zeros((n_repeat, public_len), dtype=np.int64)
            k_rr_public[:, 0] = int(fb.convert_measurement(fb.v_apd_all_up))
            k_rr_public[:, 1:] = k_rr

            state_rr_public = np.zeros((n_repeat, public_len, 3), dtype=np.float64)
            state_rr_public[:, 0, 2] = 1.0
            state_rr_public[:, 1:, :] = state_rr

            s_z_rr_public = np.ones((n_repeat, public_len), dtype=np.float64)
            s_z_rr_public[:, 1:] = s_z_rr

            omega_rr_public = np.zeros((n_repeat, public_len), dtype=np.float64)
            omega_rr_public[:, 0] = omega_init
            omega_rr_public[:, 1:] = omega_used_rr

            omega_computed_rr_public = np.zeros((n_repeat, public_len), dtype=np.float64)
            omega_computed_rr_public[:, 0] = omega_init
            omega_computed_rr_public[:, 1:] = omega_computed_rr

            Omega_rr_public = np.zeros((n_repeat, public_len), dtype=np.float64)
            Omega_rr_public[:, 0] = Omega_init
            Omega_rr_public[:, 1:] = Omega_used_rr

            Omega_computed_rr_public = np.zeros((n_repeat, public_len), dtype=np.float64)
            Omega_computed_rr_public[:, 0] = Omega_init
            Omega_computed_rr_public[:, 1:] = Omega_computed_rr
        else:
            t_rr_public = times_rr
            apd_rr_public = apd_rr[:, measurement_index_offset:idx_end].copy()
            k_rr_public = k_rr
            state_rr_public = state_rr
            s_z_rr_public = s_z_rr
            omega_rr_public = omega_used_rr
            omega_computed_rr_public = omega_computed_rr
            Omega_rr_public = Omega_used_rr
            Omega_computed_rr_public = Omega_computed_rr

        res = FeedbackReplayResult()
        res.metadata = {
            "run_id": getattr(getattr(self.ad, "run_info", object()), "run_id", None),
            "N_repeat": int(n_repeat),
            "N_step": int(public_len),
            "N_update": int(n_step),
            "measurement_index_offset": int(measurement_index_offset),
            "reset_each_repeat": bool(reset_each_repeat),
            "time_reference": time_reference,
            "has_initial_state": bool(has_initial_state),
        }
        res.params = {
            "update_raman_frequency": bool(update_raman_frequency),
            "update_rabi_frequency": bool(update_rabi_frequency),
            "include_photon_noise": bool(include_photon_noise),
            "omega_raman_override_applied": omega_override_rr is not None,
            "Omega_override_applied": Omega_override_rr is not None,
            "apd_source": apd_source,
            "omega_raman_source": "override" if omega_override_rr is not None else "computed",
            "N_photons_per_shot": float(fb.N_photons_per_shot),
            "v_apd_all_up": float(fb.v_apd_all_up),
            "v_apd_all_down": float(fb.v_apd_all_down),
            "omega_raman_initial_rad_s": float(omega_init),
            "Omega_initial_rad_s": float(Omega_init),
            "pulse_time_offset_s": float(pulse_time_offset),
        }

        res.t = t_rr_public[0].copy()
        res.apd = apd_rr_public[0].copy()
        res.k = k_rr_public[0].copy()
        res.s_z = s_z_rr_public[0].copy()
        res.state = state_rr_public[0].copy()
        res.omega_raman = omega_rr_public[0].copy()
        res.omega_raman_computed = omega_computed_rr_public[0].copy()
        res.Omega = Omega_rr_public[0].copy()
        res.Omega_computed = Omega_computed_rr_public[0].copy()

        res.t_rr = t_rr_public
        res.apd_rr = apd_rr_public
        res.k_rr = k_rr_public
        res.s_z_rr = s_z_rr_public
        res.state_rr = state_rr_public
        res.omega_raman_rr = omega_rr_public
        res.omega_raman_computed_rr = omega_computed_rr_public
        res.Omega_rr = Omega_rr_public
        res.Omega_computed_rr = Omega_computed_rr_public
        res.P0_total_rr = P0_total_rr

        self.result = res
        self.results = res
        return res

    def _resolve_result(self, replay_result):
        result = replay_result if replay_result is not None else self.result
        if result is None:
            raise ValueError("No replay result available. Call replay(...) first or pass replay_result explicitly.")
        return result

    def _select_repeat_trace(self, result, key, repeat_index):
        rr_fields = {
            "state_z_center": result.s_z_rr,
            "s_z": result.s_z_rr,
            "state_x": result.state_rr[:, :, 0],
            "state_y": result.state_rr[:, :, 1],
            "state_z": result.state_rr[:, :, 2],
            "k_photons": result.k_rr,
            "k": result.k_rr,
            "omega_raman_used_rad_s": result.omega_raman_rr,
            "omega_raman": result.omega_raman_rr,
            "omega_raman_computed_rad_s": result.omega_raman_computed_rr,
            "Omega_used_rad_s": result.Omega_rr,
            "Omega": result.Omega_rr,
            "Omega_computed_rad_s": result.Omega_computed_rr,
        }

        n_repeat = int(result.metadata["N_repeat"])
        if repeat_index < 0 or repeat_index >= n_repeat:
            raise ValueError(f"repeat_index {repeat_index} out of range for {n_repeat} repeats.")
        if key not in rr_fields:
            raise ValueError(f"Unknown replay key '{key}'.")

        x = np.asarray(result.t_rr[repeat_index])
        y = np.asarray(rr_fields[key][repeat_index])
        return x, y

    def _extract_run_series(self, source_name, n_step, repeat_index, measurement_index_offset, x_default):
        if not hasattr(self.ad, "data") or not hasattr(self.ad.data, source_name):
            raise ValueError(f"Missing in-run source ad.data.{source_name}.")

        arr = _as_repeat_axis0(getattr(self.ad.data, source_name), f"ad.data.{source_name}")
        if repeat_index < 0 or repeat_index >= arr.shape[0]:
            raise ValueError(f"repeat_index {repeat_index} out of range for ad.data.{source_name} with {arr.shape[0]} repeats.")

        y_full = np.asarray(arr[repeat_index])

        if y_full.shape[0] == n_step:
            y = y_full
        else:
            start = int(measurement_index_offset)
            end = start + n_step
            if start < 0 or end > y_full.shape[0]:
                raise ValueError(
                    f"Cannot align ad.data.{source_name} length {y_full.shape[0]} with n_step={n_step} and measurement_index_offset={measurement_index_offset}."
                )
            y = y_full[start:end]

        return x_default.copy(), y

    def _normalize_apd_overlay_values(self, values, source_name=None):
        y = np.asarray(values, dtype=np.float64)
        if y.ndim != 1 or y.size == 0:
            return y

        p = getattr(self.ad, "p", None)
        if p is None:
            return y

        v_up = getattr(p, "v_apd_all_up", None)
        v_down = getattr(p, "v_apd_all_down", None)
        if v_up is None or v_down is None:
            return y

        v_up = float(v_up)
        v_down = float(v_down)
        span = v_up - v_down
        if abs(span) <= 0.0:
            return y

        finite = y[np.isfinite(y)]
        if finite.size == 0:
            return y

        source_is_apd = source_name == "apd"
        v_min = min(v_up, v_down)
        v_max = max(v_up, v_down)
        tol = max(1.0e-9, 0.15 * abs(span))
        looks_like_apd_voltage = np.all((finite >= (v_min - tol)) & (finite <= (v_max + tol)))

        if not source_is_apd and not looks_like_apd_voltage:
            return y

        return 2.0 * (y - v_down) / span - 1.0

    def _coerce_overlay_items(self, items):
        if items is None:
            return []

        if isinstance(items, (str, dict, np.ndarray)):
            return [items]

        if not isinstance(items, (list, tuple)):
            return [items]

        if len(items) == 0:
            return []

        if any(isinstance(item, (str, dict)) for item in items):
            return list(items)

        arr = np.asarray(items)
        if arr.ndim in (1, 2) and arr.dtype.kind in "biufc":
            return [arr]

        return list(items)

    def _normalize_overlay_items(
        self,
        items,
        n_step,
        repeat_index,
        measurement_index_offset,
        x_default,
        default_label,
        normalize_apd=False,
    ):
        items = self._coerce_overlay_items(items)

        normalized = []
        for idx, item in enumerate(items):
            if isinstance(item, str):
                x, y = self._extract_run_series(
                    source_name=item,
                    n_step=n_step,
                    repeat_index=repeat_index,
                    measurement_index_offset=measurement_index_offset,
                    x_default=x_default,
                )
                if normalize_apd:
                    y = self._normalize_apd_overlay_values(y, source_name=item)
                normalized.append(
                    {
                        "label": f"in-run {item}",
                        "x": x,
                        "y": y,
                        "style": {},
                    }
                )
                continue

            if not isinstance(item, dict):
                item = {
                    "values": item,
                    "label": default_label if len(items) == 1 else f"{default_label} {idx}",
                }

            if "source" in item:
                x, y = self._extract_run_series(
                    source_name=item["source"],
                    n_step=n_step,
                    repeat_index=repeat_index,
                    measurement_index_offset=measurement_index_offset,
                    x_default=x_default,
                )
                if normalize_apd:
                    y = self._normalize_apd_overlay_values(y, source_name=item["source"])
            else:
                if "values" not in item:
                    raise ValueError(
                        f"Overlay dict item #{idx} requires either 'source' or 'values'."
                    )
                y_in = np.asarray(item["values"])
                if y_in.ndim == 2:
                    if repeat_index < 0 or repeat_index >= y_in.shape[0]:
                        raise ValueError(
                            f"Overlay values item #{idx} has {y_in.shape[0]} repeats, repeat_index={repeat_index} is out of range."
                        )
                    y_in = y_in[repeat_index]
                if y_in.ndim != 1:
                    raise ValueError(
                        f"Overlay values item #{idx} must be 1D or 2D (repeat axis 0), got shape {y_in.shape}."
                    )
                if y_in.shape[0] == n_step + int(measurement_index_offset):
                    start = int(measurement_index_offset)
                    y_in = y_in[start:start + n_step]
                if y_in.shape[0] != n_step:
                    raise ValueError(
                        f"Overlay values item #{idx} length must be n_step={n_step}, got {y_in.shape[0]}."
                    )
                y = self._normalize_apd_overlay_values(y_in) if normalize_apd else y_in

                if "time_s" in item and item["time_s"] is not None:
                    x = np.asarray(item["time_s"])
                    if x.ndim == 2:
                        if repeat_index < 0 or repeat_index >= x.shape[0]:
                            raise ValueError(
                                f"Overlay time_s item #{idx} has {x.shape[0]} repeats, repeat_index={repeat_index} is out of range."
                            )
                        x = x[repeat_index]
                    if x.ndim != 1 or x.shape[0] != n_step:
                        raise ValueError(
                            f"Overlay time_s item #{idx} must be length n_step={n_step}, got shape {x.shape}."
                        )
                else:
                    x = x_default.copy()

            normalized.append(
                {
                    "label": item.get("label", f"overlay {idx}"),
                    "x": x,
                    "y": y,
                    "style": dict(item.get("style", {})),
                }
            )

        return normalized

    def plot_replay(
        self,
        replay_result=None,
        repeat_index=0,
        in_run_data_list=None,
        in_run_simulation_list=None,
        measurement_index_offset=None,
        show_bloch=False,
        only_z=False,
        ax=None,
        bloch_ax=None,
        figsize=None,
        title=None,
        show_legend=True,
        show=True,
        sphere_alpha=0.10,
        replay_alpha=0.75,
        replay_line_color="0.55",
        replay_marker_color="0.45",
        replay_marker_size=12,
    ):
        """
        General replay visualization with optional Bloch sphere and in-run overlays.

        Parameters
        ----------
        show_bloch : bool
            If True, include a Bloch-sphere panel beside the time-series panel.
        only_z : bool
            If True, only plot the replay `s_z` trace on the time-series panel.
        in_run_data_list, in_run_simulation_list
            Optional in-run overlays. Each item may be a bare 1D/2D array, an
            `ad.data.<key>` string, or a dict with `source` or `values`.

        Simplest uses:
        - plot_replay(result, in_run_data_list=ad.data.s_z[0], only_z=True)
        - plot_replay(result, in_run_data_list=ad.data.s_z[0], show_bloch=True)
        """
        import matplotlib.pyplot as plt
        from waxa.plotting.bloch import draw_bloch_sphere

        result = self._resolve_result(replay_result)
        repeat_index = int(repeat_index)

        sx = np.asarray(result.state_rr[repeat_index, :, 0])
        sy = np.asarray(result.state_rr[repeat_index, :, 1])
        sz = np.asarray(result.state_rr[repeat_index, :, 2])
        t = np.asarray(result.t_rr[repeat_index])

        if measurement_index_offset is None:
            measurement_index_offset = int(result.metadata.get("measurement_index_offset", 0))

        n_step = int(t.shape[0])
        data_items = self._normalize_overlay_items(
            items=in_run_data_list,
            n_step=n_step,
            repeat_index=repeat_index,
            measurement_index_offset=int(measurement_index_offset),
            x_default=t,
            default_label="in-run data",
            normalize_apd=True,
        )
        sim_items = self._normalize_overlay_items(
            items=in_run_simulation_list,
            n_step=n_step,
            repeat_index=repeat_index,
            measurement_index_offset=int(measurement_index_offset),
            x_default=t,
            default_label="in-run simulation",
            normalize_apd=False,
        )

        if figsize is None:
            figsize = (11.0, 4.8) if show_bloch else (7.4, 4.2)

        created_axes = False
        if show_bloch:
            if ax is None and bloch_ax is None:
                fig = plt.figure(figsize=figsize)
                bloch_ax = fig.add_subplot(1, 2, 1, projection="3d")
                ax = fig.add_subplot(1, 2, 2)
                created_axes = True
            elif ax is None or bloch_ax is None:
                raise ValueError("show_bloch=True requires both ax and bloch_ax when supplying existing axes.")
            else:
                fig = ax.figure
        else:
            if ax is None:
                fig, ax = plt.subplots(figsize=figsize)
                created_axes = True
            else:
                fig = ax.figure

        component_specs = [("s_x", sx, "--"), ("s_y", sy, "-.")]
        if only_z:
            component_specs = [("s_z", sz, "-")]
        else:
            component_specs.append(("s_z", sz, "-"))

        for label, values, linestyle in component_specs:
            ax.plot(
                t,
                values,
                color=replay_line_color,
                linestyle=linestyle,
                linewidth=1.2,
                alpha=replay_alpha,
                label=f"replay {label}",
                zorder=2,
            )
            ax.scatter(
                t,
                values,
                color=replay_marker_color,
                s=replay_marker_size,
                alpha=min(1.0, replay_alpha + 0.1),
                zorder=3,
            )

        for item in data_items:
            style = {"linestyle": "", "marker": "o", "markersize": 3, "alpha": 0.9}
            style.update(item["style"])
            ax.plot(item["x"], item["y"], label=item["label"], **style)

        for item in sim_items:
            style = {"linestyle": "--", "linewidth": 1.2, "alpha": 0.8}
            style.update(item["style"])
            ax.plot(item["x"], item["y"], label=item["label"], **style)

        ax.set_xlabel("time (s)")
        ax.set_ylabel("s_z" if only_z else "Bloch component")
        ax.set_ylim(-1.05, 1.05)
        ax.grid(alpha=0.25)

        if show_bloch:
            draw_bloch_sphere(bloch_ax, sphere_alpha=sphere_alpha)
            bloch_ax.plot(sx, sy, sz, color=replay_line_color, lw=1.0, alpha=replay_alpha)
            bloch_ax.scatter(sx, sy, sz, color=replay_marker_color, s=max(8, replay_marker_size), alpha=min(1.0, replay_alpha + 0.1), depthshade=False)
            bloch_ax.scatter([sx[0]], [sy[0]], [sz[0]], color="tab:green", marker="o", s=28, depthshade=False, label="start")
            bloch_ax.scatter([sx[-1]], [sy[-1]], [sz[-1]], color="tab:red", marker="x", s=32, depthshade=False, label="end")
            if show_legend:
                bloch_ax.legend(loc="upper left", fontsize="small")

        run_id = result.metadata.get("run_id")
        if title is None:
            title = f"run {run_id} | replay" if run_id is not None else "feedback replay"
        if show_bloch:
            fig.suptitle(title)
            if created_axes:
                fig.tight_layout()
        else:
            ax.set_title(title)

        if show_legend:
            ax.legend(loc="best", fontsize="small")

        if show and created_axes:
            plt.show()

        return fig, (bloch_ax, ax) if show_bloch else ax

    def plot_replay_overlay(
        self,
        replay_result=None,
        replay_key="state_z_center",
        repeat_index=0,
        in_run_data_list=None,
        in_run_simulation_list=None,
        measurement_index_offset=None,
        ax=None,
        figsize=(7, 4),
        title=None,
        show_legend=True,
    ):
        """Backward-compatible wrapper for time-series replay plotting."""
        only_z = replay_key in ("state_z_center", "s_z", "state_z")
        return self.plot_replay(
            replay_result=replay_result,
            repeat_index=repeat_index,
            in_run_data_list=in_run_data_list,
            in_run_simulation_list=in_run_simulation_list,
            measurement_index_offset=measurement_index_offset,
            show_bloch=False,
            only_z=only_z,
            ax=ax,
            figsize=figsize,
            title=title,
            show_legend=show_legend,
            show=False,
        )

    def plot_replay_bloch_vs_time(
        self,
        replay_result=None,
        repeat_index=0,
        figsize=(11.0, 4.8),
        title=None,
        sphere_alpha=0.10,
        show=True,
    ):
        """Backward-compatible wrapper for replay plots with Bloch visualization."""
        return self.plot_replay(
            replay_result=replay_result,
            repeat_index=repeat_index,
            show_bloch=True,
            only_z=False,
            figsize=figsize,
            title=title,
            sphere_alpha=sphere_alpha,
            show=show,
        )