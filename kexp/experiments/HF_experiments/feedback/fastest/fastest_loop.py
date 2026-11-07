"""The fastest feedback loop: FeedbackExpt's default loop since 2026-11-04 (p.fast_path = 2).

What it is: the no-atom bench kernel of 2026-11-01/02 (bench_fastest_t23_guarded.py in this folder,
run 90988; README.md) cut down to FeedbackExpt's own loop -- every step a pulse and a read, no S2
arms -- with the library posterior. Per step, against the standard loop (feedback_loop_standard):

  * the frequency word is one RTIO write to the one moving AO (RAMAN_AO_SINGLE, anchored at the
    transition frequency, so both AOs sit where RAMAN_AO_BOTH puts them there), with no flag
    bookkeeping (hot_write); IO_UPDATE and the phase accumulator are the same events and the same
    integers as RamanBeamPair.io_update_and_phase_update (hot_update);
  * the read is one DMA playback at the pulse end: integrator gate, imaging pulse, sample, the ADC
    conversion and SPI write, the DDS staging for the next word, and, for every step but the last,
    the next step's IO_UPDATE and Raman pulse-on (trace "fb_fastest_chain"; the last read plays
    "fb_fastest_read");
  * the measurement-independent half of the posterior runs while the ADC converts
    (OverlapPosterior.propagate_hypotheses), then the blocking read (16-bit transfer, channel 7
    only), then the likelihood half (weigh_hypotheses). The two halves are
    Feedback.generate_posterior bit for bit on the host (tests/test_fastpath_posterior.py);
  * deadline guard: a frequency word with under 1 us of lead ends the shot as an RTIOUnderflow
    (a late word at the satellite is silent and misframes the rest of the shot); stage/write
    counters: a write needs exactly one staging since the last (ValueError otherwise).

What is the same: the gap (Feedback.compute_t_between_pulses_mu, so the slack sets the spacing exactly
as before), the pulse times, the posterior, remesh, the per-step records (omega_raman, apd, t, s_z)
and the hooks per_feedback_loop_top / per_feedback_loop_end / per_scan_kernel_end in their order.
The read starts 1-15 ns after the pulse end instead of at it (the trace is fixed; the gap is not a
multiple of 8 ns in general).

Since 2026-11-05 the loop runs as the bench kernel did (user: "lengthen only the first gap if it gets
rid of the 5us ... port the S2 numerics and fix it to be default if it works fine. +3 for the margin
is fine"):

  * the posterior numerics are the bench's (LeanPosterior; p.fastest_posterior = 1), the same model as
    the library's to rounding (tests/test_fastest_lean_posterior.py); p.fastest_posterior = 0 runs the
    library's (OverlapPosterior). A class that overrides a helper the lean numerics inline
    (LEAN_INLINED) gets the library's, with a printed reason;
  * with the measured required slack, the first gap (pulse 0 -> 1) is 5 us longer than the rest and
    step 0 is not chained, as every bench rung ran (p.fastest_first_gap_extra_mu = -1, auto; an
    experiment that keeps its own slack keeps its timeline, no stretch; a value >= 0 is used as set): the first post-read step of a shot has ~4.4 us less margin
    than the rest, at every spacing tried (90871: 33.7 vs 38.2 us at T 66.7; 90873: 9.3 vs 13.7 us at
    T 42, the same code path every step). Cause not shown; most likely a cold first pass through the
    post-read code (caches) after the shot's sequence.

Spacing (since 2026-11-05, user: "the fastest loop feedback should pick the wait time from the
measured required slack. make this the default behavior"): the slack is fastest_timing.required_slack_mu
-- the bench slack that passed the rule for this grid size (90958 at m 21: the floor 23.15 us + 3.0 us),
+ .5 us for the deadline guard, + whatever the run's settings lack against the bench's (the library
posterior bound 6.1 us; a first-gap stretch under 5 us). At the defaults: -0.416 us of slack, T ~ 26.6 us
at m 21 (the standard loop: 39.7 us of slack, T ~ 66.7 us). An experiment that sets
t_calculation_slack_compensation_mu itself, or p.fastest_slack_auto = 0, keeps its own. The standard
loop's slack is unchanged. A grid above 21 points is refused (SlackUntested, before a run id) until a
slack test on this loop has an entry in MEASURED_SLACK_FLOOR_US (README.md "Slack test").

Not tested with atoms. Before trusting data at a new spacing: README.md "Before atoms".
"""
import numpy as np
from numpy import int64, int32

from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, at_mu, TFloat
from artiq.coredevice.rtio import rtio_output
from artiq.coredevice.exceptions import RTIOUnderflow
from artiq.coredevice.sampler import adc_mu_to_volt, SPI_CONFIG, SPI_CS_ADC
from artiq.coredevice import spi2 as spi

from waxx.control.raman_beams import RAMAN_AO_SINGLE

# p.fast_path: which loop ran. 0 the standard loop (or a class with its own loop),
# 1 the overlap loop (alias_grid FeedbackExptFast, own loop), 2 this loop.
FAST_PATH_STANDARD = 0
FAST_PATH_OVERLAP = 1
FAST_PATH_FASTEST = 2

TRACE_READ = "fb_fastest_read"
TRACE_CHAIN = "fb_fastest_chain"

