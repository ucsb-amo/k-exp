from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        #self.xvar('v_zshim_current',np.linspace(0.,4.,15))
        #self.xvar('v_xshim_current',np.linspace(0.,4.,15))
        self.xvar('t_tof',np.linspace(.01,.5,30)*1.e-3)
        #self.xvar('beans',np.linspace(0.,1.,7))
        #self.xvar('detune_d2_c_mot',np.linspace(-5.,1.,40))
        self.p.detune_d2_c_mot = -2.
        # self.p.detune_d2_r_mot = -5.
        # self.vzshim_current = 1.71
        self.p.imaging_state = 2.
        self.p.t_tof = 10e-6
        self.p.v_xshim_current=1.43
        
        self.p.t_mot_load = 1.
        self.p.N_repeats = 1
        self.p.amp_imaging = 0.35

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        self.set_imaging_detuning(self.p.frequency_detuned_imaging)     
        
        self.mot(self.p.t_mot_load)
        self.dds.push.off()

        self.release()

        delay(self.p.t_tof)

        self.flash_repump()
        self.abs_image()
       
    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.p.v_zshim_current = 0.
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)