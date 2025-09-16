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
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('beans',[0]*500)
    
        self.p.t_tof = 60.e-6

        self.p.t_raman_sweep = 1.e-3
        self.p.frequency_raman_transition = 41.245e6
        
        self.xvar('t_raman_pulse',np.linspace(0.,70.e-6,30))
        self.p.amp_raman = 0.35

        self.p.t_tweezer_hold = .1e-3
        self.p.t_mot_load = 1.
        
        self.p.N_repeats = 1
        self.camera_params.exposure_time = 60.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time
        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging_m1)

        self.prepare_lf_tweezers()

        self.init_raman_beams(self.p.frequency_raman_transition,self.p.amp_raman)

        self.ttl.line_trigger.wait_for_line_trigger()

        delay(5.7e-3)

        self.raman.pulse(t=self.p.t_raman_pulse)

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