# a frequency word written with less lead than this ends the shot (bench: about .5 us a step)
MIN_LEAD_MU = 1000
# single-AO mode moves one AO by the whole change; the bench ran within the feedback grid
# (+-10 kHz). A scanned transition frequency spread wider than this gets the standard loop.
MAX_AO_SPREAD_HZ = 50.e3
# params the DMA traces and the folded constants are built from: scanned -> the standard loop
TRACE_PARAMS = ("t_img_pulse", "t_integrator_gate_delay", "t_integrator_gate_extra",
                "t_integrator_settle", "t_calculation_slack_compensation_mu",
                "t_raman_set_pretrigger_mu", "t_fifo_mu", "t_io_update_pretrigger_mu",
                "t_ffu_dds_pipeline_latency", "t_ffu_pipeline_latency_fudge_mu", "N_pulses",
                "n_initial_shots_before_remesh")
# methods this loop does not call (it plays its own read and splits the posterior): a class
# that overrides one of them, or the halves, gets the standard loop, which does call them
BYPASSED = ("measurement", "readout_pulse", "readout_prepare_sample", "readout_events",
            "generate_posterior", "propagate_hypotheses", "weigh_hypotheses")
# p.fastest_posterior: which posterior numerics the fastest loop runs. 1 the lean numerics of the bench
# kernel (LeanPosterior, the default since 2026-11-05), 0 the library's (OverlapPosterior, bit for bit
# Feedback.generate_posterior on the host). Both are the same model; they differ in rounding.
POSTERIOR_LIBRARY = 0
POSTERIOR_LEAN = 1
# library helpers LeanPosterior inlines: a class that overrides one gets the library posterior, which
# calls them
LEAN_INLINED = ("expected_photon_fraction", "sincos_lut_interp")
# p.fastest_first_gap_extra_mu: FIRST_GAP_AUTO (the default) stretches the first gap by the bench's
# FIRST_GAP_BENCH_MU when the loop takes the measured required slack, and not at all when the experiment
# keeps its own slack; any value >= 0 (a multiple of 8 ns) is used as set
FIRST_GAP_AUTO = -1
FIRST_GAP_BENCH_MU = 5000
# params chosen once per run: scanning one is refused before a run id
UNSCANNABLE = ("fast_path", "fastest_slack_auto", "fastest_posterior", "fastest_first_gap_extra_mu")


class OverlapPosterior:
    """generate_posterior (kexp.base.feedback.Feedback) split at the measurement: the loop body
    before `num = k - n_photons * p1` in propagate_hypotheses, the rest in weigh_hypotheses.
    Every expression is copied in the same order, so the result is bitwise the same on the host
    (tests/test_fastpath_posterior.py). Moved here from alias_grid/base_expt_feedback_fast.py
    (2026-11-04), which imports it from here."""

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
        if self.read_alpha_lightshift_on:
            # the read's constant z angle set on its own (theta11: 1.432 rad); off: w_ls t_img
            alpha_z_lightshift = self.read_alpha_lightshift
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

            # State-dependent read (2026-10-11; READ_TWIST_SIGN in kexp.base.feedback).
            # Off (the defaults): exactly the constant model -- the same multiply
            # by back_action_coherence. On: a twist d = read_twist * hz added to
            # the z rotation (second order, not renormalised: sin d ~ d,
            # cos d ~ 1 - d^2/2 -- model M1-p2, no worse than exact trig in the
            # simulation check), and the coherence
            # c0 + slope * hz (clipped to [0, 1]); hz is this point's z at the read.
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
        omega_max = self.map_frequency(max_idx, max_prob)
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


