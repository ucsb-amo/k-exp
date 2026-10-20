"""FeedbackExptBimodal -- FeedbackExptGrid with a bimodality-aware drive choice (session copy
2026-10-08 ~10:00; repo base untouched).

After each posterior update the loop normally drives the MAP (or the mean when the posterior is
flatter than 1.15 x uniform, inside weigh_hypotheses). This class adds one rule, applied in the
loop right after weigh_hypotheses: if the largest posterior value OUTSIDE the MAP's neighbourhood
(|j - max_idx| >= p.bimodal_min_separation grid points) is at least p.bimodal_mode_ratio times the
maximum, the posterior is bimodal and the drive is set to the posterior MEAN instead of the MAP.
For the symmetric two-mode posterior after pulse 0 the mean lies at the previous drive, so the loop
takes a second measurement there before committing to either mode (the mirror-image problem seen
from positive initial offsets, REPORT Addendum 8). Per pulse the loop records data.bimodal_ratio
(second mode / max) and data.drive_rule (0 = MAP or weigh_hypotheses' own flat rule, 1 = mean by
this rule). Everything else is FeedbackExptAlt's loop: alternating extra gaps, data.dT_mu, fast path.
"""
import numpy as np
from numpy import int64

from artiq.experiment import *
from artiq.language import now_mu, delay, at_mu

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from base_expt_feedback_grid import FeedbackExptGrid


class FeedbackExptBimodal(FeedbackExptGrid):

    def finish_prepare(self, shuffle=True):
        p = self.p
        p.bimodal_mode_ratio = float(getattr(p, "bimodal_mode_ratio", 0.5))
        p.bimodal_min_separation = int(getattr(p, "bimodal_min_separation", 2))
        p.bimodal_rule = 1
        n = int(p.N_pulses)
        self.data.bimodal_ratio = self.data.add_data_container(n)
        self.data.drive_rule = self.data.add_data_container(n)
        print(f"bimodal drive rule: mean instead of MAP when a second mode >= {p.bimodal_mode_ratio} x max at >= "
              f"{p.bimodal_min_separation} points from the MAP")
        super().finish_prepare(shuffle=shuffle)

    @portable(flags={"fast-math"})
    def second_mode_ratio(self):
        """Largest P0 at least p.bimodal_min_separation indices from the MAP, over P0[max]."""
        m = self.m
        max_idx = self.max_idx
        pmax = self.P0[max_idx]
        sep = self.p.bimodal_min_separation
        second = 0.0
        j = 0
        while j < m:
            d = j - max_idx
            if d < 0:
                d = -d
            if d >= sep and self.P0[j] > second:
                second = self.P0[j]
            j += 1
        if pmax > 0.0:
            return second / pmax
        return 0.0

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

            # bimodality rule: a second mode comparable to the MAP -> drive the posterior mean
            ratio = self.second_mode_ratio()
            self.data.bimodal_ratio.put_data(ratio, i)
            rule = 0.
            if update_raman_frequency:
                if ratio >= self.p.bimodal_mode_ratio:
                    self.omega_raman = omega_posterior_mean
                    rule = 1.
            self.data.drive_rule.put_data(rule, i)

            if i > (self.p.n_initial_shots_before_remesh-1):
                self.maybe_remesh(self._posterior_std, omega_center=omega_posterior_mean)

            dT = dT_i

            self.data.t.put_data(t + t_pulse + self.p.t_img_pulse, i)
            self.data.s_z.put_data(self.state_z[self.zidx], i)

            t_step += dT

            self.per_feedback_loop_end(idx=i)

        self.per_scan_kernel_end()
