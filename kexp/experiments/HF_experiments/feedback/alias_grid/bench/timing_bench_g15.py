"""Feedback-loop timing bench (no atoms), 2026-09-29 night, session code-31.

The feedback loop of base_expt_feedback.FeedbackExpt without the BEC: every shot runs
BENCH_PULSES raman-pulse / APD-read / posterior steps on the imaging light alone (no atoms: the
cooling beams are powered down, no MOT load, no tweezers), and records per pulse (ns):

  data.bench_margin[i]  next-step deadline (t_step - pretrigger) minus the RTIO counter when the
                        CPU arrives there = the slack left over from step i-1 (negative = late)
  data.bench_read[i]    RTIO counter when the ADC read returned minus the sample timestamp
  data.bench_post[i]    CPU time from the read's return to the end of the posterior

Modes (env BENCH_MODE, recorded as p.bench_mode):
  0  as production: measurement() then generate_posterior() after the blocking ADC read
  1  overlap: submit the ADC conversion (CNV + SPI write, output events only), compute the
     measurement-independent half of the posterior (each hypothesis' Bloch rotation and its
     expected photon fraction) while the ADC converts, then read and apply only the
     likelihood half (weigh_hypotheses). Same arithmetic, split in two (offline equivalence
     test: test_overlap_equivalence.py).
Env BENCH_SLACK_US > 0 overrides t_calculation_slack_compensation_mu (us); BENCH_PULSES (default
200) sets N_pulses; BENCH_SHOTS (default 10) the number of shots. Integrator window and all other
feedback params as expt_params_feedback (new window 0.7 / 1.0 / 4.0 us).
"""
import os

from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, at_mu
from artiq.coredevice.sampler import adc_mu_to_volt, SPI_CONFIG, SPI_CS_ADC
from artiq.coredevice import spi2 as spi
import numpy as np
from numpy import int64

from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt

BENCH_MODE = int(os.environ.get("BENCH_MODE", "0"))
BENCH_SLACK_US = float(os.environ.get("BENCH_SLACK_US", "0"))
BENCH_PULSES = int(os.environ.get("BENCH_PULSES", "200"))
BENCH_SHOTS = int(os.environ.get("BENCH_SHOTS", "10"))
BENCH_DIV = int(os.environ.get("BENCH_DIV", "8"))
BENCH_GRID = int(os.environ.get("BENCH_GRID", "0"))   # session copy 2026-10-07: grid size override (0 = params default)


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


