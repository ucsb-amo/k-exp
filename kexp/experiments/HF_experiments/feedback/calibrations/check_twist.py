from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from artiq.language import now_mu
from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams

class check_twist(EnvExperiment, Base):
    """Read twist (p.read_twist_per_sz): the read's z rotation vs s_z at the read.

    The Ramsey of check_lightshift with the first pulse's area theta_area (units of pi)
    scanned: from the initial |1,-1> ('up', s_z = +1) state the read sees
    s_z = cos(pi * theta_area). The second pulse is pi/2 at relative_phase.

    Reference = pi, as in check_lightshift: with no light the final s_z is
    cos(theta) cos(beta) - sin(theta) sin(beta) cos(phi) for any first area theta and
    second area beta, so the fringe phase is pi at every theta (amplitude ~ sin(theta)).

    Analysis: waxa.analysis.lightshift.ramsey_light_shift(ad) (theta_area is a scan
    axis) gives phase_shift per theta. With theta11's dphi = th_read - th_noread =
    -phase_shift (APD and |1,-1> atom number both rise with s_z):
        phase_shift = read_alpha_lightshift - read_twist_per_sz * s_z
    A detuning or reference-phase error moves every theta's phase equally: the
    intercept, not the slope.

    Pulse areas include t_raman_pulse_offset (t_raman_pi_pulse is the rate pi time),
    as in theta_ramsey; s_z is only as good as t_raman_pi_pulse.
    """

    def prepare(self):
        p = ExptParams()
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION,
                      expt_params=p,
                      warmup_shots=3)

        self.p.theta_area = 0.5
        self.xvar('theta_area', np.array([0.2, 0.35, 0.5, 0.65, 0.8]))
        self.xvar('relative_phase', np.linspace(0., 3*np.pi, 21))

        # the feedback read: amp_imaging, t_img_pulse from ExptParams (feedback)
        self.p.t_ramsey = self.p.t_img_pulse

        self.p.t_tweezer_hold = 15.e-3
        self.p.t_tof = 1.5e-3
        self.p.t_mot_load = 1.
        self.p.N_repeats = 2

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        t_pulse_theta = self.p.theta_area * self.p.t_raman_pi_pulse + self.p.t_raman_pulse_offset
        t_pulse_pi2 = 0.5 * self.p.t_raman_pi_pulse + self.p.t_raman_pulse_offset

        self.raman.set(t_phase_origin_mu=now_mu())

        self.raman.pulse(t_pulse_theta)

        self.imaging.on()
        delay(self.p.t_ramsey)
        self.imaging.off()

        self.raman.set(relative_phase=self.p.relative_phase)
        self.raman.pulse(t_pulse_pi2)

        self.ttl.raman_shutter.off()

        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(.2)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)

        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
