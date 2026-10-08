"""FeedbackExptAlt -- FeedbackExptFast (the verified 2026-10-06 fast-path session copy, 85204 /
85213-85243) with a per-pulse EXTRA inter-pulse delay, for the non-commensurate pulse-start
schedule test (session copy 2026-10-07, PLAN_gap_cycles.md; the repo base is untouched).

Changes against FeedbackExptFast, both inside feedback_loop:
  * dT_i += p.t_gap_extra_list_mu[i]  -- an int64 array (length N_pulses, 8 ns aligned) built in
    finish_prepare from p.t_gap_cycle_extra_us (a repeating cycle of extra delays in us; [0.] =
    today's behaviour). The extra is dead time appended to the gap after the posterior has run,
    so slack only grows. t_step, the pre-issued next read and io_update_and_phase_update already
    take the actual gap, and the time handed to the posterior is t_step - t_start_mu, so the
    kernel model is unchanged. generate_posterior / OverlapPosterior are not touched.
  * the gap actually used after pulse i is recorded in data.dT_mu[i] (ns). The stock host replay
    reconstructs gaps as 'constant base + drawn pulse time' and would replay these runs on the
    wrong timeline; alias_replay_gaps.FeedbackReplayGaps reads this container instead.
p.alt_gaps = 1 is recorded in the run's params.
"""
import numpy as np
from numpy import int64

from artiq.experiment import *
from artiq.language import now_mu, delay, at_mu

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from base_expt_feedback_fast import FeedbackExptFast


class FeedbackExptAlt(FeedbackExptFast):

    def finish_prepare(self, shuffle=True):
        cycle = np.atleast_1d(np.asarray(getattr(self.p, "t_gap_cycle_extra_us", [0.]), dtype=float))
        n = int(self.p.N_pulses)
        extra_ns = np.rint(cycle[np.arange(n) % cycle.size] * 1.e3).astype(np.int64)
        extra_ns = extra_ns & ~np.int64(7)
        self.p.t_gap_cycle_extra_us = cycle
        # float array (exact integers, ns): the scan machinery generates a kernel setter
        # `self.params.<key> = value` with a float value for every array param, so an
        # int64 array param does not compile (85396). Cast to int64 in the kernel.
        self.p.t_gap_extra_list_mu = extra_ns.astype(float)
        self.p.alt_gaps = 1
        # the gap actually used after pulse i (ns), one value per pulse
        self.data.dT_mu = self.data.add_data_container(n)
        print(f"alt gaps: extra delay cycle {cycle.tolist()} us -> per-pulse extra (us) "
              f"{(extra_ns / 1.e3).tolist()}")
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

            # gap after this pulse: the fast-path gap plus this step's extra delay (schedule)
            dT_i = self.compute_t_between_pulses_mu(
                t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
                t_raman_pulse=t_pulse,
                t_img_pulse=self.p.t_img_pulse,
                t_raman_pretrigger=self.p.t_raman_set_pretrigger_mu,
                t_fifo_mu=self.p.t_fifo_mu)
            dT_i = dT_i + np.int64(self.p.t_gap_extra_list_mu[i])
            self.data.dT_mu.put_data(float(dT_i), i)

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
