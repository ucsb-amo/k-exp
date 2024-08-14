from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class compare_lightsheet_magtrap_atom_number(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.camera_params.amp_imaging = .5

        self.p.t_lightsheet_hold = .1
        self.p.t_tof_magtrap = 5.e-3
        self.p.t_tof_lightsheet = 150.e-6

        # self.xvar('lightsheet_bool',[1,0])

        self.p.lightsheet_bool = 0

        self.p.N_repeats = [10]

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
    
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        if self.p.lightsheet_bool:
            self.magtrap_and_load_lightsheet()
            
            delay(self.p.t_lightsheet_hold)

            self.lightsheet.off()

            delay(self.p.t_tof_lightsheet)
        
        else:
            self.magtrap()

            delay(self.p.t_lightsheet_rampup)

            self.inner_coil.off()

            delay(self.p.t_tof_magtrap)

        self.flash_repump()
        self.abs_image()

        # self.lightsheet.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)