class timing_bench(EnvExperiment, FeedbackExpt, OverlapPosterior):

    def prepare(self):
        FeedbackExpt.__init__(self, save_data=True, save_on_underflow=True)

        self.p.update_raman_frequency_bool = 1
        self.p.include_photon_noise = 1
        self.p.N_pulses = BENCH_PULSES
        if BENCH_GRID > 0:
            self.p.feedback_grid_size = BENCH_GRID
        self.p.bench_mode = BENCH_MODE
        if BENCH_SLACK_US > 0.:
            self.p.t_calculation_slack_compensation_mu = int64(BENCH_SLACK_US * 1.e3)
        self.p.feedback_fractional_initial_offset = 0.
        self.p.N_warmup_shots = 1
        self.p.bench_shot = 0
        self.xvar('bench_shot', np.arange(BENCH_SHOTS))
        # BENCH_DIV != 8: shots alternate (shuffled) between the default Sampler ADC SPI divider
        # (8) and BENCH_DIV, so the APD reads can be compared at the same light level; every
        # shot restores 8 at its end (and every run's init re-inits the Sampler at 8)
        self.p.bench_div = 8
        if BENCH_DIV != 8:
            self.xvar('bench_div', np.array([8, BENCH_DIV]))

        self.data.bench_margin = self.data.add_data_container(BENCH_PULSES)
        self.data.bench_read = self.data.add_data_container(BENCH_PULSES)
        self.data.bench_post = self.data.add_data_container(BENCH_PULSES)
        # CPU-time profile of one step (ns, modes >= 1): top = frequency set + phase update +
        # raman pulse writes; meas = the read's event writes up to the ADC submit; pre = the
        # pre-issued next read (mode 2); prop = propagate_hypotheses; wait = until the ADC read
        # returns (includes any time the CPU is ahead of the sample)
        self.data.seg_top = self.data.add_data_container(BENCH_PULSES)
        self.data.seg_meas = self.data.add_data_container(BENCH_PULSES)
        self.data.seg_pre = self.data.add_data_container(BENCH_PULSES)
        self.data.seg_prop = self.data.add_data_container(BENCH_PULSES)
        self.data.seg_wait = self.data.add_data_container(BENCH_PULSES)
        self.c_b = int64(0)
        self.c_c = int64(0)
        self.c_d = int64(0)
        self.c_e = int64(0)
        self.t_sample_mu = int64(0)
        self.t_sample_next_mu = int64(0)
        # one expected photon fraction per hypothesis (propagate -> weigh)
        self.p1_buf = np.zeros(int(self.p.feedback_grid_size))
        print(f"bench: mode {BENCH_MODE}, {BENCH_PULSES} pulses x {BENCH_SHOTS} shots, "
              f"calc slack {self.p.t_calculation_slack_compensation_mu / 1.e3:.1f} us")

        self.finish_prepare()

    @kernel
    def scan_kernel(self):
        self.core.wait_until_mu(now_mu())
        self.p.omega_pulse_list = self.get_new_pulse_list(seed=self.p.pulse_list_seed)
        t_raman_pulse_seed = self.resolve_t_raman_pulse_seed()
        self.p.t_raman_pulse_list = self.get_new_t_raman_pulse_list(seed=t_raman_pulse_seed)
        self.data.t_raman_pulse_seed.put_data(float(t_raman_pulse_seed))
        self.data.t_raman_pulse.put_data_1d(self.p.t_raman_pulse_list)
        self.omega_raman = self.p.omega_pulse_list[0]
        self.core.break_realtime()

        self.power_down_cooling()
        self.set_adc_div(int(self.p.bench_div))
        self.integrator.init()
        self.initialize_feedback()
        delay(10.e-3)

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)
        self.prep_raman(frequency_transition=self.omega_raman/(2*np.pi), phase_mode=0)

        t_pulse_start_mu = now_mu() + 500000
        self.raman.set_up_fast_frequency_update(aggressive_mode=1)
        at_mu(t_pulse_start_mu - 20000)
        self.bench_loop(t_start_mu=t_pulse_start_mu)

        delay(1.e-3)
        self.raman.clean_up_fast_frequency_update()
        self.ttl.raman_shutter.off()
        self.set_adc_div(8)
        self.core.wait_until_mu(now_mu())
        self.reset_initial_omega_from_params()
        delay(30.e-3)

    @kernel
    def set_adc_div(self, div):
        """Sampler ADC SPI divider, as Sampler.init sets it (default 8), plus the driver's
        transfer duration (so SPI writes advance the timeline by the right amount)."""
        sampler = self.integrator.sampler_ch.sampler_device
        sampler.bus_adc.set_config_mu(SPI_CONFIG | spi.SPI_INPUT | spi.SPI_END, 32, div, SPI_CS_ADC)
        sampler.bus_adc.update_xfer_duration_mu(div, 32)
        delay(10.e-6)

    @kernel
    def bench_loop(self, t_start_mu):
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
            f = self.omega_raman / (2*np.pi)
            t_pulse = self.p.t_raman_pulse_list[i]
            self.t_raman_pulse_current = t_pulse
            self.t_raman_pulse_ideal_current = t_pulse - t_turn_on_delay
            self.data.omega_raman.put_data(self.omega_raman, i)

            t_deadline = t_step - self.p.t_raman_set_pretrigger_mu
            c_a = self.core.get_rtio_counter_mu()
            self.data.bench_margin.put_data(float(t_deadline - c_a), i)
            at_mu(t_deadline)
            self.raman.set_frequency_fast(f, do_io_update=False)
            t = (t_step - t_start_mu)*1.e-9
            phase_tracker = self.raman.io_update_and_phase_update(t_pulse_mu=t_step,
                                                                t_last_pulse_mu=t_step - dT)
            at_mu(t_step)
            self.raman.pulse(t_pulse)
            self.c_b = self.core.get_rtio_counter_mu()
            self.data.seg_top.put_data(float(self.c_b - c_a), i)

            if self.p.bench_mode >= 1:
                # dT depends only on this step's (pre-drawn) pulse time: known before the read
                dT_i = self.compute_t_between_pulses_mu(
                    t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
                    t_raman_pulse=t_pulse,
                    t_img_pulse=self.p.t_img_pulse,
                    t_raman_pretrigger=self.p.t_raman_set_pretrigger_mu,
                    t_fifo_mu=self.p.t_fifo_mu)
                issue_read = True
                if self.p.bench_mode == 2 and i > 0:
                    issue_read = False
                preissue = False
                t_pulse_next = 0.
                if self.p.bench_mode == 2 and i + 1 < self.p.N_pulses:
                    preissue = True
                    t_pulse_next = self.p.t_raman_pulse_list[i + 1]
                k = self.measurement_overlap(i, t, phase_tracker, issue_read,
                                             t_step + dT_i, t_pulse_next, preissue)
                c1 = self.core.get_rtio_counter_mu()
                self.omega_raman, omega_posterior_mean, self.Omega = self.weigh_hypotheses(
                    k, update_raman_frequency=1, update_rabi_frequency=0, include_photon_noise=1)
            else:
                k = self.measurement_timed(i)
                c1 = self.core.get_rtio_counter_mu()
                self.omega_raman, omega_posterior_mean, self.Omega = self.generate_posterior(
                    k, t, phase_raman_pulse_start=phase_tracker, update_raman_frequency=1,
                    update_rabi_frequency=0, include_photon_noise=1)
            c2 = self.core.get_rtio_counter_mu()
            self.data.bench_read.put_data(float(c1 - self.t_sample_mu), i)
            self.data.bench_post.put_data(float(c2 - c1), i)
            if self.p.bench_mode >= 1:
                self.data.seg_meas.put_data(float(self.c_c - self.c_b), i)
                self.data.seg_pre.put_data(float(self.c_d - self.c_c), i)
                self.data.seg_prop.put_data(float(self.c_e - self.c_d), i)
                self.data.seg_wait.put_data(float(c1 - self.c_e), i)

            dT = self.compute_t_between_pulses_mu(
                t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
                t_raman_pulse=t_pulse,
                t_img_pulse=self.p.t_img_pulse,
                t_raman_pretrigger=self.p.t_raman_set_pretrigger_mu,
                t_fifo_mu=self.p.t_fifo_mu)
            t_step += dT

    @kernel
    def measurement_timed(self, i):
        """base_expt_feedback.measurement, recording the sample timestamp."""
        T_CONV_MU = 80
        self.integrator.begin_integrate(reset=False)
        self.imaging.pulse(self.p.t_img_pulse)
        self.integrator.stop_and_settle()
        t0 = now_mu()
        self.t_sample_mu = t0
        self.raman.stage_ffua()
        at_mu(t0 + T_CONV_MU)
        self.integrator.clear(t=0)
        at_mu(t0)
        self.data.apd.shot_data[i] = self.integrator.sample()
        v = self.convert_measurement(self.data.apd.shot_data[i])
        return v

    @kernel
    def measurement_overlap(self, i, t, phase_tracker, issue_read, t_next_step, t_pulse_next,
                            preissue):
        """measurement_timed with Sampler_Last_CH.sample_single split: the CNV pulse and the SPI
        write (outputs) are submitted, the measurement-independent half of the posterior runs,
        then the SPI read (the blocking input) and the same decode as sample_single.

        Mode 2: issue_read False = this read's integrator gate + imaging pulse were written in the
        previous step (the cursor jumps to its sample time); preissue True = write the NEXT read's
        gate + imaging pulse now (its timing depends only on the pre-drawn pulse times), so no
        satellite write sits between the ADC read and the next deadline."""
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
        self.c_c = self.core.get_rtio_counter_mu()

        if preissue:
            # the next read: same cursor arithmetic as raman.pulse + measurement in step i+1
            at_mu(t_next_step)
            delay(t_pulse_next)
            self.integrator.begin_integrate(reset=False)
            self.imaging.pulse(self.p.t_img_pulse)
            self.integrator.stop_and_settle()
            self.t_sample_next_mu = now_mu()
        self.c_d = self.core.get_rtio_counter_mu()

        self.propagate_hypotheses(t, phase_tracker)
        self.c_e = self.core.get_rtio_counter_mu()

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

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        self.end(os.path.abspath(__file__), notify=False, restart_monitor=False)
