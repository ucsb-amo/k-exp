from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=False,
                      camera_select=cameras.xy_basler,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('frequency_detuned_imaging',np.arange(350.,450.,3)*1.e6)]

        # self.xvar('dumdum',[0]*10)
        # self.xvar('t_tof',np.linspace(10.,20.,10)*1.e-3)
        
        self.p.amp_imaging = .18
        self.p.imaging_state = 2.
        self.p.t_tof = 15.e-3
        self.p.t_mot_load = .2
        self.p.N_repeats = 100

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging)

        self.dds.mot_killer.set_dds_gamma(0.,.188)
        
        self.mot(self.p.t_mot_load)
        self.dds.push.off()

        self.cmot_d1(self.p.t_d1cmot)

        self.ttl.pd_scope_trig.pulse(1.e-8)
        self.gm(self.p.t_gm)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        self.dds.mot_killer.on()

        delay(self.p.t_tof)

        self.flash_repump()
        self.abs_image()

        self.dds.mot_killer.off()
       
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
        
        