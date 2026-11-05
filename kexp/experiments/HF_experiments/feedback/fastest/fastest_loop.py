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

What is NOT carried over from the bench: the posterior numerics of the S2 kernel (std on demand, no
prefactor) -- the library posterior is kept so the loop is the standard loop's posterior exactly; the
spacing (the slack default is unchanged: T ~ 66.7 us at m = 21); the 2 us integrator settle (the
param default is unchanged). The bench floors (23.15 us at m 21) were measured with the S2 numerics.

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


class FastestLoop:
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
        if "fast_path" in {str(x.key) for x in getattr(self, "scan_xvars", ())}:
            raise ValueError("fast_path cannot be scanned: the loop is chosen once per run "
                             "(compare the loops in separate, interleaved runs)")
        want = int(np.ravel(getattr(p, "fast_path", FAST_PATH_FASTEST))[0])
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
        print(f"feedback: fastest loop (single-AO moves anchored at {f_ref:.0f} Hz, DMA read, "
              f"overlapped posterior, deadline guard)")

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
            "hc_t_ffu_dds_pipeline_latency", "hc_t_ffu_pipeline_latency_fudge_mu"}

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

            chain = 0
            if i + 1 < self.hc_N_pulses:
                chain = 1
            k = self.measurement_fastest(i, t, phase_tracker, t_step + dT - self.fast_G_mu,
                                         chain, h_read, h_chain)
            issued = chain
            self.omega_raman, omega_posterior_mean, self.Omega = self.weigh_hypotheses(
                k, update_raman_frequency=update_raman_frequency,
                update_rabi_frequency=update_rabi_frequency,
                include_photon_noise=include_photon_noise)
            if i > (self.hc_n_initial-1):
                self.maybe_remesh(self._posterior_std, omega_center=omega_posterior_mean)

            # model S_z of grid point zidx: exact resonance only with feedback_grid_shift = 0
            self.data.s_z.put_data(self.state_z[self.zidx], i)

            t_step += dT

            self.per_feedback_loop_end(idx=i)

        # every read is in: back to the 32-bit transfer every other read expects
        at_mu(t_step)
        self.set_adc_transfer_bits(32)

        self.per_scan_kernel_end()
