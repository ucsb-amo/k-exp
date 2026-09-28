from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras, aprint
from kexp.base import Feedback
import numpy as np
from numpy import int64

from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt
from artiq.coredevice.sampler import adc_mu_to_volt


class feedback_reinit(EnvExperiment, FeedbackExpt):
    """Adaptive feedback with one pole reinitialisation and a finer remesh per shot
    (user, 2026-09-27 ~22:25).

    Once the posterior std falls below feedback_reinit_std_threshold_Omega (no earlier
    than after pulse feedback_reinit_min_pulse; forced after pulse
    feedback_reinit_force_pulse if it never does, 0 = never forced), the NEXT pulse is a
    "pole pulse": its length is chosen to rotate the spin to the nearest pole
    (S_z = +-1) with the model's own rotation (generate_posterior, drive on resonance
    with the hypothesis):
      method 0: the MAP hypothesis' Bloch vector, theta* = (-atan2(a, b)) mod pi;
      method 1: maximise the posterior-weighted E[S_z^2] over all hypotheses,
                theta* = 0.5 atan2(-2 Sab, Sbb - Saa) mod pi;
    with a = u_x s_y - u_y s_x, b = s_z, (u_x, u_y) the drive axis in each hypothesis
    frame. Its readout measures the remaining contrast. The pole pulse updates the
    posterior like any other pulse. Then the grid is remeshed (half-width
    feedback_reinit_span_Omega, centred on the MAP, posterior linearly interpolated;
    Feedback.remesh_to_centered) and every hypothesis restarts from (0, 0, s0):
    s0 = the measured S_z (feedback_reinit_state_source 0; linear readout map,
    midpoint 0.5) or the model's predicted value (1). The remaining pulses run as
    usual on the new grid. t_reinit_extra_mu is added to the two gaps around the pole
    pulse for the extra computation; the model uses the real pulse times, so it
    accounts for it.

    Recorded per shot: data.reinit_pulse (0-based index of the pole pulse, -1 = none),
    reinit_trigger_std (posterior std / Omega that triggered it), reinit_theta,
    reinit_sz_pred, reinit_sz_meas, reinit_center (rad/s). Per pulse: probabilities and
    the grid (omega_raman_mesh), row k = after pulse k (row 0 = prior).
    """

    def prepare(self):

        FeedbackExpt.__init__(self,
                              save_data=True,
                              save_on_underflow=True)

        self.p.update_raman_frequency_bool = 1
        self.p.include_photon_noise = 1

        ### parameters

        self.p.feedback_fractional_initial_offset = 2.
        self.xvar('feedback_fractional_initial_offset', np.linspace(-2.5, 2.5, 11))

        self.p.N_repeats = 5
        self.p.N_pulses = 17

        self.p.feedback_guess_span_Omega = 2.5 # 21 points x 0.25 Omega, as FB_scan

        ### reinitialisation
        self.p.feedback_reinit_std_threshold_Omega = 0.5
        self.p.feedback_reinit_min_pulse = 2
        self.p.feedback_reinit_force_pulse = 6
        self.p.feedback_reinit_span_Omega = 0.625
        self.p.feedback_reinit_method = 1
        self.p.feedback_reinit_state_source = 0
        self.p.t_reinit_extra_mu = int64(30000)
        # options added 2026-09-28 (defaults = the 2026-09-27 behaviour):
        # trigger_mode 0: posterior std < threshold; 1: alias margin, ln(P_MAP / max P outside
        #   MAP +- margin_excl grid points) >= margin_nats
        self.p.feedback_reinit_trigger_mode = 0
        self.p.feedback_reinit_margin_nats = 2.0
        self.p.feedback_reinit_margin_excl = 1
        # pole_enabled 0: no pole pulse, no readout of the contrast: remesh right after the
        #   triggering pulse with the Bloch states interpolated (not reset)
        self.p.feedback_reinit_pole_enabled = 1
        # temper_beta < 1: P0 -> P0**beta (renormalised) before the remesh (1 = off)
        self.p.feedback_reinit_temper_beta = 1.0
        # center_mode 0: centre the new grid on the MAP; 1: on the P0-weighted mean of MAP +- 1
        self.p.feedback_reinit_center_mode = 0
        # gap test: extra delay added to every other gap (after odd pulses); 0 = off. The model
        # uses the real pulse times, so it accounts for it.
        self.p.t_gap_alt_extra_mu = int64(0)
        # timing probe (2026-09-28): per pulse, at 6 points, record the RTIO counter (wall clock) and the
        # timeline cursor now_mu, both relative to the train start (mu): data.probe[i, 2*q] = counter,
        # data.probe[i, 2*q+1] = now. q: 0 before the FTW write (after at_mu(t_step - pretrigger)),
        # 1 after set_frequency_fast, 2 after io_update_and_phase_update, 3 after measurement (sample
        # returned), 4 after generate_posterior, 5 after the bookkeeping at the end of the iteration.
        self.p.t_probe_enabled = 0
        # split posterior (2026-09-28): 1 = do the k-independent half of generate_posterior (rotate every
        # hypothesis) BEFORE the blocking ADC read, while the timeline plays the pulse and readout, and
        # only the likelihood/normalisation/MAP after it. Same operations in the same order.
        self.p.t_split_posterior = 0
        # fast path (2026-09-28; needs t_split_posterior = 1, ignores the reinit options): submit only the
        # IO-update events before the pulse and do the DDS phase-tracker arithmetic (same integer ops as
        # RamanBeamPair.io_update_and_phase_update) after the readout events, before the ADC read; and
        # record pulse i's bookkeeping (data.t, data.s_z, probabilities/grid rows) in iteration i+1 after
        # its DDS events. The recorded values are the same: nothing they read changes in between.
        self.p.t_fast_path = 0

        self.data.reinit_pulse = self.data.add_data_container(1)
        self.data.reinit_trigger_std = self.data.add_data_container(1)
        self.data.reinit_theta = self.data.add_data_container(1)
        self.data.reinit_sz_pred = self.data.add_data_container(1)
        self.data.reinit_sz_meas = self.data.add_data_container(1)
        self.data.reinit_center = self.data.add_data_container(1)
        self.data.reinit_trigger_margin = self.data.add_data_container(1)
        self.data.probe = self.data.add_data_container((self.p.N_pulses, 14))
        # fast path + probe: wall time (mu) of [pulse/readout/ADC event submission, deferred phase math,
        # propagate_hypotheses, one unused AO split + 2 FTW roundings] per pulse
        self.data.probe_cpu = self.data.add_data_container((self.p.N_pulses, 4))

        self.finish_prepare()
        self.p1_scratch = np.zeros(self.p.feedback_grid_size, dtype=np.float64)

    @portable(flags={"fast-math"})
    def propagate_hypotheses(self, t, phase_raman_pulse_start=0.):
        """k-independent half of Feedback.generate_posterior (same operations, same order): rotate
        every hypothesis' Bloch vector for the pulse starting at t, apply the readout light shift and
        the back-action, and store p1_j = expected_photon_fraction(hz_j) in self.p1_scratch."""
        omega_guess_list = self.omega_guess_list
        state_x = self.state_x
        state_y = self.state_y
        state_z = self.state_z
        m = self.m
        omega_raman = self.omega_raman
        Omega = self.Omega
        Omega_sq = Omega * Omega
        dt_eff = self.t_raman_pulse_current
        dt_ideal = self.t_raman_pulse_ideal_current
        dt_z = self.p.t_img_pulse
        if m > 1:
            domega = omega_guess_list[1] - omega_guess_list[0]
        else:
            domega = 0.0
        omega0 = omega_guess_list[0]
        phi = phase_raman_pulse_start - omega0*t
        delta_omega0 = omega0 - omega_raman
        (sin_wt, cos_wt) = self.sincos_lut_interp(phi)
        (sin_wt_step, cos_wt_step) = self.sincos_lut_interp(-domega * t)
        alpha_z_lightshift = self.omega_z_lightshift * dt_z
        alpha_z = dt_eff * delta_omega0 - alpha_z_lightshift
        (sin_z, cos_z) = self.sincos_lut_interp(alpha_z)
        alpha_z_step = dt_eff * domega
        (sin_z_step, cos_z_step) = self.sincos_lut_interp(alpha_z_step)
        j = 0
        while j < m:
            omega = omega_guess_list[j]
            delta_omega = omega_raman - omega
            norm_H = np.sqrt(Omega_sq + delta_omega * delta_omega)
            if norm_H > 0.0:
                inv_norm_H = 1.0 / norm_H
                Omega_over_H = Omega * inv_norm_H
                u_z = delta_omega * inv_norm_H
                (sin_H, cos_H) = self.sincos_lut_interp(-dt_ideal * norm_H)
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
            self.p1_scratch[j] = self.expected_photon_fraction(hz)
            next_sin_wt = sin_wt * cos_wt_step + cos_wt * sin_wt_step
            next_cos_wt = cos_wt * cos_wt_step - sin_wt * sin_wt_step
            sin_wt = next_sin_wt
            cos_wt = next_cos_wt
            next_sin_z = sin_z * cos_z_step + cos_z * sin_z_step
            next_cos_z = cos_z * cos_z_step - sin_z * sin_z_step
            sin_z = next_sin_z
            cos_z = next_cos_z
            j += 1

    @portable(flags={"fast-math"})
    def update_with_measurement(self, k,
                                update_raman_frequency=1,
                                update_rabi_frequency=0,
                                include_photon_noise=1):
        """k-dependent half of Feedback.generate_posterior (same operations, same order), using the
        p1_j stored by propagate_hypotheses. Returns (omega_raman_out, mean, std) like generate_posterior."""
        P0_total = 0.0
        moment_2 = 0.0
        mn = 0.0
        omega_guess_list = self.omega_guess_list
        omega_sq_list = self.omega_sq_list
        P0 = self.P0
        m = self.m
        n_photons = int(self.N_photons_per_shot)
        if include_photon_noise:
            sigma = self.std_n_photons_per_shot
            sigma_sq = sigma * sigma
        else:
            sigma = 0.
            sigma_sq = 0.
        k_int = int(k)
        if k_int < 0:
            k_int = 0
        if k_int > n_photons:
            k_int = n_photons
        nk_int = n_photons - k_int
        j = 0
        while j < m:
            omega = omega_guess_list[j]
            p1 = self.p1_scratch[j]
            q = 1.0 - p1
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
            j += 1
        if P0_total <= 0.0:
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
        max_idx = 0
        max_prob = P0[0]
        i = 1
        while i < len(P0):
            if P0[i] > max_prob:
                max_prob = P0[i]
                max_idx = i
            i += 1
        omega_max = omega_guess_list[max_idx]
        self.max_idx = max_idx
        uniform_prob = 1.0 / m
        if max_prob < 1.15 * uniform_prob:
            omega_raman_out = mn
            self._flat_prob_counter += 1
        else:
            omega_raman_out = omega_max
        self.omega_max = omega_max
        self._posterior_std = std
        if not update_raman_frequency:
            omega_raman_out = self.omega_raman
        if not update_rabi_frequency:
            std = self.Omega
        return omega_raman_out, mn, std

    @kernel
    def deferred_phase_update(self, dT, dt0, dt1) -> TFloat:
        """The arithmetic half of RamanBeamPair.io_update_and_phase_update (same integer operations),
        run after io_update() was submitted; dT = gap since the previous pulse (mu)."""
        r = self.raman
        T = self.p.t_io_update_pretrigger_mu
        dt = self.p.t_ffu_pipeline_latency_fudge_mu
        spmu = r._sysclk_per_mu
        r._phi0_mu += r.dds0._last_ftw * (dT - T + dt0 + dt) * spmu >> 16
        r._phi0_mu += r.dds0._ftw * (T - dt0 - dt) * spmu >> 16
        r._phi1_mu += r.dds1._last_ftw * (dT - T + dt1 + dt) * spmu >> 16
        r._phi1_mu += r.dds1._ftw * (T - dt1 - dt) * spmu >> 16
        a0 = r.dds0.aom_order
        a1 = r.dds1.aom_order
        return r.pow_to_phase(2*np.int32(a0*r._phi0_mu - a1*r._phi1_mu))

    @kernel
    def adc_submit(self):
        # Sampler_Last_CH.sample_single_mu up to the blocking read: CNV pulse, conversion wait, SPI transfer
        sd = self.integrator.sampler_ch.sampler_device
        sd.cnv.pulse(30.e-9)
        delay(450.e-9)
        sd.bus_adc.write(0)

    @kernel
    def adc_read(self, i):
        # the rest of Sampler_Last_CH.sample_single for the integrator's channel, then as measurement()
        sch = self.integrator.sampler_ch
        sd = sch.sampler_device
        mask = 1 << 15
        val = sd.bus_adc.read()
        d1 = val >> 16
        val &= 0xffff
        d0 = -(val & mask) + (val & ~mask)
        ch = sch.ch
        channel = (ch - 6) + 8 - len(sch.samples)
        gain = (sd.gains >> (channel)*2) & 0b11
        if ch == 7:
            v = adc_mu_to_volt(d1, gain, sd.corrected_fs)
        else:
            v = adc_mu_to_volt(d0, gain, sd.corrected_fs)
        sch.samples[ch] = v
        self.data.apd.shot_data[i] = v
        return self.convert_measurement(v)

    @kernel
    def feedback_loop_fast(self, t_start_mu,
                           update_raman_frequency=0,
                           update_rabi_frequency=0,
                           include_photon_noise=1):
        """t_fast_path = 1: the feedback loop with the ADC events submitted before the k-independent
        posterior half, the DDS phase arithmetic deferred to before the read, and pulse i's bookkeeping
        done in iteration i+1 after its DDS events. No reinit, no remesh; the grid is recorded as-is."""
        self.omega_z_lightshift = 2 * np.pi * self.p.frequency_lightshift
        k = 0
        f = self.omega_raman / (2*np.pi)
        t_start_mu = t_start_mu & ~7
        t_step = t_start_mu
        at_mu((t_start_mu - 10000) & ~7)
        self.raman.set_frequency_fast(f)
        self.raman.stage_ffua()
        phase_tracker = 0.
        dT = self.p.t_between_pulses_mu
        t_turn_on_delay = self.p.t_raman_pulse_offset
        T = self.p.t_io_update_pretrigger_mu
        T_PIPE = self.p.t_ffu_dds_pipeline_latency
        dt0 = int64(0)
        dt1 = int64(0)
        t_prev = 0.
        t_pulse_prev = 0.
        self.data.reinit_pulse.put_data(-1.)
        at_mu(t_start_mu)
        for i in range(self.p.N_pulses):
            self.per_feedback_loop_top(idx=i)
            f = self.omega_raman / (2*np.pi)
            t_pulse = self.p.t_raman_pulse_list[i]
            self.data.omega_raman.put_data(self.omega_raman, i)
            at_mu(t_step - self.p.t_raman_set_pretrigger_mu)
            self.probe_point(i, 0, t_start_mu)
            self.raman.set_frequency_fast(f, do_io_update=False)
            self.probe_point(i, 1, t_start_mu)
            t = (t_step - t_start_mu)*1.e-9
            at_mu(t_step - T - T_PIPE)
            dt0, dt1 = self.raman.io_update()
            at_mu(t_step)
            self.probe_point(i, 2, t_start_mu)
            if i > 0:
                self.bookkeep(i - 1, t_prev, t_pulse_prev)
            self.t_raman_pulse_current = t_pulse
            self.t_raman_pulse_ideal_current = t_pulse - t_turn_on_delay
            at_mu(t_step)
            c_a = self.core.get_rtio_counter_mu()
            self.raman.pulse(t_pulse)
            self.measurement_events()
            self.adc_submit()
            c_b = self.core.get_rtio_counter_mu()
            phase_tracker = self.deferred_phase_update(dT, dt0, dt1)
            c_c = self.core.get_rtio_counter_mu()
            self.propagate_hypotheses(t, phase_tracker)
            c_d = self.core.get_rtio_counter_mu()
            if self.p.t_probe_enabled == 1:
                # timing only: one AO split + FTW rounding (result unused), in the idle wait before the read
                self.raman.state_splitting_to_ao_frequency(f)
                ftw_a = np.int32(round(self.raman.dds0.dds_device.ftw_per_hz * self.raman._dummy[0]))
                ftw_b = np.int32(round(self.raman.dds1.dds_device.ftw_per_hz * self.raman._dummy[1]))
                c_e = self.core.get_rtio_counter_mu()
                self.data.probe_cpu.put_data(float(c_b - c_a), i, 0)
                self.data.probe_cpu.put_data(float(c_c - c_b), i, 1)
                self.data.probe_cpu.put_data(float(c_d - c_c), i, 2)
                self.data.probe_cpu.put_data(float(c_e - c_d), i, 3)
                self.probe_point(i, 6, t_start_mu)
            k = self.adc_read(i)
            self.probe_point(i, 3, t_start_mu)
            self.omega_raman, omega_posterior_mean, self.Omega = self.update_with_measurement(k,
                                                    update_raman_frequency=update_raman_frequency,
                                                    update_rabi_frequency=update_rabi_frequency,
                                                    include_photon_noise=include_photon_noise)
            self.probe_point(i, 4, t_start_mu)
            dT = self.compute_t_between_pulses_mu(
                t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
                t_raman_pulse=t_pulse,
                t_img_pulse=self.p.t_img_pulse,
                t_raman_pretrigger=self.p.t_raman_set_pretrigger_mu,
                t_fifo_mu=self.p.t_fifo_mu
            )
            t_prev = t
            t_pulse_prev = t_pulse
            t_step += dT
            self.probe_point(i, 5, t_start_mu)
        self.bookkeep(self.p.N_pulses - 1, t_prev, t_pulse_prev)
        self.per_scan_kernel_end()

    @kernel
    def bookkeep(self, i, t, t_pulse):
        # pulse i's records (the fast path calls this one iteration later)
        self.data.t.put_data(t + t_pulse + self.p.t_img_pulse, i)
        self.data.s_z.put_data(self.state_z[self.zidx], i)
        self.per_feedback_loop_end(idx=i)

    @kernel
    def measurement_events(self):
        # FeedbackExpt.measurement up to the ADC read: integrator gate, readout pulse, settle,
        # stage the next fast frequency update, schedule the integrator clear; cursor left at t0.
        T_CONV_MU = 80
        self.integrator.begin_integrate(reset=False)
        self.imaging.pulse(self.p.t_img_pulse)
        self.integrator.stop_and_settle()
        t0 = now_mu()
        self.raman.stage_ffua()
        at_mu(t0 + T_CONV_MU)
        self.integrator.clear(t=0)
        at_mu(t0)

    @kernel
    def measurement_read(self, i):
        self.data.apd.shot_data[i] = self.integrator.sample()
        v = self.convert_measurement(self.data.apd.shot_data[i])
        return v

    @kernel
    def probe_point(self, i, q, t_start_mu):
        if self.p.t_probe_enabled == 1:
            c = self.core.get_rtio_counter_mu()
            self.data.probe.put_data(float(c - t_start_mu), i, 2 * q)
            self.data.probe.put_data(float(now_mu() - t_start_mu), i, 2 * q + 1)

    @portable(flags={"fast-math"})
    def alias_margin(self):
        """ln(P_MAP / max P over grid points more than margin_excl steps from the MAP)."""
        j = self.max_idx
        excl = self.p.feedback_reinit_margin_excl
        pout = 0.0
        k = 0
        while k < self.m:
            d = k - j
            if d < 0:
                d = -d
            if d > excl and self.P0[k] > pout:
                pout = self.P0[k]
            k += 1
        if pout <= 0.0:
            return 100.0
        return np.log(self.P0[j] / pout)

    @portable(flags={"fast-math"})
    def temper_posterior(self):
        beta = self.p.feedback_reinit_temper_beta
        if beta < 1.0:
            tot = 0.0
            k = 0
            while k < self.m:
                if self.P0[k] > 0.0:
                    self.P0[k] = np.exp(beta * np.log(self.P0[k]))
                tot += self.P0[k]
                k += 1
            k = 0
            while k < self.m:
                self.P0[k] = self.P0[k] / tot
                k += 1

    @portable(flags={"fast-math"})
    def reinit_center(self):
        j = self.max_idx
        if self.p.feedback_reinit_center_mode == 0:
            return self.omega_guess_list[j]
        num = 0.0
        den = 0.0
        k = j - 1
        while k <= j + 1:
            if k >= 0 and k < self.m:
                num += self.P0[k] * self.omega_guess_list[k]
                den += self.P0[k]
            k += 1
        return num / den

    @portable(flags={"fast-math"})
    def select_map(self):
        best = 0
        pbest = self.P0[0]
        j = 1
        while j < self.m:
            if self.P0[j] > pbest:
                pbest = self.P0[j]
                best = j
            j += 1
        self.max_idx = best
        self.omega_raman = self.omega_guess_list[best]

    @portable(flags={"fast-math"})
    def remesh_only(self):
        """pole_enabled 0: remesh now, posterior and Bloch states interpolated. Returns the centre."""
        center = self.reinit_center()
        self.temper_posterior()
        self.remesh_to_centered(center, self.p.feedback_reinit_span_Omega, 1, 1, 1)
        self.select_map()
        return center

    @portable(flags={"fast-math"})
    def pole_ab(self, j, phase_start, t):
        """(a, b) of hypothesis j for a pulse starting at t with DDS phase phase_start,
        in generate_posterior's convention: axis angle phase_start - omega_j t."""
        (s, c) = self.sincos_lut_interp(phase_start - self.omega_guess_list[j] * t)
        a = c * self.state_y[j] - s * self.state_x[j]
        b = self.state_z[j]
        return a, b

    @portable(flags={"fast-math"})
    def pole_angle(self, phase_start, t):
        """Rotation angle theta* in [0, pi) of the pole pulse (see class docstring)."""
        if self.p.feedback_reinit_method == 0:
            (a, b) = self.pole_ab(self.max_idx, phase_start, t)
            theta = -np.arctan2(a, b)
        else:
            saa = 0.0
            sbb = 0.0
            sab = 0.0
            j = 0
            while j < self.m:
                (a, b) = self.pole_ab(j, phase_start, t)
                pj = self.P0[j]
                saa += pj * a * a
                sbb += pj * b * b
                sab += pj * a * b
                j += 1
            theta = 0.5 * np.arctan2(-2.0 * sab, sbb - saa)
        while theta < 0.0:
            theta += np.pi
        while theta >= np.pi:
            theta -= np.pi
        return theta

    @portable(flags={"fast-math"})
    def pole_expected_sz(self, phase_start, t, theta):
        """Model S_z after the pole pulse: of the MAP hypothesis (method 0) or the
        posterior mean (method 1)."""
        c = np.cos(theta)
        s = np.sin(theta)
        if self.p.feedback_reinit_method == 0:
            (a, b) = self.pole_ab(self.max_idx, phase_start, t)
            return b * c - a * s
        sz = 0.0
        j = 0
        while j < self.m:
            (a, b) = self.pole_ab(j, phase_start, t)
            sz += self.P0[j] * (b * c - a * s)
            j += 1
        return sz

    @portable(flags={"fast-math"})
    def reinitialize(self, s_meas, sz_pred):
        """Remesh (centre per center_mode, posterior tempered per temper_beta) and restart every
        hypothesis at (0, 0, s0). Returns the centre."""
        center = self.reinit_center()
        self.temper_posterior()
        self.remesh_to_centered(center, self.p.feedback_reinit_span_Omega, 1, 0, 1)
        s0 = s_meas
        if self.p.feedback_reinit_state_source == 1:
            s0 = sz_pred
        if s0 > 1.0:
            s0 = 1.0
        if s0 < -1.0:
            s0 = -1.0
        best = 0
        pbest = self.P0[0]
        j = 0
        while j < self.m:
            self.state_x[j] = 0.0
            self.state_y[j] = 0.0
            self.state_z[j] = s0
            if self.P0[j] > pbest:
                pbest = self.P0[j]
                best = j
            j += 1
        self.max_idx = best
        self.omega_raman = self.omega_guess_list[best]
        return center

    @kernel
    def feedback_loop(self, t_start_mu,
                      update_raman_frequency=0,
                      update_rabi_frequency=0,
                      include_photon_noise=1):
        # FeedbackExpt.feedback_loop plus the pole reinitialisation; see the class docstring.
        if self.p.t_fast_path == 1:
            self.feedback_loop_fast(t_start_mu, update_raman_frequency=update_raman_frequency,
                                    update_rabi_frequency=update_rabi_frequency,
                                    include_photon_noise=include_photon_noise)
            return
        self.omega_z_lightshift = 2 * np.pi * self.p.frequency_lightshift

        k = 0
        f = self.omega_raman / (2*np.pi)

        t_start_mu = t_start_mu & ~7
        t_step = t_start_mu

        at_mu((t_start_mu - 10000) & ~7)

        self.raman.set_frequency_fast(f)
        self.raman.stage_ffua()
        phase_tracker = 0.

        dT = self.p.t_between_pulses_mu
        t_turn_on_delay = self.p.t_raman_pulse_offset

        reinit_next = 0
        reinit_done = 0
        sz_pred = 0.
        self.data.reinit_pulse.put_data(-1.)
        self.data.reinit_trigger_std.put_data(-1.)
        self.data.reinit_theta.put_data(0.)
        self.data.reinit_sz_pred.put_data(0.)
        self.data.reinit_sz_meas.put_data(0.)
        self.data.reinit_center.put_data(0.)
        self.data.reinit_trigger_margin.put_data(-1.)

        at_mu(t_start_mu)

        for i in range(self.p.N_pulses):

            self.per_feedback_loop_top(idx=i)
            f = self.omega_raman / (2*np.pi)

            t_pulse = self.p.t_raman_pulse_list[i]

            self.data.omega_raman.put_data(self.omega_raman, i)

            at_mu(t_step - self.p.t_raman_set_pretrigger_mu)
            self.probe_point(i, 0, t_start_mu)
            self.raman.set_frequency_fast(f, do_io_update=False)
            self.probe_point(i, 1, t_start_mu)

            t = (t_step - t_start_mu)*1.e-9

            phase_tracker = self.raman.io_update_and_phase_update(t_pulse_mu = t_step,
                                                                t_last_pulse_mu = t_step - dT)
            self.probe_point(i, 2, t_start_mu)

            if reinit_next == 1:
                theta = self.pole_angle(phase_tracker, t)
                sz_pred = self.pole_expected_sz(phase_tracker, t, theta)
                t_pulse = theta / self.Omega + t_turn_on_delay
                # the pulse actually played (scan_kernel stored the drawn list)
                self.data.t_raman_pulse.put_data(t_pulse, i)
                self.data.reinit_pulse.put_data(float(i))
                self.data.reinit_theta.put_data(theta)
                self.data.reinit_sz_pred.put_data(sz_pred)

            self.t_raman_pulse_current = t_pulse
            self.t_raman_pulse_ideal_current = t_pulse - t_turn_on_delay

            at_mu(t_step)

            self.raman.pulse(t_pulse)
            if self.p.t_split_posterior == 1:
                self.measurement_events()
                self.propagate_hypotheses(t, phase_tracker)
                k = self.measurement_read(i)
                self.probe_point(i, 3, t_start_mu)
                self.omega_raman, omega_posterior_mean, self.Omega = self.update_with_measurement(k,
                                                    update_raman_frequency=update_raman_frequency,
                                                    update_rabi_frequency=update_rabi_frequency,
                                                    include_photon_noise=include_photon_noise)
            else:
                k = self.measurement(i)
                self.probe_point(i, 3, t_start_mu)
                self.omega_raman, omega_posterior_mean, self.Omega = self.generate_posterior(k, t,
                                                        phase_raman_pulse_start=phase_tracker,
                                                        update_raman_frequency=update_raman_frequency,
                                                        update_rabi_frequency=update_rabi_frequency,
                                                        include_photon_noise=include_photon_noise)
            self.probe_point(i, 4, t_start_mu)

            extra = int64(0)
            if reinit_next == 1:
                # measured S_z of the pole readout (linear map, midpoint 0.5)
                s_meas = 2.0 * (k / self.N_photons_per_shot) - 1.0
                self.data.reinit_sz_meas.put_data(s_meas)
                center = self.reinitialize(s_meas, sz_pred)
                self.data.reinit_center.put_data(center)
                reinit_next = 0
                reinit_done = 1
                extra = self.p.t_reinit_extra_mu
            elif reinit_done == 0 and i >= self.p.feedback_reinit_min_pulse - 1 and i < self.p.N_pulses - 2:
                margin = self.alias_margin()
                fire = 0
                if self.p.feedback_reinit_trigger_mode == 1:
                    if margin >= self.p.feedback_reinit_margin_nats:
                        fire = 1
                elif self._posterior_std < self.p.feedback_reinit_std_threshold_Omega * self.Omega:
                    fire = 1
                if self.p.feedback_reinit_force_pulse > 0 and i >= self.p.feedback_reinit_force_pulse - 1:
                    fire = 1
                if fire == 1:
                    self.data.reinit_trigger_std.put_data(self._posterior_std / self.Omega)
                    self.data.reinit_trigger_margin.put_data(margin)
                    extra = self.p.t_reinit_extra_mu
                    if self.p.feedback_reinit_pole_enabled == 1:
                        reinit_next = 1
                    else:
                        # no pole pulse: remesh after this pulse (reinit_pulse = this pulse's index)
                        center = self.remesh_only()
                        self.data.reinit_pulse.put_data(float(i))
                        self.data.reinit_center.put_data(center)
                        reinit_done = 1

            dT = self.compute_t_between_pulses_mu(
                t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
                t_raman_pulse=t_pulse,
                t_img_pulse=self.p.t_img_pulse,
                t_raman_pretrigger=self.p.t_raman_set_pretrigger_mu,
                t_fifo_mu=self.p.t_fifo_mu
            ) + extra
            if i % 2 == 1:
                dT += self.p.t_gap_alt_extra_mu

            self.data.t.put_data(t + t_pulse + self.p.t_img_pulse, i)
            self.data.s_z.put_data(self.state_z[self.zidx], i)

            t_step += dT

            self.per_feedback_loop_end(idx=i)
            self.probe_point(i, 5, t_start_mu)

        self.per_scan_kernel_end()

    @kernel
    def per_feedback_loop_end(self, idx):
        # posterior and grid after pulse idx (row 0 = prior)
        self.data.probabilities.put_data_1d(self.P0, idx+1)
        self.data.omega_raman_mesh.put_data_1d(self.omega_guess_list, idx+1)

    @kernel
    def per_scan_kernel_end(self):
        pass

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
