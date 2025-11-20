from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=True,
                      camera_select='xy_basler',
                      save_data=True)

        # self.xvar('frequency_detuned_imaging',np.arange(-50.,50.,5)*1.e6)


        # self.xvar('dumdum',[0]*1000)

        # self.xvar('v_yshim_current',np.linspace(0.,9.8,10))

        # self.xvar('t_tof',np.linspace(.05,.5,10)*1.e-3)
        self.xvar('t_tof',np.linspace(0.4,1.2,10)*1.e-3)

        # self.p.amp_imaging = .35
        self.p.imaging_state = 2.
        self.p.t_tof = 20e-6
        self.p.t_mot_load = 1.
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        self.set_imaging_detuning(self.p.frequency_detuned_imaging)     
        
        self.mot(self.p.t_mot_load)
        self.dds.push.off()

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.release()

        delay(self.p.t_tof)

        self.flash_repump()
        self.abs_image()
       
    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)