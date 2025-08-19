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

        self.xvar('t_ramsey_delay',np.linspace(0.,50.,10)*1.e-6)
        self.p.t_ramsey_delay = 100.e-6

        self.p.do_dynamical_decoupling = 0
        # self.xvar('do_dynamical_decoupling',[0,1])
        self.p.N_dd_pulses = 6
        self.p.dt_dd_gap = (self.p.t_ramsey_delay - self.p.N_dd_pulses * self.p.t_raman_pi_pulse) / (self.p.N_dd_pulses + 1)

        self.p.t_tof = 300.e-6

        self.p.t_tweezer_hold = .1e-3
        self.p.t_mot_load = 1.
        self.p.N_repeats = 2
        
        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.p.dt_dd_gap = (self.p.t_ramsey_delay - self.p.N_dd_pulses * self.p.t_raman_pi_pulse) / (self.p.N_dd_pulses + 1)

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging_m1)

        self.prepare_lf_tweezers()

        self.init_raman_beams(self.p.frequency_raman_transition,self.p.amp_raman)

        self.ttl.line_trigger.wait_for_line_trigger()
        delay(1.e-3)
        
        # self.raman.pulse(self.p.t_raman_pi_pulse/2)
        
        if self.p.do_dynamical_decoupling:
            pass
        #     for _ in range(self.p.N_dd_pulses):
        #         delay(self.p.dt_dd_gap)
        #         self.raman.pulse(self.p.t_raman_pi_pulse)
        #     delay(self.p.dt_dd_gap)
        else:
            delay(self.p.t_ramsey_delay)

        # self.raman.pulse(self.p.t_raman_pi_pulse/2)

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