import numpy as np

from kexp.experiments.HF_experiments.feedback.calibrations.rabi_posterior.expt_params_rabi_posterior \
    import ExptParams as ExptParamsRabiPosterior


class ExptParams(ExptParamsRabiPosterior):
    """Params for the joint APD / Bloch calibration pulse train.

    Subclasses the rabi-posterior params, so every APD and lightshift constant
    still comes from expt_params_feedback.py -- this experiment MEASURES those
    constants, and the inherited values are the starting point the host-side
    posterior grids around, not an input to the answer.

    The one thing this changes is the pulse schedule, and it changes it in the
    opposite direction from rabi_posterior_pulse_train. That experiment
    randomizes every pulse duration on purpose, so that Omega is measured over
    the same spread of durations the feedback loop actually drives. That is the
    right call there and the wrong one here, because randomizing costs this fit
    a lot of resolving power. Simulated round trips at 30 shots x 15 pulses,
    quoting the seed-to-seed scatter of the posterior mean:

        pulse schedule                        f_rabi   midpoint   v_down
        randomized in [1/4, 3/4]*t_pi         581 Hz     0.040    3.1 mV
        randomized in [0.15, 1.9]*t_pi        317 Hz     0.040    5.0 mV
        fixed per shot, scanned [0.15, 1.9]    80 Hz     0.036    0.9 mV

    Two effects compound. Holding the duration FIXED within a shot makes the
    accumulated rotation exactly i*theta at pulse i, so sensitivity to Omega
    builds coherently along the train instead of random-walking. And a WIDE
    duration range sweeps s_z across the whole [-1, +1] interval, so v_up and
    v_down -- which live at s_z = +/-1 -- are interpolated rather than
    extrapolated off the end of the sampled range.
    """

    def __init__(self):
        super().__init__()

        # Constant duration within a shot; the duration itself is scanned by
        # the experiment. This turns get_new_t_raman_pulse_list into a constant
        # list at the scanned p.t_raman_pulse, which is exactly what is wanted.
        self.t_raman_pulse_random_bool = 0

        # Durations to scan, as fractions of t_raman_pi_pulse. Chosen to sweep
        # s_z across the full [-1, +1] range while keeping the shortest pulse
        # far longer than the 127 ns turn-on delay; the spacing is deliberately
        # uneven so no rotation angle is a small-integer multiple of another.
        self.t_raman_pulse_frac_pi_list = np.array(
            [0.15, 0.3, 0.45, 0.6, 0.75, 0.9, 1.1, 1.35, 1.6, 1.9])

        # The AOM/switch turn-on latency, declared rather than implied. The
        # inherited t_raman_pulse_ideal only pins this down when t_raman_pulse
        # is a scalar, and here it is scanned -- see
        # RabiCalibration.from_params, which prefers this field.
        self.t_raman_turn_on_delay = 127.e-9

        # 15 pulses per shot x 10 durations x N_repeats shots. At N_repeats =
        # 10 that is 100 shots / 1500 measurements, which simulates to roughly
        # +/-45 Hz on f_rabi, +/-0.02 on the midpoint and +/-0.5 mV on the APD
        # endpoints. Everything scales as 1/sqrt(shots) from there.
        self.N_pulses = 15
        self.N_repeats = 10
