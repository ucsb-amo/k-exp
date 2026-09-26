"""ExptParams for the OPX port of the Bayesian frequency-feedback loop.

Inherits every ARTIQ-side feedback parameter (expt_params_feedback.py) and
adds what the OPX sequence (kexp/experiments/opx_sequences/feedback.py)
needs on top: the APD readout calibration in OPX units, the fixed-point
representation limits, and the per-cycle timing budget.

Phase model: "reset" (design decision D4). Both Raman analog drives get
reset_if_phase applied at the align immediately before every pulse, so the
two-photon drive phase at pulse start is 0 and the posterior's hypothesis
term is -omega_j * t_i, with t_i the pulse start time from pulse 0.
CONSEQUENCE: between pulses the atom-drive phase advances by omega_0 * dt,
i.e. ~0.478 turns per 4 ns clock cycle (119.4639 MHz * 4 ns = 0.4779 turns),
so the pulse starts must be known exactly in clock cycles. Every per-step
interval is computed on the host from the drawn pulse-time list (as
ARTIQ's compute_t_between_pulses_mu does per step) and the OPX is held to
it with a per-step wait on the switch element; the actual start of every
pulse is recorded with a timestamp stream, the replay uses the actual
pulse times, and the finish hook recomputes the schedule from the saved
durations and prints any scheduled-vs-actual mismatch.

Write-back convention as everywhere in kexp: comment out the old value,
tag the new one with `#run, date`. Values marked PLACEHOLDER have not been
measured on the OPX path and the run that produces them is named next to
each.

*** NOT YET RUN ON HARDWARE. Prerequisites: M1 (handshake latency on a
scope), M2 (OPX-driven Rabi flop -> t_raman_pi_pulse re-measured at the OPX
drive amplitude), M3 (APD endpoints in OPX demod units + time_of_flight). ***
"""

from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams as ExptParamsFeedback


