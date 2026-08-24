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

        # 10 raman pulses, each followed by a measurement pulse.
        self.N_pulses = 10

        # Fixed pi/2 pulse for every pulse in the train. s_z starts at +1, so
        # the first pulse lands on the equator where d(cos theta)/d theta is
        # largest -- maximum sensitivity to Omega. Successive pulses accumulate
        # i*theta, which is what sharpens the posterior.
        self.t_raman_pulse = self.t_raman_pi_pulse / 2
        # Coherent rotation area is shorter than the programmed pulse by the
        # AOM/switch turn-on delay (127 ns, see expt_params_feedback.py).
        self.t_raman_pulse_ideal = self.t_raman_pulse - 127.e-9

        # Every pulse in the train is identical -- no per-shot randomization.
        self.t_raman_pulse_random_bool = 0

        # RTIO headroom inserted after each measurement pulse. Nothing is
        # computed on the kernel between pulses (unlike the feedback loop), so
        # this is pure slack rather than calculation-time compensation.
        self.t_pulse_gap = 10.e-6

        # Post-train diagnostic reads: [0] light leakage with the atoms
        # released, [1] detector dark level.
        self.N_reference_reads = 2

        self.N_repeats = 30

        self.t_tweezer_hold = 2.e-3
        self.t_tof = 800.e-6
