
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=True,
                      save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)

        self.p.N_repeats = 3

        self.p.ramp_down_painting = 0
        self.xvar('ramp_down_painting',[0,1])
        
        self.p.t_tweezer_hold = 10.e-3
        self.xvar('t_tweezer_hold',np.linspace(0.,2000.,6)*1.e-3)

        self.p.t_tof = 800.e-6
        self.p.t_imaging_pulse = 20.e-6
        self.p.amp_imaging = 0.2
        self.camera_params.gain = 300
        
        self.data.apd = self.data.add_data_container(1)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amp_imaging)

        if self.p.ramp_down_painting:
            self.prepare_hf_tweezers(ramp_down_painting=True)
        else:
            self.prepare_hf_tweezers(ramp_down_painting=False)
         
        delay(self.p.t_tweezer_hold)
        
        self.tweezer.off()

        delay(self.p.t_tof)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        self.abs_image()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

