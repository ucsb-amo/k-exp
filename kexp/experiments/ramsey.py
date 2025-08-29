from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.control.slm.slm import SLM
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        f_range = 15.e3
        df = 5.e3
        self.p.frequency_raman_transition = 41.12e6
        # self.xvar('frequency_raman_transition',
        #           self.p.frequency_raman_transition + np.arange(-f_range, f_range +df, df))

        self.xvar('t_ramsey_delay', np.linspace(0.,400.,30)*1.e-6)
        # self.p.t_ramsey_delay = 10.e-6
        self.p.t_ramsey_delay = 5.e-6

        # self.xvar('line_trigger_phase_delay', np.linspace(0.00, 0.017, 10))
        self.p.line_trigger_phase_delay = 0.
        
        # self.xvar('relative_phase_shift',np.linspace(0.,np.pi,10))
        self.p.relative_phase_shift = 0.
        self.p.global_phase_shift = 0.

        self.p.do_pi_pulse = 0

        self.p.t_tof = 600.e-6
        self.p.t_tweezer_hold = .1e-3

        self.p.t_mot_load = 1.
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(self.p.frequency_detuned_imaging_m1)

        self.prepare_lf_tweezers()

        self.init_raman_beams(self.p.frequency_raman_transition,self.p.amp_raman)

        self.line_trigger()

        self.state_prep()
        
        self.ramsey()

        self.release_and_image()

    @kernel
    def ramsey(self):
        # Ramsey sequence
        self.raman.pulse(self.p.t_raman_pi_pulse/2)

        delay(self.p.t_ramsey_delay)

        self.raman.set_phase(global_phase=self.p.global_phase_shift,
                             relative_phase=self.p.relative_phase_shift)
        self.raman.pulse(self.p.t_raman_pi_pulse/2)

    @kernel
    def line_trigger(self):
        # line trigger
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(1.e-3)
        delay(self.p.line_trigger_phase_delay)

    @kernel
    def state_prep(self):
        # state prep
        if self.p.do_pi_pulse:
            self.raman.pulse(self.p.t_raman_pi_pulse)
        else:
            delay(self.p.t_raman_pi_pulse)
        
    @kernel
    def release_and_image(self):
        delay(self.p.t_tweezer_hold)
        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()
        
    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)