class LeanPosterior:
    """The posterior numerics of the bench kernel (bench_fastest_t23_guarded.py, the S2 class:
    propagate_hypotheses + update_with_measurement), the ones every bench floor was measured with,
    made complete for FeedbackExpt's loop. Default posterior of the fastest loop since 2026-11-05
    (user: "port the S2 numerics and fix it to be default if it works fine").

    The same model as Feedback.generate_posterior, term for term; what differs is arithmetic only:

      * propagate: the hypothesis' rotation angle through the sine table inline (the same table and
        the same interpolation as sincos_lut_interp); the rotation products grouped as
        (1 - cos) * u_a * u_b; the read fraction inline (expected_photon_fraction's expression);
      * weigh: the Gaussian read likelihood without its prefactor sigma / sqrt(sigma^2), which is 1
        (it cancels in the normalisation anyway) and with 1 / (2 sigma^2) computed once; the
        normalisation as one multiply by 1 / total, fused with the search for the maximum (the
        first maximum, as the library's strict > from index 0);
      * the posterior std only when something uses it (hc_lean_need_std: the remesh is on; or
        update_rabi_frequency), as the bench's "std on demand". When it is not computed,
        _posterior_std is -1, never a stale value.

    Kept from the library, which the bench did not have: the binomial read (include_photon_noise 0),
    the std and the Rabi-rate output, the degenerate (all-zero) and flat branches, map_frequency.
    tests/test_fastest_lean_posterior.py holds it against the library posterior."""

    @portable(flags={"fast-math"})
    def lean_propagate(self, t, phase_raman_pulse_start=0.):
        omega_guess_list = self.omega_guess_list
        state_x = self.state_x
        state_y = self.state_y
        state_z = self.state_z
        p1s = self.p1_buf
        m = self.m
        omega_raman = self.omega_raman
        Omega = self.Omega
        Omega_sq = Omega * Omega
        dt_eff = self.t_raman_pulse_current
        dt_ideal = self.t_raman_pulse_ideal_current
        dt_z = self.p.t_img_pulse
        twist_on = self.read_twist_on
        twist = self.read_twist
        coherence0 = self.back_action_coherence
        slope_on = self.read_coherence_slope_on
        slope = self.read_coherence_slope
        remap = self.feedback_measurement_midpoint_remap_enabled
        two_pi = self.two_pi
        inv_two_pi = self.inv_two_pi
        lut_scale = self.lut_scale
        lut_mask = self.lut_mask
        lut_quarter = self.lut_quarter
        sin_lut = self.sin_lut
        mid = self.feedback_measurement_midpoint_fraction - 0.5
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
        if self.read_alpha_lightshift_on:
            alpha_z_lightshift = self.read_alpha_lightshift
        alpha_z = dt_eff * delta_omega0 - alpha_z_lightshift
        (sin_z, cos_z) = self.sincos_lut_interp(alpha_z)
        alpha_z_step = dt_eff * domega
        (sin_z_step, cos_z_step) = self.sincos_lut_interp(alpha_z_step)
        j = 0
        while j < m:
            delta_omega = omega_raman - omega_guess_list[j]
            norm_H = np.sqrt(Omega_sq + delta_omega * delta_omega)
            if norm_H > 0.0:
                inv_norm_H = 1.0 / norm_H
                Omega_over_H = Omega * inv_norm_H
                u_z = delta_omega * inv_norm_H
                # sincos_lut_interp(-dt_ideal * norm_H), inline
                x = -dt_ideal * norm_H
                x -= two_pi * int(x * inv_two_pi)
                if x < 0.0:
                    x += two_pi
                y = x * lut_scale
                i0 = int(y) & lut_mask
                frac = y - i0
                i1 = (i0 + 1) & lut_mask
                s0 = sin_lut[i0]
                c0 = sin_lut[(i0 + lut_quarter) & lut_mask]
                sin_H = s0 + frac * (sin_lut[i1] - s0)
                cos_H = c0 + frac * (sin_lut[(i1 + lut_quarter) & lut_mask] - c0)
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
            uxuy = one_minus_cos * u_x * u_y
            uxuz = one_minus_cos * u_x * u_z
            uyuz = one_minus_cos * u_y * u_z
            hx = (cos_H + one_minus_cos * u_x * u_x) * sx + (uxuy - sin_H * u_z) * sy + (uxuz + sin_H * u_y) * sz
            hy = (uxuy + sin_H * u_z) * sx + (cos_H + one_minus_cos * u_y * u_y) * sy + (uyuz - sin_H * u_x) * sz
            hz = (uxuz - sin_H * u_y) * sx + (uyuz + sin_H * u_x) * sy + (cos_H + one_minus_cos * u_z * u_z) * sz
            nx = cos_z * hx + sin_z * hy
            ny = -sin_z * hx + cos_z * hy
            if twist_on:
                d_twist = twist * hz
                cos_d = 1.0 - d_twist * d_twist * 0.5
                nx_twisted = cos_d * nx + d_twist * ny
                ny = -d_twist * nx + cos_d * ny
                nx = nx_twisted
            coherence = coherence0
            if slope_on:
                coherence = coherence + slope * hz
                if coherence < 0.0:
                    coherence = 0.0
                elif coherence > 1.0:
                    coherence = 1.0
            state_x[j] = nx * coherence
            state_y[j] = ny * coherence
            state_z[j] = hz
            # expected_photon_fraction(hz), inline
            p1 = 0.5 * (1.0 + hz)
            if remap:
                p1 += mid * (1.0 - hz * hz)
            if p1 < 0.0:
                p1 = 0.0
            elif p1 > 1.0:
                p1 = 1.0
            p1s[j] = p1
            next_sin_wt = sin_wt * cos_wt_step + cos_wt * sin_wt_step
            cos_wt = cos_wt * cos_wt_step - sin_wt * sin_wt_step
            sin_wt = next_sin_wt
            next_sin_z = sin_z * cos_z_step + cos_z * sin_z_step
            cos_z = cos_z * cos_z_step - sin_z * sin_z_step
            sin_z = next_sin_z
            j += 1

    @portable(flags={"fast-math"})
    def lean_weigh(self, k, update_raman_frequency=1, update_rabi_frequency=0, include_photon_noise=1):
        P0_total = 0.0
        moment_2 = 0.0
        mn = 0.0
        omega_guess_list = self.omega_guess_list
        omega_sq_list = self.omega_sq_list
        P0 = self.P0
        p1s = self.p1_buf
        m = self.m
        n_photons = int(self.N_photons_per_shot)
        need_std = self.hc_lean_need_std
        if update_rabi_frequency:
            need_std = 1
        if include_photon_noise:
            sigma = self.std_n_photons_per_shot
            c = 0.5 / (sigma * sigma)
            j = 0
            while j < m:
                num = k - n_photons * p1s[j]
                pj = P0[j] * np.exp(-c * num * num)
                P0_total += pj
                mn += pj * omega_guess_list[j]
                if need_std:
                    moment_2 += pj * omega_sq_list[j]
                P0[j] = pj
                j += 1
        else:
            # the binomial read, as the library's
            k_int = int(k)
            if k_int < 0:
                k_int = 0
            if k_int > n_photons:
                k_int = n_photons
            nk_int = n_photons - k_int
            j = 0
            while j < m:
                p1 = p1s[j]
                pj = P0[j] * (self.powi(p1, k_int) * self.powi(1.0 - p1, nk_int))
                P0_total += pj
                mn += pj * omega_guess_list[j]
                if need_std:
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
        max_idx = 0
        max_prob = -1.0
        if P0_total > 1.e-290:
            inv_total = 1.0 / P0_total
            mn = mn * inv_total
            i = 0
            while i < len(P0):
                v = P0[i] * inv_total
                P0[i] = v
                if v > max_prob:
                    max_prob = v
                    max_idx = i
                i += 1
        else:
            # a subnormal total: its inverse overflows to inf (inf * 0 = NaN); divide, as the library does
            inv_total = 0.0
            mn = mn / P0_total
            i = 0
            while i < len(P0):
                v = P0[i] / P0_total
                P0[i] = v
                if v > max_prob:
                    max_prob = v
                    max_idx = i
                i += 1
        self.P0_total = P0_total
        std = -1.0
        if need_std:
            if inv_total > 0.0:
                var = moment_2 * inv_total - mn * mn
            else:
                var = moment_2 / P0_total - mn * mn
            if var < 0.0:
                var = 0.0
            std = np.sqrt(var)
        self._posterior_std = std
        omega_max = self.map_frequency(max_idx, max_prob)
        self.max_idx = max_idx
        uniform_prob = 1.0 / m
        if max_prob < 1.15 * uniform_prob:
            omega_raman_out = mn
            self._flat_prob_counter += 1
        else:
            omega_raman_out = omega_max
        self.omega_max = omega_max
        if not update_raman_frequency:
            omega_raman_out = self.omega_raman
        if not update_rabi_frequency:
            std = self.Omega
        return omega_raman_out, mn, std


