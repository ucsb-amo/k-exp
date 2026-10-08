"""FeedbackExptFast -- FeedbackExpt with the fast feedback step of the 2026-09-29 timing bench
(session copy, 2026-10-06; user: "implement fast path"). The repo base is untouched.

Per step, as production (base_expt_feedback.FeedbackExpt.feedback_loop) except:
  * the ADC conversion is SUBMITTED (CNV pulse + SPI write, output events only) and the
    measurement-independent half of the posterior -- each hypothesis' Bloch rotation and its
    expected photon fraction (propagate_hypotheses) -- runs while the ADC converts; the blocking
    SPI read follows, then only the likelihood half (weigh_hypotheses). Same arithmetic as
    Feedback.generate_posterior split in two: offline bitwise identical (test_overlap_equivalence,
    2000 random cases on 83531 on 2026-09-29 and on 85201 tonight).
  * the NEXT read's integrator gate + imaging pulse are written right after this read's submit
    (their timing depends only on the pre-drawn pulse times), so no satellite write sits between
    the ADC read and the next deadline (bench mode 2).
  * t_calculation_slack_compensation_mu is set by the run copy (20 us tonight; bench: mode 2 at
    20 us kept a 21 us minimum margin over 10,000 steps, production at 39.7 us had 26 us; 16 us
    was the floor, 14 us underflowed).
Everything else (pre-shot, SLM mask, remesh hooks, per-step data, hooks per_feedback_loop_top/end)
is inherited. p.fast_path = 1 is recorded in the run's params.
"""
import numpy as np
from numpy import int64

from artiq.experiment import *
from artiq.language import now_mu, delay, at_mu
from artiq.coredevice.sampler import adc_mu_to_volt

from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt


class OverlapPosterior:
    """generate_posterior (kexp.base.feedback.Feedback) split at the measurement: the loop body
    before `num = k - n_photons * p1` in propagate_hypotheses, the rest in weigh_hypotheses.
    Every expression is copied in the same order, so the result is bitwise the same."""

    @portable(flags={"fast-math"})
    def propagate_hypotheses(self, t, phase_raman_pulse_start=0.):
        omega_guess_list = self.omega_guess_list
        state_x = self.state_x
        state_y = self.state_y
        state_z = self.state_z
        p1_buf = self.p1_buf

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

            p1_buf[j] = self.expected_photon_fraction(hz)

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
    def weigh_hypotheses(self, k,
                         update_raman_frequency=1,
                         update_rabi_frequency=0,
                         include_photon_noise=1):
        P0_total = 0.0
        moment_2 = 0.0
        mn = 0.0

        omega_guess_list = self.omega_guess_list
        omega_sq_list = self.omega_sq_list
        P0 = self.P0
        p1_buf = self.p1_buf

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
            p1 = p1_buf[j]
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


