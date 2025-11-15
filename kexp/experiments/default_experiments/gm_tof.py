from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.xy_basler,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('frequency_detuned_imaging',np.arange(350.,450.,3)*1.e6)]

        

        # self.xvar('dumdum',[0]*10)
        # self.xvar('v_yshim_current',np.linspace(0.,9.8,10))
        # self.xvar('v_zshim_current_gm',np.linspace(0.6, 1., 10))
        # self.xvar('v_xshim_current_gm',np.linspace(0.5, 1., 10))
        # self.xvar('v_yshim_current_gm',np.linspace(0.0, 2.99, 10))
        # self.xvar('t_tof',[20.e-3,1.e-3])
        
        # self.xvar('t_mot_load',np.linspace(0.05,0.3,3))
        # self.xvar('t_tof',np.array([1.e-3,10.e-3,20.e-3]))
        # self.xvar('t_tof',np.linspace(300.,10000.,10)*1.e-6)
        # self.xvar('pfrac_d1_c_gm',np.linspace(0.5,1.0,5))
        # self.xvar('pfrac_d1_r_gm',np.linspace(0.3,0.6,5))
        self.p.v_zshim_current_gm = 0.82
        self.p.v_xshim_current_gm = 0.78
        self.p.v_yshim_current_gm = 1.0
        self.p.pfrac_d1_c_d1cmot = 1.0
        self.p.pfrac_d1_c_gm = 1.0
        self.p.pfrac_d1_r_gm = 0.3
        self.p.pfrac_c_gmramp_end = 0.7
        self.p.pfrac_r_gmramp_end = 0.3

        self.xvar('t_tof',np.linspace(1.,20.,10)*1.e-3)
        
        # self.p.amp_imaging = .35
        self.p.imaging_state = 2.
        self.p.t_tof = 7.5e-3
        self.p.t_mot_load = 1.5
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging)
        
        self.mot(self.p.t_mot_load)
        self.dds.push.off()

        self.cmot_d1(self.p.t_d1cmot)

        self.gm(self.p.t_gm * s)
        self.ttl.pd_scope_trig.pulse(1.e-6)
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
        self.p.v_xshim_current_gm = 0.8
        