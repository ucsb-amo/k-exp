from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=False)

        # self.p.v_yshim_current_gm = 1.2
        self.xvar('dumdum',[0]*100)

        self.p.t_2d_mot_load = 2.
        self.p.v_2d_mot_current = 2.5

        # self.xvar('t_tof',np.linspace(14.,20.,10)*1.e-3)
        
        self.p.amp_imaging = .38
        # self.p.imaging_state = 2.
        self.p.t_tof = 20.e-6
        self.p.t_mot_load = 2.
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):    
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.dds.d2_2d_c.set_dds_gamma(delta=self.p.detune_d2_c_2dmot,
                                 amplitude=self.p.amp_d2_c_2dmot)
        delay(self.params.t_rtio)
        self.dds.d2_2d_r.set_dds_gamma(delta=self.p.detune_d2_r_2dmot,
                                 amplitude=self.p.amp_d2_r_2dmot)
        delay(self.params.t_rtio)
        self.dds.push.set_dds_gamma(delta=self.p.detune_push,
                                 amplitude=self.p.amp_push)
        self.dds.push.off()
        
        self.dac.supply_current_2dmot.set(v=self.p.v_2d_mot_current)

        self.dds.d2_2d_c.on()
        self.dds.d2_2d_r.on()

        delay(self.p.t_2d_mot_load)

        self.dds.push.on()
        
        self.mot(self.p.t_mot_load)
        self.dds.push.off()

        self.release()

        delay(self.p.t_tof)

        self.flash_repump()
        self.abs_image()
       
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