from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams as ExptParamsFeedback


class ExptParams(ExptParamsFeedback):
    """Params for the Rabi-frequency posterior pulse-train experiment.

    Subclasses the feedback params so every APD/lightshift/back-action
    calibration constant is inherited verbatim -- there is exactly one source of
    truth shared with the live feedback stack, and the host-side analysis
    (kexp.analysis.RabiPosterior) reads those same names off ad.p.

    The Raman transition frequency is assumed already correct here, so none of
    the frequency-grid / fast-frequency-update machinery is used: the drive sits
    on resonance for the whole pulse train.
    """

    def __init__(self):
        super().__init__()

        # Raman pulses, each followed by a measurement pulse. 20 is where the
        # single-shot design study saturates: measurement back-action
        # (back_action_coherence = 0.756) damps the transverse component each
        # cycle, so information stops accumulating. Worst-case single-shot
        # posterior width over a 50-72 kHz prior, best window and seed:
        #
        #     N        8      10      12      15      20      25      30      40
        #     Hz    1224    1113    1036     976     938     909     901     901
        #
        # Past 20 you pay 35 us of tweezer hold per pulse for <5% width.
        self.N_pulses = 20

        # Nominal pulse: pi/2. s_z starts at +1, so a pi/2 pulse lands on the
        # equator where d(cos theta)/d theta is largest -- maximum sensitivity
        # to Omega. This is what the train uses when randomization is off, and
        # it is also what sets the turn-on delay below.
        self.t_raman_pulse = self.t_raman_pi_pulse / 2
        # Coherent rotation area is shorter than the programmed pulse by the
        # AOM/switch turn-on delay (127 ns, see expt_params_feedback.py). Only
        # the difference matters, so this stays scalar even when the pulse
        # times themselves are randomized.
        self.t_raman_pulse_offset = 127.e-9
        self.t_raman_pulse_ideal = self.t_raman_pulse - self.t_raman_pulse_offset

        ### randomized raman pulse times
        # Each pulse of each shot gets its own duration, drawn uniform in
        # [t_raman_pulse_min_frac_pi, t_raman_pulse_max_frac_pi] *
        # t_raman_pi_pulse by kexp.base.feedback.draw_t_raman_pulse_list -- the
        # same draw, from the same code, that the live feedback loop runs.
        #
        # The reason to randomize here is that this experiment exists to
        # calibrate Omega *for the feedback loop*, and the feedback loop drives
        # randomized pulse times. Measuring with a single fixed duration would
        # pin the answer to that one duration; anything that makes Omega
        # slightly duration-dependent (AOM turn-on transient, thermal or
        # pointing drift over a pulse) would then bias the calibration in a way
        # the feedback loop never sees. Drawing from the feedback window
        # instead averages Omega over exactly the durations it will be used at.
        #
        # CORRECTION to the note above: randomizing is NOT statistically
        # neutral, it is the single most important design choice here, and the
        # reason is aliasing rather than duration-averaging.
        #
        # A CONSTANT duration is far sharper locally -- 15 pulses at 0.95*t_pi
        # give a Cramer-Rao bound of 228 Hz against 763 Hz for the randomized
        # window -- but it is catastrophically multimodal. Every pulse then
        # accumulates the same theta, so hypotheses differing by a full extra
        # turn per pulse are indistinguishable. Scoring designs by the EXPECTED
        # POSTERIOR WIDTH over a wide 20-200 kHz prior, which charges for that
        # mass instead of ignoring it:
        #
        #     design            CRB      expected posterior width
        #     const 0.95 t_pi   228 Hz            61976 Hz
        #     const 3.00 t_pi   175 Hz            43367 Hz
        #     rand [0.5, 1.0]   763 Hz              781 Hz
        #
        # So: randomize, and choose the window for identifiability, not for
        # local sharpness.
        #
        # These bounds are now set HERE rather than inherited from
        # expt_params_feedback.py. The inheritance was deliberate -- it kept
        # Omega calibrated over the durations the feedback loop actually drives
        # -- so the trade is explicit: [0.6, 1.2] beats the feedback window
        # [0.5, 1.0] by 1.4x on worst-case single-shot width (659 vs 938 Hz at
        # N=20), at the cost of averaging Omega over a slightly wider spread
        # than the loop uses. If Omega ever turns out to be strongly
        # duration-dependent, revert to inheriting and take the width hit.
        self.t_raman_pulse_min_frac_pi = 0.6
        self.t_raman_pulse_max_frac_pi = 1.2

        self.t_raman_pulse_random_bool = 1
        # PINNED, not 0. With N_repeats = 1 there is no averaging over
        # schedules, so the one schedule you get is the whole experiment -- and
        # they are not equally good. Over 25 seeds at N=20 in [0.6, 1.2] the
        # worst-case width ranges 659-1800 Hz; seed 19 is the best of them.
        #
        # End-to-end Monte Carlo (60 noise realizations x 5 true frequencies,
        # full RabiPosterior on a 20-200 kHz grid):
        #
        #     [0.5,1.0] N=15 unpinned   RMSE 5609 Hz   4.3% of shots >5 kHz off
        #     [0.6,1.2] N=20 seed 19    RMSE  572 Hz   0.0%
        #
        # The RMSE gap is almost entirely those alias failures -- the median
        # error only moves 861 -> 317 Hz. A pinned good seed is what removes
        # them.
        #
        # CAVEAT: draw_t_raman_pulse_list scales the drawn times by
        # t_raman_pi_pulse, so this seed is optimal for the CURRENT t_pi
        # (8.6438 us). Re-run the seed search if t_pi moves much. Set back to 0
        # for a fresh schedule per shot when N_repeats > 1.
        self.t_raman_pulse_seed = 19

        ### alternating random / constant blocks
        # Random pulses break aliases; constant pulses accumulate rotation angle
        # and sharpen. Alternating gets both -- see
        # kexp.base.feedback.draw_t_raman_pulse_list_blocks for the full
        # argument and the measured table. RMSE at N_pulses = 20,
        # N_repeats = 20, full RabiPosterior on a 20-200 kHz grid:
        #
        #     all random                 117.1 Hz
        #     R6 -> C14   (1 block)       92.0 Hz
        #     R3 C7 R3 C7 (2 blocks)      73.5 Hz   <-- this
        #     R2 C3 x4    (4 blocks)      92.8 Hz
        #
        # 1.6x better than the pure random schedule, no catastrophic failures.
        #
        # ONLY SAFE WITH ENOUGH REPEATS. The constant blocks leave a residual
        # alias; at N_repeats = 1 every hybrid tested put 0.8-6.7% of shots more
        # than 5 kHz off, where the all-random schedule put 0%. Set
        # t_raman_pulse_block_bool = 0 whenever N_repeats drops below ~10 --
        # then the [0.6, 1.2] seed-19 random schedule above is the right design
        # (measured 0% failures, 504 Hz RMSE single-shot).
        self.t_raman_pulse_block_bool = 0
        self.t_raman_pulse_n_random_per_block = 3
        self.t_raman_pulse_n_const_per_block = 7
        # 3.0 * t_pi = 25.9 us per constant pulse, so the cycle stretches from
        # ~35 us to ~41 us and the 20-pulse train runs ~820 us -- still well
        # inside t_tweezer_hold.
        self.t_raman_pulse_const_frac_pi = 3.0

        # RTIO headroom inserted after each measurement pulse. Nothing is
        # computed on the kernel between pulses (unlike the feedback loop), so
        # this is pure slack rather than calculation-time compensation.
        self.t_pulse_gap = 10.e-6

        # Post-train diagnostic reads: [0] light leakage with the atoms
        # released, [1] detector dark level.
        self.N_reference_reads = 2

        self.N_repeats = 20

        self.t_tweezer_hold = 2.e-3
        self.t_tof = 800.e-6

        # self.t_raman_pi_pulse = 8.5742e-06 #76292, 2026-08-25
         # run 76292 | RabiJointPosterior, 2026-08-25
        # f_rabi = 58.3144 +/- 0.7609 kHz
        # self.frequency_lightshift                   = 3.6e+04   # Hz  at t_img_pulse = 5e-06 s
        # feedback_measurement_midpoint_fraction: pinned in this fit, not measured
        # self.back_action_coherence                  = 0.8048      # +/- 0.0392 (5%)
        # self.v_apd_all_up                           = -0.12201    # V   +/- 3.58 mV
        # self.v_apd_all_down                         = -0.20180    # V   +/- 3.23 mV