class FastestLoop(LeanPosterior):
    """Mixed into FeedbackExpt. Host side: fastest_choose (which loop runs, and why) and
    fastest_finish (the folded constants). Kernel side: the traces, the hot write path, the
    read and the loop."""

    # ---- host ---------------------------------------------------------------------------

    def fastest_refusal(self, base_cls):
        """Why this run cannot take the fastest loop (None: it can). base_cls is FeedbackExpt."""
        p = self.p
        cls = type(self)
        if getattr(cls, "feedback_loop") is not getattr(base_cls, "feedback_loop"):
            return "own loop"
        for name in BYPASSED:
            if getattr(cls, name, None) is not getattr(base_cls, name, None):
                return f"{cls.__name__} overrides {name}, which the fastest loop does not call"
        scanned = {str(x.key) for x in getattr(self, "scan_xvars", ())}
        hit = [k for k in TRACE_PARAMS if k in scanned]
        if hit:
            return f"scans {', '.join(hit)}, which the fastest loop's traces are built from"
        if int(self.integrator.sampler_ch.ch) != 7:
            return f"APD on sampler channel {int(self.integrator.sampler_ch.ch)}: the 16-bit read is channel 7 only"
        f = np.ravel(np.asarray(p.frequency_raman_transition, dtype=float))
        if f.size and float(f.max() - f.min()) > MAX_AO_SPREAD_HZ:
            return (f"scans frequency_raman_transition over {float(f.max() - f.min()) / 1e3:.0f} kHz; "
                    f"single-AO moves are tested within {MAX_AO_SPREAD_HZ / 1e3:.0f} kHz")
        if int(p.N_pulses) < 1:
            return "N_pulses < 1"
        return None

    def fastest_defaults(self, base_cls):
        """The standard loop and no fastest hooks: FeedbackExpt.__init__ sets these, so a class that
        never reaches FeedbackExpt.finish_prepare still compiles its cleanups."""
        self.fast_loop = 0
        self._fastest_traces_recorded = 0
        self._feedback_loop_kernels = [base_cls.feedback_loop_standard]
        self._fastest_shot_kernels = [FastestLoop.fastest_nothing]
        self._fastest_cleanup_kernels = [FastestLoop.fastest_nothing]

    def fastest_choose(self, base_cls):
        """In finish_prepare, before the run is registered: decide the loop, record it in
        p.fast_path, and for the fastest loop put the Raman pair in single-AO mode.

        The choice is a host-side function list (as waxx's abort snapshot), so the kernel
        compiles only the loop that runs: a standard run compiles none of this module's kernels."""
        p = self.p
        scanned = {str(x.key) for x in getattr(self, "scan_xvars", ())}
        for key in UNSCANNABLE:
            if key in scanned:
                raise ValueError(f"{key} cannot be scanned: it is chosen once per run "
                                 "(compare the settings in separate, interleaved runs)")
        want = int(np.ravel(getattr(p, "fast_path", FAST_PATH_FASTEST))[0])
        want_auto_slack = int(np.ravel(getattr(p, "fastest_slack_auto", 1))[0])
        want_posterior = int(np.ravel(getattr(p, "fastest_posterior", POSTERIOR_LEAN))[0])
        want_extra = int(np.ravel(getattr(p, "fastest_first_gap_extra_mu", FIRST_GAP_AUTO))[0])
        if want_posterior not in (POSTERIOR_LIBRARY, POSTERIOR_LEAN):
            raise ValueError(f"fastest_posterior must be {POSTERIOR_LEAN} (lean) or "
                             f"{POSTERIOR_LIBRARY} (library), not {want_posterior}")
        if want_extra != FIRST_GAP_AUTO and (want_extra < 0 or want_extra % 8 != 0):
            raise ValueError(f"fastest_first_gap_extra_mu must be {FIRST_GAP_AUTO} (auto) or >= 0 and a "
                             f"multiple of 8 ns, not {want_extra}")
        # record what ran: the measured slack, the lean posterior and the first-gap stretch are the
        # fastest loop's only; set below only when they apply (the standard loop: library, 0 extra)
        p.fastest_slack_auto = 0
        p.fastest_posterior = POSTERIOR_LIBRARY
        p.fastest_first_gap_extra_mu = int64(0)
        self.fastest_defaults(base_cls)
        if want != FAST_PATH_FASTEST:
            p.fast_path = want
            return
        why = self.fastest_refusal(base_cls)
        if why == "own loop":
            # the class runs its own feedback_loop: record the standard value unless it set its own
            p.fast_path = FAST_PATH_STANDARD
            return
        if why is not None:
            print(f"!! feedback: the standard loop runs, not the fastest loop: {why}.")
            p.fast_path = FAST_PATH_STANDARD
            return
        f_ref = float(np.median(np.ravel(np.asarray(p.frequency_raman_transition, dtype=float))))
        self.raman.set_ao_mode(RAMAN_AO_SINGLE, f_ref)
        self.raman.prepare_direct_fast_path()
        self.p1_buf = np.zeros(int(p.feedback_grid_size))
        self.fast_loop = 1
        self._feedback_loop_kernels = [FastestLoop.feedback_loop_fastest]
        self._fastest_shot_kernels = [FastestLoop.fastest_shot_setup]
        self._fastest_cleanup_kernels = [FastestLoop.fastest_cleanup]
        p.fast_path = FAST_PATH_FASTEST
        # the posterior numerics: lean unless asked otherwise or the class changes a helper it inlines
        posterior = want_posterior
        if posterior == POSTERIOR_LEAN:
            cls = type(self)
            changed = [n for n in LEAN_INLINED if getattr(cls, n, None) is not getattr(base_cls, n, None)]
            if changed:
                print(f"!! feedback: the library posterior runs, not the lean one: {cls.__name__} "
                      f"overrides {', '.join(changed)}, which the lean posterior inlines.")
                posterior = POSTERIOR_LIBRARY
        p.fastest_posterior = posterior
        # the first-gap stretch: auto = the bench's 5 us when the loop takes the measured required slack
        # (the tight spacing it exists for; required_slack_mu assumes it), none when the experiment keeps
        # its own slack (a calibration or a pinned run keeps its timeline as it was); a set value as set
        p.fastest_first_gap_extra_mu = int64(FIRST_GAP_BENCH_MU if want_extra == FIRST_GAP_AUTO else want_extra)
        self.fastest_pick_slack(want_auto_slack)
        if want_extra == FIRST_GAP_AUTO and int(p.fastest_slack_auto) != 1:
            p.fastest_first_gap_extra_mu = int64(0)
        extra = int(p.fastest_first_gap_extra_mu)
        print(f"feedback: fastest loop (single-AO moves anchored at {f_ref:.0f} Hz, DMA read, "
              f"overlapped posterior, deadline guard); "
              f"{'lean' if posterior == POSTERIOR_LEAN else 'library'} posterior; "
              f"first gap +{extra / 1.e3:.3f} us"
              + (" (auto)" if want_extra == FIRST_GAP_AUTO else " (as set)"))

    def fastest_pick_slack(self, want_auto_slack):
        """The fastest loop's spacing: the measured required slack (fastest_timing.required_slack_mu)
        unless p.fastest_slack_auto = 0 or the experiment set t_calculation_slack_compensation_mu
        itself (any value other than the ExptParamsFeedback default it was built with). Records the
        outcome in p.fastest_slack_auto (1 applied, 0 not) and the slack that runs in
        p.t_calculation_slack_compensation_mu."""
        from kexp.experiments.HF_experiments.feedback.fastest import fastest_timing as ft
        p = self.p
        slack_now = int(np.ravel(p.t_calculation_slack_compensation_mu)[0])
        default = getattr(self, "_slack_default_mu", None)
        if not want_auto_slack:
            print(f"feedback: slack {slack_now / 1.e3:.3f} us as set (p.fastest_slack_auto = 0)")
            return
        if default is not None and slack_now != int(default):
            print(f"feedback: slack {slack_now / 1.e3:.3f} us as the experiment set it, "
                  f"not the measured required slack")
            return
        m = int(p.feedback_grid_size)
        slack = ft.required_slack_mu(p, m)
        p.t_calculation_slack_compensation_mu = int64(slack)
        p.fastest_slack_auto = 1
        print(f"feedback: slack {slack / 1.e3:.3f} us from the measured required slack "
              f"(was {slack_now / 1.e3:.3f} us): {ft.required_slack_basis(m, p)}")

    def fastest_finish(self):
        """After Base.finish_prepare: the params are final. Fold the constants the loop reads
        every step, and the trace geometry."""
        if self.fast_loop != 1:
            return
        p = self.p
        self.hc_min_lead_mu = int64(MIN_LEAD_MU)
        self.hc_N_pulses = int(p.N_pulses)
        self.hc_n_initial = int(p.n_initial_shots_before_remesh)
        self.hc_t_raman_set_pretrigger_mu = int64(p.t_raman_set_pretrigger_mu)
        self.hc_t_calculation_slack_compensation_mu = int64(p.t_calculation_slack_compensation_mu)
        self.hc_t_img_pulse = float(p.t_img_pulse)
        self.hc_t_fifo_mu = int64(p.t_fifo_mu)
        self.hc_t_io_update_pretrigger_mu = int64(p.t_io_update_pretrigger_mu)
        self.hc_t_ffu_dds_pipeline_latency = int64(p.t_ffu_dds_pipeline_latency)
        self.hc_t_ffu_pipeline_latency_fudge_mu = int64(p.t_ffu_pipeline_latency_fudge_mu)
        self.hc_lean = int(p.fastest_posterior)
        # the lean posterior computes the std only when something uses it: the remesh (any scanned
        # value on) or update_rabi_frequency (a loop argument, checked in lean_weigh)
        self.hc_lean_need_std = int(bool(np.any(np.ravel(p.feedback_remesh_threshold_Omega) > 0.)))
        # step 0's gap only: the bench rungs all ran with it (README "Structure of one step")
        self.hc_first_gap_extra_mu = int64(p.fastest_first_gap_extra_mu)
        # the gap is (gap_fixed + pulse) & ~7 (compute_t_between_pulses_mu); the read starts
        # fast_G before the next pulse start, so the chained pulse-on lands on it exactly and the
        # read starts 1-15 ns after this pulse's end (8 ns aligned: the IO_UPDATE in the chained
        # trace then lands where the unchained one would)
        gap_fixed = (int(p.t_calculation_slack_compensation_mu) + int(p.t_raman_set_pretrigger_mu)
                     + int(np.int64(float(p.t_img_pulse) * 1.e9)) + int(p.t_fifo_mu))
        self.fast_G_mu = int64((gap_fixed & ~7) - 8)
        if int(self.fast_G_mu) <= 0:
            raise ValueError(f"fastest loop: fixed gap {gap_fixed} ns too short for the chained read")
        self.t_read_trace_mu = int64(0)
        self.stage_seq = 0
        self.write_seq = 0
        self.hot_gain = 0
        self.hot_dt0 = int64(0)
        self.hot_dt1 = int64(0)
        self.kernel_invariants = set(getattr(self, "kernel_invariants", set())) | {
            "fast_G_mu", "hc_min_lead_mu", "hc_N_pulses", "hc_n_initial",
            "hc_t_raman_set_pretrigger_mu", "hc_t_calculation_slack_compensation_mu",
            "hc_t_img_pulse", "hc_t_fifo_mu", "hc_t_io_update_pretrigger_mu",
            "hc_t_ffu_dds_pipeline_latency", "hc_t_ffu_pipeline_latency_fudge_mu",
            "hc_lean", "hc_lean_need_std", "hc_first_gap_extra_mu"}

    # ---- kernel: per shot and cleanup (picked on the host by fastest_choose) ------------------

    @kernel
    def fastest_nothing(self):
        pass

    @kernel
    def fastest_shot_setup(self):
        """Top of scan_kernel: record the read traces in the first shot of the run."""
        if self._fastest_traces_recorded == 0:
            self.fastest_record_traces()

    @kernel
    def fastest_cleanup(self):
        """From cleanup_scan_kernel and cleanup_abort_kernel: a shot that ended inside the loop
        left the ADC on the 16-bit transfer, which every other read would misdecode."""
        self.core.break_realtime()
        self.set_adc_transfer_bits(32)

    # ---- kernel: the hot write path (bench_fastest_t23_guarded.py, unchanged) ----------------

    @kernel
    def hot_stage(self):
        self.stage_seq += 1
        r = self.raman
        rtio_output(r._fw_cfg_target, r._fw_cfg8)
        delay_mu(r._fw_ref_mu)
        rtio_output(r._fw_data_target, r._fw_addr)
        delay_mu(r._fw_xfer8_mu)
        rtio_output(r._fw_cfg_target, r._fw_cfg32)
        delay_mu(r._fw_ref_mu)

    @kernel(flags={"fast-math"})
    def hot_write(self, f):
        if self.stage_seq != self.write_seq + 1:
            raise ValueError("fastest loop: DDS staging and frequency write out of order")
        self.write_seq = self.stage_seq
        r = self.raman
        ftw = r._fw_ref_ftw + int32(round(r._fw_ftw_per_delta * (f - r._ao_ref_delta)))
        r.frequency_transition = f
        r.dds0._last_ftw = r.dds0._ftw
        r.dds1._last_ftw = r.dds1._ftw
        if r._ao_uses0 == 1:
            r._new_ftw0 = ftw
            r._new_ftw1 = r.dds1._ftw
        else:
            r._new_ftw0 = r.dds0._ftw
            r._new_ftw1 = ftw
        rtio_output(r._fw_data_target, ftw)

    @kernel
    def hot_update(self, t_step, dT, chained) -> TFloat:
        # RamanBeamPair.io_update_and_phase_update: the same event and the same integers
        r = self.raman
        T = self.hc_t_io_update_pretrigger_mu
        dt0 = self.hot_dt0
        dt1 = self.hot_dt1
        if chained == 0:
            # chained: the previous step's trace carries this event
            at_mu((t_step - T - self.hc_t_ffu_dds_pipeline_latency) & ~7)
            if r._ao_uses0 == 1:
                delay_mu(dt0)
            else:
                delay_mu(dt1)
            rtio_output(r._fw_io_target, 1)
            delay_mu(int64(8))
            rtio_output(r._fw_io_target, 0)
        r.dds0._ftw = r._new_ftw0
        r.dds1._ftw = r._new_ftw1
        dt0 += int64(4)
        dt1 += int64(4)
        dt = self.hc_t_ffu_pipeline_latency_fudge_mu
        spmu = r._sysclk_per_mu
        r._phi0_mu += r.dds0._last_ftw * (dT - T + dt0 + dt) * spmu >> 16
        r._phi0_mu += r.dds0._ftw * (T - dt0 - dt) * spmu >> 16
        r._phi1_mu += r.dds1._last_ftw * (dT - T + dt1 + dt) * spmu >> 16
        r._phi1_mu += r.dds1._ftw * (T - dt1 - dt) * spmu >> 16
        a0 = r.dds0.aom_order
        a1 = r.dds1.aom_order
        return r.pow_to_phase(2*np.int32(a0*r._phi0_mu - a1*r._phi1_mu))

    # ---- kernel: the read traces --------------------------------------------------------------

    @kernel
    def fastest_read_events(self):
        """The read as readout_pulse + readout_prepare_sample + the ADC submit, the DDS staging
        last (it only has to precede the next frequency write)."""
        sampler = self.integrator.sampler_ch.sampler_device
        t_r0 = now_mu()
        self.integrator.begin_integrate(reset=False)
        self.imaging.dds_sw.on()
        delay(self.p.t_img_pulse)
        self.imaging.dds_sw.off()
        self.integrator.stop_and_settle()
        t0 = now_mu()
        self.t_read_trace_mu = t0 - t_r0
        at_mu(t0 + 80)
        self.integrator.clear(t=0)
        at_mu(t0)
        sampler.cnv.pulse(30.e-9)
        delay(450.e-9)
        sampler.bus_adc.write(0)
        self.hot_stage()

    @kernel
    def fastest_record_traces(self):
        """Both read traces, once per run, at the top of the first shot (so the slack in hand is a
        shot's, not a step's)."""
        self.core.break_realtime()
        with self.core_dma.record(TRACE_READ):
            self.fastest_read_events()
        self.core.break_realtime()
        delay(1.e-3)
        r = self.raman
        G = self.fast_G_mu
        t_io = (G - self.hc_t_io_update_pretrigger_mu - self.hc_t_ffu_dds_pipeline_latency) & ~7
        if r._ao_uses0 == 1:
            t_io += int64(r.dds0.dds_device.sync_data.io_update_delay)
        else:
            t_io += int64(r.dds1.dds_device.sync_data.io_update_delay)
        with self.core_dma.record(TRACE_CHAIN):
            t_r0 = now_mu()
            self.fastest_read_events()
            at_mu(t_r0 + t_io)
            rtio_output(r._fw_io_target, 1)
            delay_mu(int64(8))
            rtio_output(r._fw_io_target, 0)
            at_mu(t_r0 + G)
            r.dds_sw.dds_device.sw.on()
        self.core.break_realtime()
        delay(10.e-3)
        self._fastest_traces_recorded = 1

    @kernel
    def set_adc_transfer_bits(self, n):
        """The Sampler ADC SPI transfer length: 16 (channel 7 only, the fastest loop) or 32 (both
        channels, what every other read expects). At the cursor; 10 us after it."""
        sd = self.integrator.sampler_ch.sampler_device
        sd.bus_adc.set_config_mu(SPI_CONFIG | spi.SPI_INPUT | spi.SPI_END, n, sd.div, SPI_CS_ADC)
        delay(10.e-6)

    @kernel
    def measurement_fastest(self, i, t, phase_tracker, t_read, chain, h_read, h_chain):
        """The read of step i: play its trace at t_read (the chained one also starts the next
        pulse), run the measurement-independent posterior half while the ADC converts, then
        the blocking 16-bit read, decoded as Sampler_Last_CH.sample_single does channel 7."""
        sampler = self.integrator.sampler_ch.sampler_device
        at_mu(t_read)
        if chain == 1:
            self.core_dma.playback_handle(h_chain)
        else:
            self.core_dma.playback_handle(h_read)
        self.stage_seq += 1

        # hc_lean is a kernel invariant: the compiler keeps one branch
        if self.hc_lean == 1:
            self.lean_propagate(t, phase_tracker)
        else:
            self.propagate_hypotheses(t, phase_tracker)

        val = sampler.bus_adc.read() & 0xffff
        if val & 0x8000:
            val -= 0x10000
        self.data.apd.shot_data[i] = adc_mu_to_volt(val, self.hot_gain, sampler.corrected_fs)
        return self.convert_measurement(self.data.apd.shot_data[i])

    # ---- kernel: the loop -----------------------------------------------------------------

    @kernel
    def feedback_loop_fastest(self, t_start_mu,
                              update_raman_frequency=0,
                              update_rabi_frequency=0,
                              include_photon_noise=1):
        self.omega_z_lightshift = 2 * np.pi * self.p.frequency_lightshift

        t_start_mu = t_start_mu & ~7
        t_step = t_start_mu

        h_read = self.core_dma.get_handle(TRACE_READ)
        h_chain = self.core_dma.get_handle(TRACE_CHAIN)
        # the trace switches the imaging light directly: the SLM settle check imaging.pulse does
        self.imaging.light_guard.ensure_mask_settled()
        sd = self.integrator.sampler_ch.sampler_device
        ch = (self.integrator.sampler_ch.ch - 6) + 8 - len(self.integrator.sampler_ch.samples)
        self.hot_gain = (sd.gains >> ch * 2) & 0b11
        self.hot_dt0 = int64(self.raman.dds0.dds_device.sync_data.io_update_delay)
        self.hot_dt1 = int64(self.raman.dds1.dds_device.sync_data.io_update_delay)

        at_mu((t_start_mu - 15000) & ~7)
        self.set_adc_transfer_bits(16)

        at_mu((t_start_mu - 10000) & ~7)
        f = self.omega_raman / (2*np.pi)
        self.raman.set_frequency_fast(f)
        self.raman.stage_ffua()
        self.stage_seq = 1
        self.write_seq = 0
        phase_tracker = 0.

        dT = self.p.t_between_pulses_mu
        # the explicit offset: t_raman_pulse - t_raman_pulse_ideal is wrong when t_raman_pulse is scanned
        t_turn_on_delay = self.p.t_raman_pulse_offset
        issued = 0     # 1: the previous step's trace started this step's pulse

        at_mu(t_start_mu)

        for i in range(self.hc_N_pulses):

            self.per_feedback_loop_top(idx=i)
            f = self.omega_raman / (2*np.pi)

            t_pulse = self.p.t_raman_pulse_list[i]
            self.t_raman_pulse_current = t_pulse
            self.t_raman_pulse_ideal_current = t_pulse - t_turn_on_delay

            at_mu(t_step - self.hc_t_raman_set_pretrigger_mu)
            if now_mu() - self.core.get_rtio_counter_mu() < self.hc_min_lead_mu:
                raise RTIOUnderflow("fastest loop deadline guard: the frequency word would be late")
            self.hot_write(f)

            t = (t_step - t_start_mu)*1.e-9

            phase_tracker = self.hot_update(t_step, dT, issued)

            at_mu(t_step)
            if issued == 1:
                delay(t_pulse)
                self.raman.dds_sw.dds_device.sw.off()
            else:
                self.raman.pulse(t_pulse)

            # records while the read is in flight
            self.data.omega_raman.put_data(self.omega_raman, i)
            self.data.t.put_data(t + t_pulse + self.hc_t_img_pulse, i)

            # the gap after this pulse depends only on its (pre-drawn) length
            dT = self.compute_t_between_pulses_mu(
                t_calculation_slack_compensation_mu=self.hc_t_calculation_slack_compensation_mu,
                t_raman_pulse=t_pulse,
                t_img_pulse=self.hc_t_img_pulse,
                t_raman_pretrigger=self.hc_t_raman_set_pretrigger_mu,
                t_fifo_mu=self.hc_t_fifo_mu)

            # the chained trace starts the next pulse a fixed fast_G after the read starts, so a
            # gap stretched beyond dT cannot chain: step 0 with the first-gap stretch plays the plain
            # read right after its pulse, and step 1 writes its own IO_UPDATE and pulse-on (as every
            # bench rung ran: a non-zero schedule entry was never pre-issued)
            stretch = int64(0)
            if i == 0:
                stretch = self.hc_first_gap_extra_mu
            chain = 0
            if i + 1 < self.hc_N_pulses and stretch == 0:
                chain = 1
            k = self.measurement_fastest(i, t, phase_tracker, t_step + dT - self.fast_G_mu,
                                         chain, h_read, h_chain)
            issued = chain
            if self.hc_lean == 1:
                self.omega_raman, omega_posterior_mean, self.Omega = self.lean_weigh(
                    k, update_raman_frequency=update_raman_frequency,
                    update_rabi_frequency=update_rabi_frequency,
                    include_photon_noise=include_photon_noise)
            else:
                self.omega_raman, omega_posterior_mean, self.Omega = self.weigh_hypotheses(
                    k, update_raman_frequency=update_raman_frequency,
                    update_rabi_frequency=update_rabi_frequency,
                    include_photon_noise=include_photon_noise)
            if i > (self.hc_n_initial-1):
                self.maybe_remesh(self._posterior_std, omega_center=omega_posterior_mean)

            # model S_z of grid point zidx: exact resonance only with feedback_grid_shift = 0
            self.data.s_z.put_data(self.state_z[self.zidx], i)

            # the next step's hot_update integrates the phase over this dT: the stretch included
            dT += stretch
            t_step += dT

            self.per_feedback_loop_end(idx=i)

        # every read is in: back to the 32-bit transfer every other read expects
        at_mu(t_step)
        self.set_adc_transfer_bits(32)

        self.per_scan_kernel_end()