class FeedbackExptFast(FeedbackExpt, OverlapPosterior):

    def finish_prepare(self, shuffle=True):
        # one expected photon fraction per hypothesis (propagate -> weigh)
        self.p1_buf = np.zeros(int(self.p.feedback_grid_size))
        self.t_sample_mu = int64(0)
        self.t_sample_next_mu = int64(0)
        self.p.fast_path = 1
        print(f"fast path: overlapped ADC read + pre-issued next read; calc slack "
              f"{self.p.t_calculation_slack_compensation_mu / 1.e3:.1f} us")
        super().finish_prepare(shuffle=shuffle)

    @kernel
    def feedback_loop(self, t_start_mu,
                      update_raman_frequency=0,
                      update_rabi_frequency=0,
                      include_photon_noise=1):

        self.omega_z_lightshift = 2 * np.pi * self.p.frequency_lightshift

        f = self.omega_raman / (2*np.pi)

        t_start_mu = t_start_mu & ~7
        t_step = t_start_mu

        at_mu((t_start_mu - 10000) & ~7)

        self.raman.set_frequency_fast(f)
        self.raman.stage_ffua()
        phase_tracker = 0.

        dT = self.p.t_between_pulses_mu
        t_turn_on_delay = self.p.t_raman_pulse_offset

        at_mu(t_start_mu)

        for i in range(self.p.N_pulses):

            self.per_feedback_loop_top(idx=i)
            f = self.omega_raman / (2*np.pi)

            t_pulse = self.p.t_raman_pulse_list[i]
            self.t_raman_pulse_current = t_pulse
            self.t_raman_pulse_ideal_current = t_pulse - t_turn_on_delay

            self.data.omega_raman.put_data(self.omega_raman, i)

            at_mu(t_step - self.p.t_raman_set_pretrigger_mu)
            self.raman.set_frequency_fast(f, do_io_update=False)

            t = (t_step - t_start_mu)*1.e-9

            phase_tracker = self.raman.io_update_and_phase_update(t_pulse_mu = t_step,
                                                                t_last_pulse_mu = t_step - dT)

            at_mu(t_step)

            self.raman.pulse(t_pulse)

            # the gap after this pulse depends only on this step's (pre-drawn) pulse time, so the
            # next read's timing is known before this read returns
            dT_i = self.compute_t_between_pulses_mu(
                t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
                t_raman_pulse=t_pulse,
                t_img_pulse=self.p.t_img_pulse,
                t_raman_pretrigger=self.p.t_raman_set_pretrigger_mu,
                t_fifo_mu=self.p.t_fifo_mu)
            issue_read = i == 0
            preissue = i + 1 < self.p.N_pulses
            t_pulse_next = 0.
            if preissue:
                t_pulse_next = self.p.t_raman_pulse_list[i + 1]

            k = self.measurement_overlap(i, t, phase_tracker, issue_read,
                                         t_step + dT_i, t_pulse_next, preissue)
            self.omega_raman, omega_posterior_mean, self.Omega = self.weigh_hypotheses(
                k, update_raman_frequency=update_raman_frequency,
                update_rabi_frequency=update_rabi_frequency,
                include_photon_noise=include_photon_noise)
            if i > (self.p.n_initial_shots_before_remesh-1):
                self.maybe_remesh(self._posterior_std, omega_center=omega_posterior_mean)

            dT = dT_i

            # time of result of pulse i
            self.data.t.put_data(t + t_pulse + self.p.t_img_pulse, i)
            # result of pulse i
            self.data.s_z.put_data(self.state_z[self.zidx], i)

            t_step += dT

            self.per_feedback_loop_end(idx=i)

        self.per_scan_kernel_end()

    @kernel
    def measurement_overlap(self, i, t, phase_tracker, issue_read, t_next_step, t_pulse_next,
                            preissue):
        """base_expt_feedback.measurement with Sampler_Last_CH.sample_single split: the CNV pulse
        and the SPI write (outputs) are submitted, the measurement-independent half of the
        posterior runs, then the SPI read (the blocking input) and the same decode as sample_single.

        issue_read False = this read's integrator gate + imaging pulse were written in the previous
        step (the cursor jumps to its sample time); preissue True = write the NEXT read's gate +
        imaging pulse now, so no satellite write sits between the ADC read and the next deadline."""
        T_CONV_MU = 80
        if issue_read:
            self.integrator.begin_integrate(reset=False)
            self.imaging.pulse(self.p.t_img_pulse)
            self.integrator.stop_and_settle()
        else:
            at_mu(self.t_sample_next_mu)
        t0 = now_mu()
        self.t_sample_mu = t0
        self.raman.stage_ffua()
        at_mu(t0 + T_CONV_MU)
        self.integrator.clear(t=0)
        at_mu(t0)
        sampler = self.integrator.sampler_ch.sampler_device
        sampler.cnv.pulse(30.e-9)
        delay(450.e-9)
        sampler.bus_adc.write(0)

        if preissue:
            # the next read: same cursor arithmetic as raman.pulse + measurement in step i+1
            at_mu(t_next_step)
            delay(t_pulse_next)
            self.integrator.begin_integrate(reset=False)
            self.imaging.pulse(self.p.t_img_pulse)
            self.integrator.stop_and_settle()
            self.t_sample_next_mu = now_mu()

        self.propagate_hypotheses(t, phase_tracker)

        val = sampler.bus_adc.read()
        adc_data = [0]*2
        mask = 1 << 15
        adc_data[1] = val >> 16
        val &= 0xffff
        adc_data[0] = -(val & mask) + (val & ~mask)
        samples = self.integrator.sampler_ch.samples
        cfs = sampler.corrected_fs
        for ch in [6, 7]:
            channel = (ch-6) + 8 - len(samples)
            gain = (sampler.gains >> (channel)*2) & 0b11
            samples[ch] = adc_mu_to_volt(adc_data[ch-6], gain, cfs)
        self.data.apd.shot_data[i] = samples[self.integrator.sampler_ch.ch]
        v = self.convert_measurement(self.data.apd.shot_data[i])
        return v
