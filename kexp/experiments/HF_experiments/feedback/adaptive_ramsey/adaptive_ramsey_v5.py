"""Adaptive Ramsey test experiment, v5 (2026-10-30 ~10:4x; after the 90165 stall, organizer code-fd).

v5 = v4 + instrumentation of the shot's TAIL (90165 stalled in shot 5 AFTER "train done" and before the
shot-complete notice, silently; 90152 the same way): a lead check (timeline cursor minus the RTIO
counter) right after the train, after the hold, after abs_image, and before the end-of-shot
wait_until_mu, each aprinted as a "[adaptive Ramsey] tail <stage> lead <mu>" marker (async RPCs,
after the timing-critical part of the shot), and a "!!" line when any lead exceeds 50 ms. Nothing
in the sequence changes: a far-future cursor is reported, not corrected (correcting it would hide
where it came from). The per-stage markers put the next stall between two named lines.

v4 (adaptive_ramsey_v4.py, left as it was) was:

v4 = v3 with: the per-shot push of the ramsey_* containers moved from right after the train to the
END of scan_kernel (after abs_image, beside the existing wait_until_mu), so the hold, the shutter /
tweezer off, the TOF and the image are not delayed by a variable RPC; parameter sanity checks at
prepare (t_ramsey_gap_max in (0, 100 ms], t_ramsey_total_max in (0, 500 ms], t_ramsey_gap_min >= 0,
candidates finite and >= 1) so int64(t_ramsey_gap_max * 1e9) is always sane; and the base
kexp/base/adaptive_ramsey.py hardened (ramsey_wrap_phase without loops, non-finite -> 0;
ramsey_clip_gap_mu NaN / negative guards). Mid-shot RPC in scan_kernel: none between the first pulse
and abs_image except aprints (async).

v3 (adaptive_ramsey_v3.py, left as it was) was:

v3 = v2 + robustness and record-keeping, no change to the protocol or the posterior:
  * every gap is re-clamped at its point of use, t_step += min(max(dT, floor), cap), cap =
    t_ramsey_gap_max (never below the floor): a timestamp far in the future is impossible
    whatever the planner's arithmetic returns; a gap outside [floor, cap] is counted
    (data.ramsey_n_clamped per shot) and aprinted;
  * per-shot console markers (two async RPCs per shot, none per pulse): "shot start" with the
    shot counter and drive offset, "train done" with the train length -- so a stall shows where
    it sits;
  * the per-pulse posterior is recorded (data.probabilities row i+1 = after pulse i, row 0 = the
    prior; data.omega_raman_mesh row 0 = this shot's grid), as random_bayesian does;
  * the ramsey_* containers of the shot (t_gap, phase, Q, std, mean, set_margin, timing,
    n_clamped) are PUSHED to liveOD right after the train (push_shot_data from an RPC with the
    kernel's arrays), so an aborted or incomplete run keeps them (90152's file had them all 0:
    END_RUN containers are never written when a run is aborted).

v2 (adaptive_ramsey_v2.py, left as it was) = v1 + the phase-write timing margin:

right after
RamanBeamPair.set(frequency, relative_phase) the kernel records now_mu() - t_step per pulse
(data.ramsey_set_margin, s; NEGATIVE = the DDS write finished before the pulse time) and aprints a
warning when it is above -2 us. Budget for the write is t_ramsey_phase_set_pretrigger_mu (12 us);
if it overran, at_mu(t_step) would move the cursor back and the pulse would fire before the phase
took effect -- a silently wrong phase. Smoke pass = margin negative with room on every pulse and a
clean core log. The timing probe (data.ramsey_timing) covers posterior + plan only.

Original header:
Adaptive Ramsey test experiment (2026-10-30, DESIGN STAGE -- not yet run on hardware).

Single-shot frequency estimation with the feedback posterior (kexp.base.feedback.Feedback) where the
protocol, not the drive frequency, adapts: every pulse is pi/2, the drive stays at the initial
offset, and after every weak APD read the kernel chooses the NEXT gap (pulse-start period) and the
next pulse's two-photon phase from the posterior (kexp.base.adaptive_ramsey.ramsey_plan_next; the
default maximizes the posterior variance of the predicted S_z over the candidate gaps and the
phase). The posterior update is Feedback.generate_posterior unchanged; the estimate is the
posterior after the last read. See README.md beside this file and the simulator
kexp.analysis.adaptive_ramsey (policies, scoring, the phase-sign check).

Sequence (scan_kernel): FeedbackExpt's preparation (tweezers, SLM mask, APD imaging at the
midpoint detuning) -> prep_raman at the drive frequency in SYNCHRONIZED phase mode with the phase
origin at the start of the train (as check_twist / raman_ls_ramsey) -> feedback_loop ->
hold, tweezer off, TOF, abs_image (the APD stage is in: no frames) -> reset. No fast-frequency-
update staging: the drive never hops, the phase is set with RamanBeamPair.set(relative_phase)
t_ramsey_phase_set_pretrigger_mu before each pulse.

End state: as FeedbackExpt (raman shutter off, tweezer off in the shot; the scanner's cleanup resets
the coils on normal completion and on the RTIO handlers, and runs cleanup_abort_kernel -- the safe
state -- before any other exception goes on). The only new hardware action is the per-pulse DDS
phase register write.

Recorded per pulse (data.ramsey_*): the gap taken, the phase (model convention), the quality the
choice maximized, the posterior std and mean; per shot the measured kernel times of one posterior
update and one plan step against the slack. Plus FeedbackExpt's containers (apd, omega_raman,
t_raman_pulse, s_z, t, probabilities, omega_raman_mesh).

Run-only checks the first run must pass before any data is trusted (README.md 'first run'):
  1. data.ramsey_timing: t_posterior + t_plan + ~set() < slack - 15 us (else raise the slack);
  2. no RTIOUnderflow (save_on_underflow keeps what was taken);
  3. a PHASE_RANDOM run (ramsey_phase_policy = 3) scored with
     kexp.analysis.adaptive_ramsey.phase_sign_check: the sign of the programmed phase in the model
     is UNVERIFIED (ramsey_phase_sign); an adaptive run under the wrong sign picks the worst phase.
"""
from artiq.experiment import *
from artiq.language import now_mu, delay, at_mu, TFloat
from kexp import Base, img_types, cameras, aprint
from kexp.base import Feedback
from kexp.base.adaptive_ramsey import AdaptiveRamsey, draw_ramsey_phase_list, PHASE_RANDOM
from kexp.base.feedback import check_feedback_grid_params
import numpy as np
from numpy import int64

