from artiq.experiment import *
from artiq.experiment import delay
from artiq.language import now_mu
from kexp import Base, img_types, cameras
from kexp.base import RandomRamanPulseTimes

from kexp.experiments.HF_experiments.feedback.calibrations.rabi_posterior.expt_params_apd_joint_calibration \
    import ExptParams as ExptParamsAPDJoint


class apd_joint_calibration(EnvExperiment, Base, RandomRamanPulseTimes):
    """Pulse train with a scanned pulse duration, for calibrating the APD.

    Same sequence as rabi_posterior_pulse_train -- N_pulses raman pulses
    interleaved with weak APD measurements, drive on resonance throughout --
    but every pulse within a shot uses the SAME duration, and that duration is
    scanned across shots over a wide range.

    The point is what the host-side fit can then do with it. Written in voltage
    rather than photon-count space the measurement model is

        v = (1 - g)*v_apd_all_down + g*v_apd_all_up

    with g the photon fraction, which is exactly LINEAR in the two APD
    endpoints while s_z depends only on the Bloch-level parameters. So
    kexp.analysis.RabiJointPosterior can grid over
    (f_rabi, midpoint_fraction, frequency_lightshift, back_action_coherence)
    and marginalize v_apd_all_down and v_apd_all_up out in closed form,
    returning all six at once. That turns the light shift and the back-action
    coherence -- the constants that currently dominate the systematic budget on
    f_rabi -- from assumed inputs into measured outputs.

    Why the duration is scanned rather than randomized, and what it costs to do
    otherwise, is in expt_params_apd_joint_calibration.py.

    Analyze with:

        from kexp import atomdata
        from kexp.analysis import RabiJointPosterior

        ad = atomdata(<run_id>)
        jp = RabiJointPosterior(
            ad,
            f_rabi_grid=(54.e3, 58.e3, 81),
            midpoint_grid=(0.50, 0.72, 45),
            lightshift_grid=(28.e3, 42.e3, 21),
            coherence_grid=(0.75, 0.95, 21),
        )
        jp.run().print()
    """

    def prepare(self):
        self.p = ExptParamsAPDJoint()
        # DISPERSIVE, not ABSORPTION: init_kernel(setup_slm=True) branches on
        # this to choose the SLM phase mask (Base.setup_slm), and ABSORPTION
        # writes a FLAT mask instead of the phase-contrast dot. The weak APD
        # state readout is a dispersive measurement, and the calibration this
        # experiment exists to refine -- v_apd_all_up/down from
        # apd_voltage_vs_state_2 -- is taken with the dot in place. Declaring
        # ABSORPTION here reads the atoms out through a different optical
        # configuration than the calibration was taken in, which inverts the
        # sign of the state-dependent APD response (see runs 76245 / 76269, and
        # RabiJointPosterior.polarity_check).
        Base.__init__(self, setup_camera=False,
                      camera_select=cameras.andor,
                      imaging_type=img_types.DISPERSIVE,
                      save_data=True,
                      expt_params=self.p)

        # The scan axis. Statistics come from N_repeats shots at each duration;
        # the spread of durations is what makes the six-way fit identifiable.
        self.xvar('t_raman_pulse',
                  self.p.t_raman_pi_pulse * self.p.t_raman_pulse_frac_pi_list)

        # Draw once here so the list attribute has its compile-time shape and
        # dtype; scan_kernel rebuilds it per shot. With
        # p.t_raman_pulse_random_bool = 0 (set in the params) this is a
        # constant list at the scalar p.t_raman_pulse, which the scan machinery
        # overwrites per shot -- so each shot gets a flat list at its own
        # scanned duration.
        self.p.t_raman_pulse_list = self.get_new_t_raman_pulse_list(
            seed=self.resolve_t_raman_pulse_seed())

        # All "one value per pulse" containers are sized exactly N_pulses --
        # there is no reserved pre-pulse slot here, and an oversized container
        # leaves an unwritten zero column that the analysis would have to guess
        # about (see data_vault_feedback.py and
        # kexp.analysis.feedback._trim_known_unused_trailing_column).
        self.data.apd = self.data.add_data_container(self.p.N_pulses)
        self.data.t = self.data.add_data_container(self.p.N_pulses)
        # The realized duration of each pulse of this shot. RabiJointPosterior
        # reads this per shot and never has to trust the scan axis.
        self.data.t_raman_pulse = self.data.add_data_container(self.p.N_pulses)
        self.data.t_raman_pulse_seed = self.data.add_data_container(1)
        # [0] light leakage with the atoms released, [1] detector dark level.
        # [0] is an approximate independent anchor on v_apd_all_down.
        self.data.apd_reference = \
            self.data.add_data_container(self.p.N_reference_reads)

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        # This shot's pulse times, built on the host from the scanned duration.
        # Both RPCs need slack, so they run outside the RTIO timeline;
        # break_realtime re-arms it.
        self.core.wait_until_mu(now_mu())
        t_raman_pulse_seed = self.resolve_t_raman_pulse_seed()
        self.p.t_raman_pulse_list = self.get_new_t_raman_pulse_list(
            seed=t_raman_pulse_seed)
        self.data.t_raman_pulse_seed.put_data(float(t_raman_pulse_seed))
        self.data.t_raman_pulse.put_data_1d(self.p.t_raman_pulse_list)
        self.core.break_realtime()

        # Midpoint detuning and amp_imaging must match what the APD/lightshift
        # calibrations in expt_params_feedback.py were taken at -- this
        # experiment refines those constants, so it has to sit at the same
        # operating point they describe.
        self.set_imaging_detuning(
            frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        self.integrator.init()

        self.prepare_hf_tweezers()

        # Drive frequency defaults to p.frequency_raman_transition -- the whole
        # premise of this experiment is that it is already correct. phase_mode=1
        # anchors the DDS phase origin, so on resonance every pulse in the train
        # rotates about the same equatorial axis.
        self.prep_raman()

        t0_mu = now_mu()

        for i in range(self.p.N_pulses):
            self.data.t.put_data((now_mu() - t0_mu) * 1.e-9, i)

            self.raman.pulse(self.p.t_raman_pulse_list[i])

            # measure_integrated_v, not integrated_imaging_pulse: the sampler
            # readback is a blocking RTIO input that leaves ~zero slack, so
            # back-to-back calls need the trailing t_apd_slack this re-arms.
            self.data.apd.put_data(
                self.imaging.measure_integrated_v(self.p.t_img_pulse), i)

            delay(self.p.t_pulse_gap)

        # The mechanical raman shutter is milliseconds-slow, so it stays open
        # for the entire train -- individual pulses are gated by the AOM switch
        # inside raman.pulse.
        self.ttl.raman_shutter.off()

        # Reference reads with the atoms gone: light leakage, then dark.
        delay(self.p.t_tweezer_hold)
        self.tweezer.off()
        delay(10.e-3)
        self.data.apd_reference.put_data(
            self.imaging.measure_integrated_v(self.p.t_img_pulse), 0)
        delay(50.e-6)
        self.data.apd_reference.put_data(
            self.imaging.measure_integrated_v(self.p.t_img_pulse, dark=True), 1)

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
