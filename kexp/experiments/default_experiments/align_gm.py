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
        # 

        # self.xvar('do_hybrid', [0.,1.])

        self.p.imaging_state = 2.
        self.p.t_tof = 12.e-3
        self.p.t_mot_load = 1.
        self.p.N_repeats = 1000

        # self.xvar('amp_imaging',np.linspace(0.25,1.,8))
        # self.xvar('v_xshim_current_gm',np.linspace(0.,1.,8))
        # self.xvar('v_yshim_current_gm',np.linspace(0.,3.,7))
        # self.xvar('v_zshim_current_gm',np.linspace(0,1.2,7))


        # self.xvar('pfrac_r_gmramp_end',np.linspace(0.0,0.5,9))
        # self.xvar('pfrac_c_gmramp_end',np.linspace(0.0,0.5,9))
        
        # self.xvar('t_gm',[0.,self.p.t_gm])

        # self.xvar('t_tof',np.linspace(6.,12.,10)*1.e-3)

        # self.xvar('detune_d1_c_gm',np.linspace(6.,11.,7))
        # self.xvar('detune_d1_r_gm',np.linspace(6.,11.,7))
        # self.p.detune_d1_c_gm = 8.5
        # self.p.detune_d1_r_gm = 8.5

        # self.xvar('pfrac_d1_c_gm',np.linspace(0.3,1.,6))
        # self.p.pfrac_d1_c_gm = 0.94
        # self.xvar('pfrac_d1_r_gm',np.linspace(0.3,1.,6))
        # self.p.pfrac_d1_r_gm = 0.9

        # self.p.pfrac_c_gmramp_start = 0.35
        # self.p.pfrac_r_gmramp_start = 0.5

        self.adjust('detune_d1_c_gm', min_val=0., max_val=13.)
        self.adjust('detune_d1_r_gm', min_val=0., max_val=13.)

        self.adjust('pfrac_r_gmramp_end', min_val=0., max_val=self.p.pfrac_d1_r_gm)
        self.adjust('pfrac_c_gmramp_end', min_val=0., max_val=self.p.pfrac_d1_c_gm)

        self.adjust('v_xshim_current_gm',min_val=0.,max_val=9.9)
        self.adjust('v_yshim_current_gm',min_val=0.,max_val=9.9)
        self.adjust('v_zshim_current_gm',min_val=0.,max_val=9.9)

        self.p.pfrac_c_gmramp_end = 0.35
        self.p.pfrac_r_gmramp_end = 0.5

        # self.p.pfrac_c_gmramp_end = 0.15
        # self.p.pfrac_r_gmramp_end = 0.39

        # self.xvar('')

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.imaging.set_power(self.camera_params.amp_imaging)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()

        self.cmot_d1(self.p.t_d1cmot)
        
        self.gm(self.p.t_gm)
        self.ttl.pd_scope_trig.pulse(1.e-8)
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
        
        