class ExptParams(ExptParamsFeedback):
    def __init__(self):
        super().__init__()

        ### APD readout calibration in OPX units (milestone M3)
        # The OPX integrates the APD over t_opx_integration_len and the run
        # file stores apd = demod2volts(apd_raw) = 4096 * raw / duration_ns
        # (kexp.control.opx.units). These endpoints are in THOSE volts: the
        # mean APD voltage over the window for the all-up (|1,-1>, the
        # prepared state, brighter) and all-down states.
        # PLACEHOLDER, to be calibrated (OPX M3): copied verbatim from the
        # ARTIQ integrator endpoints (run 78309, expt_params_feedback.py) so
        # the code runs. The ARTIQ integrator volts and the OPX mean volts
        # are different scales (and the OPX demod2volts factor-2 convention
        # is itself unverified), so these numbers are wrong on the OPX path
        # until the endpoint calibration is repeated through the OPX measure:
        # re-run calibrations/apd_voltage_vs_state_2.py with the OPX doing
        # the imaging pulses (sequence rabi_raman_apd or a 5-pulse variant),
        # then k-jam/analysis/artisinal/apd_pulse_analysis_measured_pi.ipynb.
        self.v_apd_all_up_opx = -0.12361    # V (OPX demod2volts) PLACEHOLDER, copied from 78309
        self.v_apd_all_down_opx = -0.19702  # V (OPX demod2volts) PLACEHOLDER, copied from 78309

        # Photon-fraction noise of one weak measurement. Only the RATIO
        # sigma/N enters the posterior (the Gaussian likelihood with the
        # fixed detector-noise sigma), so the OPX carries this single number
        # instead of n_photons_per_shot and std_n_photons_per_shot.
        # 212.75 / 1336.2 = 0.1592 (run 78309, "using down std"). To be
        # re-derived from the M3 endpoint calibration (shot-to-shot std of
        # the down-state mean voltage divided by the up-down range).
        self.std_photon_fraction_opx = self.std_n_photons_per_shot / self.n_photons_per_shot

        # Switch-path turn-on latency on the OPX path: the programmed 'pass'
        # play is this much longer than the coherent rotation it produces.
        # PLACEHOLDER: 127 ns is the ARTIQ DDS raman_switch path value
        # (t_raman_pulse_offset). The OPX gates the same switch AOM through
        # its digital output and the RF switch box, so it must be re-measured
        # (M2: the t_raman_pulse scan of apd_voltage_vs_state_2.py with the
        # OPX playing the pulse, fit the zero crossing of the flop).
        self.t_raman_pulse_offset_opx = 127.e-9  # s PLACEHOLDER (ARTIQ DDS path value)

        ### per-cycle timing (OPX clock, 4 ns)
        # Per-step hold on the Raman switch element after the imaging
        # exposure, covering the measurement readback and the posterior
        # update for one pulse (the OPX's measure blocks until the ADC
        # result exists, so the whole update runs inside this hold). The
        # cycle is deterministic as long as the OPX finishes inside it; if
        # it does not, the next pulse slips and the finish hook's slip
        # check (recomputed schedule vs the pulse timestamps) prints ***.
        # QOP simulator, 2026-09-25, m = 21, N_pulses = 6, budget collapsed
        # to 16 ns (scratchpad run_sim_3b.py; every interval identical):
        # the interval exceeds the scheduled statements by
        #   pass 2 (inv_sqrt, exp table, flat rule)   4875 cc = 19.5 us
        #   pass 3b, exact trig (sincos bits 0)       2043 cc =  8.2 us
        #   pass 3b, 12-bit sincos table (default)    1938 cc =  7.75 us
        #   pass 3b, 16 discrete durations            1074 cc =  4.3 us
        # (each includes the constant sync overhead below). The budget must
        # cover ~1850 cc beyond the scheduled hold for the default and ~1955
        # cc for exact trig: 10 us = 2500 cc leaves 35 % / 28 % margin for
        # hardware vs simulator. Check on hardware with the finish hook's
        # slip line before tightening further.
        # self.t_opx_feedback_compute_budget = 40.e-6   # spec value, first pass
        # self.t_opx_feedback_compute_budget = 25.e-6  #simulator, 2026-09-25 (pass 2 structure)
        self.t_opx_feedback_compute_budget = 10.e-6  #simulator, 2026-09-25 (pass 3b structure)
        # Constant per-cycle align/sync overhead (s), added to the schedule
        # per pulse: the extra cycles between two pulse-start timestamps
        # beyond d_i + edge + t_img + edge + budget + extra gap. Must be a
        # multiple of 4 ns. QOP simulator: 95 cycles with the first-pass
        # structure (2026-09-24, N_pulses = 3, m = 5); 91 cycles on every
        # one of 5 intervals with the pass-2 structure (2026-09-25,
        # N_pulses = 6, m = 21, budget 25 us, per-step wait array); 82
        # cycles on every one of 5 intervals with the pass-3b structure
        # (2026-09-25, N_pulses = 6, m = 21, budget 10 us, sincos table and
        # exact trig alike). The OPX's real-time posterior uses the SCHEDULED
        # pulse starts, so an error here is a phase error of 0.478 turns per
        # cycle per pulse in the hypothesis tables (the replay uses the
        # timestamps and is unaffected). The pulse timestamps keep checking
        # it every shot on hardware (the finish hook's slip line); re-measure
        # it whenever the loop structure changes.
        # self.t_opx_feedback_align_overhead = 0.   # until measured
        # self.t_opx_feedback_align_overhead = 380.e-9  #simulator, 2026-09-24
        # self.t_opx_feedback_align_overhead = 364.e-9  #simulator, 2026-09-25 (pass 2 structure)
        self.t_opx_feedback_align_overhead = 328.e-9  #simulator, 2026-09-25 (pass 3b structure)
        # The same constant for the discrete-duration structure
        # (t_raman_pulse_n_levels > 0), which has its own table reads at the
        # pulse boundary: 86 cycles on every one of 5 intervals (QOP
        # simulator, 2026-09-25, 16 levels, budget 10 us). The flat-rule
        # structure (feedback_flat_rule_bool = 1) has NOT been measured;
        # expect the slip line to fire until it is.
        self.t_opx_feedback_align_overhead_levels = 344.e-9  #simulator, 2026-09-25
        # Free-evolution knob, like ARTIQ's delta_t_mu: lengthens every
        # per-step interval by this much (s, multiple of 4 ns). Enters the
        # schedule and the hypothesis phase tables like everything else.
        self.t_feedback_extra_gap = 0.

        ### fixed-point representation of the posterior (QUA fixed = [-8, 8))
        # Log-weights are kept as L/s on the OPX with s = this scale, so the
        # per-point decrement -((p_meas - p1)/sigma_p)^2 / (2 s) needs NO
        # clamp: with p_meas clamped once per pulse to [-2, 3] and p1 in
        # [0, 1] it is >= -(3/sigma_p)^2/(2 s) = -5.55 for s = 32, and the
        # floor of the lazy max-normalisation sits at -8 - that = -2.45
        # (-78.5 nats; derived in the sequence, not a free parameter).
        # Against the unclamped double-precision posterior this agrees to
        # 8e-34 at nominal noise and 2e-8 at 4x noise, where the pass-2
        # L/4 + 7.9 sigma clamp changed 32 % of the decisions (brainstorm
        # l32_vs_exact.py). Saved with the run: the finish hook and the
        # replay derive P0 = exp(s L)/sum from it. Power of two.
        # self.feedback_log_weight_floor = -32.   # nats (pass 2, L/4 representation)
        # self.feedback_q_clamp = 7.9             # (pass 2, retired with L/32)
        self.feedback_log_weight_scale = 32  #simulator, 2026-09-25

        # Control law: 0 = the next drive is always the posterior argmax
        # (the OPX default: ARTIQ's flat rule never fired in 6000 synthetic
        # pulses of any model-consistent case, brainstorm flat_rule_check.py,
        # and dropping it removes the exp/sum/inv/dot pass); 1 = ARTIQ's
        # flat rule (drive the posterior mean when max P0 < 1.15/m), with
        # the mean snapped to the nearest grid index because the OPX drive
        # is a grid index. The replay/oracle mirror the flag.
        self.feedback_flat_rule_bool = 0

        # exp(L) on the OPX (flat rule ON only) from an interpolation table
        # with 2^bits nodes per unit of L/s (8: step 1/256, 2050 entries)
        # followed by log2(s) squarings, instead of Math.exp (60 vs 16
        # cycles per point on the QOP simulator, 2026-09-25). 0 = Math.exp.
        self.opx_exp_lut_bits = 8  #simulator, 2026-09-25

        # cos/sin of the per-point rotation angle from a sine table with
        # 2^bits nodes per turn (12: 5122 entries, <= 2.9e-7 on the trig
        # values, <= 2.3e-5 on P0) and linear interpolation instead of
        # Math.cos2pi + Math.sin2pi: 75 vs 82 cycles per grid point on the
        # QOP simulator (2026-09-25, brainstorm/hbench_run.py); end to end
        # 1938 vs 2043 cycles per pulse (7.75 vs 8.17 us), identical
        # decisions -- a small gain; 0 is a safe choice too. 0 = the Math
        # calls (exact). Ignored with t_raman_pulse_n_levels > 0 (no trig
        # then). Saved with the run so the replay emulates the same table.
        self.opx_sincos_lut_bits = 12  #simulator, 2026-09-25

        # Discrete pulse durations: 0 = the continuous uniform draw
        # (draw_t_raman_pulse_list, as ARTIQ); n >= 4 = every pulse drawn
        # from n durations equally spaced on [min, max] * t_pi
        # (draw_t_raman_pulse_list_levels), which lets the OPX take the
        # rotation matrix of every (level, hypothesis) from a table -- no
        # trig in the loop, 33 vs 75 cycles per grid point on the QOP
        # simulator. Physics: 2-3 levels alias measurably (+5-7 % wrong
        # grid point, 3 sigma); 4-16 levels within +0.6..+3 % of continuous
        # at 1000 seeds (<= 2 sigma, brainstorm b_alias_ongrid.py; a 10k-seed
        # run is owed before this is switched on for real). >= 8 recommended.
        self.t_raman_pulse_n_levels = 0

        ### forced / documented
        # Remesh is not ported (host/replay only, D7): the sequence refuses
        # to trace with a nonzero threshold.
        self.feedback_remesh_threshold_Omega = 0.
        # Phase model flag: 1 = "reset" model described in the module
        # docstring, the only implemented value. Kept numeric (no ExptParams
        # attribute is a string: the HDF5 params writer and the OPX per-shot
        # tables only handle numbers). The sequence refuses any other value.
        self.feedback_phase_model_reset = 1
