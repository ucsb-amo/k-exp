from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.xy_basler,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('frequency_detuned_imaging',np.arange(350.,450.,3)*1.e6)

        # self.xvar('dumdum',[0]*10)
        # self.xvar('v_yshim_current',np.linspace(0.,9.8,10))
        # self.xvar('v_zshim_current_gm',np.linspace(0.6, 1., 10))
        # self.xvar('v_xshim_current_gm',np.linspace(0.0, 1., 10))
        # self.xvar('v_yshim_current_gm',np.linspace(0.0, 4., 15))
        self.xvar('t_tof',np.linspace(12.,20.,2)*1.e-3)
        # self.xvar('t_tof',np.linspace(300.,10000.,10)*1.e-6)
        # self.xvar('t_mot_load',np.linspace(0.25,1.,10))
        # self.xvar('detune_gm',np.linspace(8.5,13.,10))
        # self.p.v_zshim_current_gm
        
        # self.p.amp_imaging = .35
        self.p.imaging_state = 2.
        self.p.t_tof = 10.e-3
        self.p.t_mot_load = 0.5
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging)
        
        self.mot(self.p.t_mot_load)
        self.dds.push.off()

        self.cmot_d1(self.p.t_d1cmot)

        self.ttl.pd_scope_trig.pulse(1.e-6)

        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

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