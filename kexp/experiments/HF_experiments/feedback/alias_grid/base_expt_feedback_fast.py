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
Everything else (SLM mask, remesh hooks, per-step data, hooks per_feedback_loop_top/end)
is inherited. p.fast_path = 1 is recorded in the run's params.
"""
import numpy as np
from numpy import int64

from artiq.experiment import *
from artiq.language import now_mu, delay, at_mu
from artiq.coredevice.sampler import adc_mu_to_volt

from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt
from kexp.experiments.HF_experiments.feedback.fastest.fastest_loop import OverlapPosterior


# OverlapPosterior moved to fastest/fastest_loop.py (2026-11-04), where FeedbackExpt's default loop uses it;
# imported here so this class and tests/test_fastpath_posterior.py keep their names.


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
        if issue_read:
            self.readout_pulse()
        else:
            at_mu(self.t_sample_next_mu)
        self.t_sample_mu = now_mu()
        self.readout_prepare_sample()
        sampler = self.integrator.sampler_ch.sampler_device
        sampler.cnv.pulse(30.e-9)
        delay(450.e-9)
        sampler.bus_adc.write(0)

        if preissue:
            # the next read: same cursor arithmetic as raman.pulse + measurement in step i+1
            at_mu(t_next_step)
            delay(t_pulse_next)
            self.readout_pulse()
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