from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt
from kexp.experiments.HF_experiments.feedback.adaptive_ramsey.expt_params_adaptive_ramsey import ExptParams
from kexp.experiments.HF_experiments.feedback.adaptive_ramsey.data_vault_adaptive_ramsey import DataVault


class AdaptiveRamseyExptV5(FeedbackExpt, AdaptiveRamsey):

    def __init__(self, save_data=True, suppress_live_od=False, save_on_underflow=True,
                 warmup_shots=3, mot_preload=False):
        # FeedbackExpt.__init__ with this experiment's params and containers
        self.data = DataVault(self)
        self.p = ExptParams()
        Base.__init__(self,
                      save_data=save_data,
                      imaging_type=img_types.DISPERSIVE,
                      camera_select=cameras.apd,
                      expt_params=self.p,
                      data_vault=self.data,
                      suppress_live_od=suppress_live_od,
                      save_on_underflow=save_on_underflow,
                      warmup_shots=warmup_shots,
                      mot_preload=mot_preload)
        self.p.cal_enabled = 0          # no interleaved readout sub-scan in the design stage

    def finish_prepare(self, shuffle=True):
        p = self.p
        if int(p.update_raman_frequency_bool) or int(p.t_raman_pulse_random_bool) or int(p.preshot_contrast):
            raise ValueError("AdaptiveRamseyExpt: drive hops, random pulse durations and the pre-shot are "
                             "not part of this protocol (update_raman_frequency_bool, "
                             "t_raman_pulse_random_bool, preshot_contrast must be 0)")
        if not (0. < float(p.ramsey_pulse_area_pi) <= 1.):
            raise ValueError(f"ramsey_pulse_area_pi must be in (0, 1]; got {p.ramsey_pulse_area_pi}")
        if abs(float(p.ramsey_phase_sign)) != 1.:
            raise ValueError("ramsey_phase_sign must be +1 or -1")
        # v4: the gap bounds the kernel casts to mu must be sane (reviewer, 2026-10-30)
        gap_max, total_max, gap_min = float(p.t_ramsey_gap_max), float(p.t_ramsey_total_max), float(p.t_ramsey_gap_min)
        if not (0. < gap_max <= 0.1):
            raise ValueError(f"t_ramsey_gap_max must be in (0, 100 ms]; got {gap_max}")
        if not (0. < total_max <= 0.5):
            raise ValueError(f"t_ramsey_total_max must be in (0, 500 ms]; got {total_max}")
        if not (0. <= gap_min <= gap_max):
            raise ValueError(f"t_ramsey_gap_min must be in [0, t_ramsey_gap_max]; got {gap_min}")
        cands = np.asarray(p.ramsey_gap_candidates, dtype=float)
        if cands.size < 1 or not np.all(np.isfinite(cands)) or np.any(cands < 1.) or np.any(cands > 64.):
            raise ValueError(f"ramsey_gap_candidates must be finite multiples of the floor in [1, 64]; got {cands}")
        p.t_raman_pulse = float(p.ramsey_pulse_area_pi) * float(p.t_raman_pi_pulse) + float(p.t_raman_pulse_offset)
        p.t_raman_pulse_ideal = p.t_raman_pulse - float(p.t_raman_pulse_offset)
        p.ramsey_gap_candidates = np.asarray(p.ramsey_gap_candidates, dtype=float)
        # the PHASE_RANDOM list: drawn per shot in scan_kernel; a draw here fixes the array's shape
        p.ramsey_phase_list = draw_ramsey_phase_list(1, int(p.N_pulses))
        self.data.adaptive_ramsey_containers(p)
        # v2: per pulse, now_mu() - t_step right after the phase write (s; negative = in time)
        self.data.ramsey_set_margin = self.data.add_data_container(int(p.N_pulses))
        # v3: how many gaps the use-site clamp had to correct this shot (0 = the planner's
        # values were all inside [floor, cap])
        self.data.ramsey_n_clamped = self.data.add_data_container(1)
        self._ramsey_shot_counter = 0
        super().finish_prepare(shuffle=shuffle)
        print(f"adaptive Ramsey: gap floor {self.p.t_between_pulses_mu / 1.e3:.1f} us "
              f"(first fringe {1.e6 / self.p.t_between_pulses_mu:.1f} kHz; prior span "
              f"{self.p.frequency_feedback_grid_full_span / 1.e3:.1f} kHz), candidates "
              f"x{np.array2string(p.ramsey_gap_candidates, precision=1)}, phase policy "
              f"{int(p.ramsey_phase_policy)}, gap policy {int(p.ramsey_gap_policy)}, phase sign "
              f"{p.ramsey_phase_sign:+.0f} (unverified)")

    @rpc
    def get_new_ramsey_phase_list(self) -> TArray(TFloat):
        seed = int(self.p.ramsey_phase_seed)
        if seed == 0:
            seed = int(np.random.SeedSequence().entropy % (2 ** 31 - 1)) or 1
        self.p.ramsey_phase_list = draw_ramsey_phase_list(seed, int(self.p.N_pulses))
        return self.p.ramsey_phase_list

    @rpc
    def push_ramsey_shot(self, t_gap, phase, q, std, mean, set_margin, timing, n_clamped):
        """v3: this shot's ramsey_* values into the run's file now (Expt.push_shot_data: at the
        shot's final slot; never raises; falls back to END_RUN if liveOD refuses). Called from the
        kernel right after the train with the kernel's arrays, so an aborted run keeps them."""
        d = self.data
        self.push_shot_data([
            (d.ramsey_t_gap, np.asarray(t_gap, dtype=float)),
            (d.ramsey_phase, np.asarray(phase, dtype=float)),
            (d.ramsey_Q, np.asarray(q, dtype=float)),
            (d.ramsey_std, np.asarray(std, dtype=float)),
            (d.ramsey_mean, np.asarray(mean, dtype=float)),
            (d.ramsey_set_margin, np.asarray(set_margin, dtype=float)),
            (d.ramsey_timing, np.asarray(timing, dtype=float)),
            (d.ramsey_n_clamped, np.asarray([float(n_clamped)], dtype=float)),
        ])

    @kernel
    def ramsey_tail_mark(self, stage):
        """v5: how far the timeline cursor is ahead of real time here (mu), as a console marker;
        loud above 50 ms. Async RPCs only; no timeline movement."""
        lead_mu = now_mu() - self.core.get_rtio_counter_mu()
        aprint("[adaptive Ramsey] tail", stage, "lead", lead_mu)
        if lead_mu > 50000000:
            aprint("!! adaptive Ramsey: cursor", lead_mu, "mu ahead of real time at tail stage", stage)

    @kernel
    def initialize_feedback(self):
        """Feedback.initialize_feedback, then time one plan step the same way and record both
        against the slack (data.ramsey_timing, every shot)."""
        Feedback.initialize_feedback(self)
        t_floor_mu = self.p.t_between_pulses_mu
        t0 = self.core.get_rtio_counter_mu()
        self.core.wait_until_mu(t0)
        (dT_mu, theta, q) = self.ramsey_plan_next(1, 1.0e-6, 0.0, self.omega_raman, self.omega_raman,
                                                  float(self.p.t_io_update_pretrigger_mu) * 1.0e-9,
                                                  t_floor_mu)
        t_plan_mu = abs(t0 - self.core.get_rtio_counter_mu())
        self.core.break_realtime()
        self.data.ramsey_timing.put_data(float(self.t_posterior_mu), 0)
        self.data.ramsey_timing.put_data(float(t_plan_mu), 1)
        self.data.ramsey_timing.put_data(float(self.p.t_calculation_slack_compensation_mu), 2)
        if self.t_posterior_mu + t_plan_mu + 15000 > self.p.t_calculation_slack_compensation_mu:
            aprint("!! adaptive Ramsey: posterior + plan time", self.t_posterior_mu + t_plan_mu,
                   "mu leaves < 15 us of the slack", self.p.t_calculation_slack_compensation_mu,
                   "mu for set(relative_phase): expect underflows; raise t_calculation_slack_compensation_mu")
        # the plan above moved the posterior's bookkeeping; the shot starts clean
        self.reset_feedback_state()
        self._initialize_frequency_grid()

    @kernel
    def scan_kernel(self):
        self.core.wait_until_mu(now_mu())
        self.p.ramsey_phase_list = self.get_new_ramsey_phase_list()
        self.p.t_raman_pulse_list = self.get_new_t_raman_pulse_list(seed=1)   # constant list
        self.data.t_raman_pulse_seed.put_data(0.)
        self.data.t_raman_pulse.put_data_1d(self.p.t_raman_pulse_list)
        self._ramsey_shot_counter += 1
        aprint("[adaptive Ramsey] shot start", self._ramsey_shot_counter, "offset u",
               self.p.feedback_fractional_initial_offset)
        self.core.break_realtime()

        self.integrator.init()
        self.initialize_feedback()
        delay(10.e-3)

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        if self.p.slm_mask_every_shot:
            self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask, dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=False)

        # the drive at the initial offset, synchronized phase mode: the two-photon phase at time t
        # is relative_phase + omega_d (t - origin); the origin is set right before the train
        self.prep_raman(frequency_transition=self.omega_raman / (2 * np.pi), phase_mode=1)

        t_pulse_start_mu = now_mu() + 500000
        at_mu(t_pulse_start_mu - 40000)
        self.raman.set(t_phase_origin_mu=now_mu())
        at_mu(t_pulse_start_mu - 20000)
        self.ttl.pd_scope_trig3.pulse(1.e-6)

        self.feedback_loop(t_start_mu=t_pulse_start_mu,
                           update_raman_frequency=0,
                           update_rabi_frequency=0,
                           include_photon_noise=self.p.include_photon_noise)
        self.ramsey_tail_mark(1)      # after the train

        delay(self.p.t_tweezer_hold)
        self.ttl.raman_shutter.off()
        self.ramsey_tail_mark(2)      # after the hold

        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()
        self.ramsey_tail_mark(3)      # after abs_image, before the end-of-shot wait

        self.core.wait_until_mu(now_mu())
        aprint("[adaptive Ramsey] tail 4 wait done")
        # v4: this shot's ramsey_* values into the file (RPC; nothing of the sequence follows it)
        self.push_ramsey_shot(self.data.ramsey_t_gap.shot_data, self.data.ramsey_phase.shot_data,
                              self.data.ramsey_Q.shot_data, self.data.ramsey_std.shot_data,
                              self.data.ramsey_mean.shot_data, self.data.ramsey_set_margin.shot_data,
                              self.data.ramsey_timing.shot_data, self.data.ramsey_n_clamped.shot_data[0])
        self.reset_initial_omega_from_params()
        self.core.break_realtime()
        delay(30.e-3)

    @kernel
    def feedback_loop(self, t_start_mu, update_raman_frequency=0, update_rabi_frequency=0,
                      include_photon_noise=1):
        """The adaptive Ramsey train. Timeline per step i (t_step = pulse i start):
        set(relative_phase) at t_step - pretrigger; pulse (pi/2) at t_step; read; posterior;
        plan (gap, phase) for i+1; t_step += gap (never below the production gap formula with the
        phase-set pretrigger). The drive frequency never changes; phi_dds(t) = omega_d t."""
        self.omega_z_lightshift = 2 * np.pi * self.p.frequency_lightshift

        t_start_mu = t_start_mu & ~7
        t_step = t_start_mu
        omega_d = self.omega_raman
        f_d = omega_d / (2 * np.pi)
        sign = self.p.ramsey_phase_sign
        t_pulse = self.p.t_raman_pulse
        t_turn_on_delay = self.p.t_raman_pulse_offset
        t_pre = float(self.p.t_io_update_pretrigger_mu) * 1.0e-9
        t_floor_mu = self.compute_t_between_pulses_mu(
            t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
            t_raman_pulse=t_pulse,
            t_img_pulse=self.p.t_img_pulse,
            t_raman_pretrigger=self.p.t_ramsey_phase_set_pretrigger_mu,
            t_fifo_mu=self.p.t_fifo_mu)

        theta = 0.0
        if self.p.ramsey_phase_policy == PHASE_RANDOM:
            theta = self.p.ramsey_phase_list[0]
        q = 0.0
        dT_mu = t_floor_mu
        # v3: the use-site cap on every gap (never below the floor)
        t_cap_mu = int64(self.p.t_ramsey_gap_max * 1.e9) & ~7
        if t_cap_mu < t_floor_mu:
            t_cap_mu = t_floor_mu
        n_clamped = 0
        self.data.omega_raman_mesh.put_data_1d(self.omega_guess_list, 0)
        self.data.probabilities.put_data_1d(self.P0, 0)

        for i in range(self.p.N_pulses):
            self.per_feedback_loop_top(idx=i)
            self.t_raman_pulse_current = t_pulse
            self.t_raman_pulse_ideal_current = t_pulse - t_turn_on_delay
            self.data.omega_raman.put_data(omega_d, i)
            self.data.ramsey_phase.put_data(theta, i)
            self.data.ramsey_Q.put_data(q, i)

            t = (t_step - t_start_mu) * 1.e-9
            phi_dds = omega_d * t

            # v3: how far ahead of real time this pulse is placed; a far-future timestamp would
            # make the blocking APD read wait that long in wall time (the 90152 stall's signature)
            lead_mu = t_step - self.core.get_rtio_counter_mu()
            if lead_mu > 50000000:
                aprint("!! adaptive Ramsey: pulse", i, "placed", lead_mu, "mu ahead of real time (> 50 ms)")
            # this pulse's phase register, then the pulse and the read
            at_mu(t_step - self.p.t_ramsey_phase_set_pretrigger_mu)
            self.raman.set(frequency_transition=f_d, relative_phase=self.ramsey_wrap_phase(sign * theta))
            # v2: did the write finish before the pulse time? (cursor after set() minus t_step)
            set_margin_mu = now_mu() - t_step
            self.data.ramsey_set_margin.put_data(float(set_margin_mu) * 1.e-9, i)
            if set_margin_mu > -2000:
                aprint("!! adaptive Ramsey: phase write ended", set_margin_mu,
                       "mu relative to the pulse time (pulse", i, "): phase not guaranteed")
            at_mu(t_step)
            self.raman.pulse(t_pulse)
            k = self.ramsey_read(i)

            (omega_out, omega_mean, omega_std) = self.generate_posterior(
                k, t, phase_raman_pulse_start=sign * theta + phi_dds,
                update_raman_frequency=0, update_rabi_frequency=0,
                include_photon_noise=include_photon_noise)
            self.data.ramsey_std.put_data(self._posterior_std, i)
            self.data.ramsey_mean.put_data(omega_mean, i)

            # the plan for pulse i+1 (also after the last pulse: recorded, not taken)
            (dT_mu, theta, q) = self.ramsey_plan_next(i + 1, t, phi_dds, omega_d, omega_d, t_pre, t_floor_mu)
            # v3: clamp at the point of use; count and say when the planner was outside
            if dT_mu < t_floor_mu or dT_mu > t_cap_mu:
                n_clamped += 1
                aprint("!! adaptive Ramsey: planned gap", dT_mu, "mu outside [floor, cap] = [",
                       t_floor_mu, ",", t_cap_mu, "] after pulse", i, "-- clamped")
                if dT_mu < t_floor_mu:
                    dT_mu = t_floor_mu
                else:
                    dT_mu = t_cap_mu
            self.data.ramsey_t_gap.put_data(float(dT_mu) * 1.e-9, i)
            self.data.probabilities.put_data_1d(self.P0, i + 1)

            self.data.t.put_data(t + t_pulse + self.p.t_img_pulse, i)
            self.data.s_z.put_data(self.state_z[self.zidx], i)

            t_step += dT_mu
            self.per_feedback_loop_end(idx=i)

        self.data.ramsey_n_clamped.put_data(float(n_clamped), 0)
        aprint("[adaptive Ramsey] train done, length", (t_step - t_start_mu) * 1.e-9, "s, clamped", n_clamped)
        self.per_scan_kernel_end()

    @kernel
    def ramsey_read(self, i):
        """FeedbackExpt.measurement without the fast-frequency-update staging: integrator window,
        imaging pulse, settle, sample (blocking), clear."""
        T_CONV_MU = 80
        self.integrator.begin_integrate(reset=False)
        self.imaging.pulse(self.p.t_img_pulse)
        self.integrator.stop_and_settle()
        t0 = now_mu()
        at_mu(t0 + T_CONV_MU)
        self.integrator.clear(t=0)
        at_mu(t0)
        self.data.apd.shot_data[i] = self.integrator.sample()
        return self.convert_measurement(self.data.apd.shot_data[i])


class adaptive_ramsey_v5(EnvExperiment, AdaptiveRamseyExptV5):
    """The test run: 7 drive offsets x N_repeats, the default (max-variance) policy.
    First run: run-only (/test-experiment), check data.ramsey_timing and underflows; then a
    PHASE_RANDOM run for the phase-sign check before any adaptive run is scored."""

    def prepare(self):
        AdaptiveRamseyExptV5.__init__(self, save_data=True, save_on_underflow=True)

        self.p.N_pulses = 12
        self.p.N_repeats = 3
        # drive offsets as fractions of the largest allowed (the night's 7-offset set)
        self.xvar('feedback_fractional_initial_offset', np.linspace(-0.95, 0.95, 7))
        # self.p.ramsey_phase_policy = PHASE_RANDOM     # the phase-sign check run

        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        self.end(os.path.abspath(__file__))
