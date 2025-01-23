from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('frequency_detuned_imaging',np.arange(350.,450.,3)*1.e6)

        # self.xvar('i_cmot',np.linspace(13.,25.,10))

        # self.xvar('v_zshim_current',np.linspace(.0,1.,10))
        # self.p.v_zshim_current = .11
        # self.xvar('v_yshim_current',np.linspace(5.,9.99,10))
        # self.xvar('v_xshim_current',np.linspace(.0,9.,10))
       
        # self.xvar('detune_d2_r_d1cmot',np.linspace(-7.,0.,10))
        # self.p.detune_d2_r_d1cmot = -3.88
        # self.xvar('amp_d2_r_d1cmot',np.linspace(.02,.18,10))
        # self.p.amp_d2_r_d1cmot = .037
        
        # self.xvar('detune_d1_c_d1cmot',np.linspace(0.,10.,20))
        # self.p.detune_d1_c_d1cmot = 6.8
        # self.xvar('pfrac_d1_c_d1cmot',np.linspace(.1,.99,20))
        # self.p.pfrac_d1_c_d1cmot = .99

        # self.xvar('detune_d1_c_gm',np.linspace(3.,11.,8))
        # self.p.detune_d1_c_gm = 6.4
        # self.xvar('detune_d1_r_gm',np.linspace(3.,11.,8))
        # self.p.detune_d1_r_gm = 6.4
        # self.p.detune_gm = 7.85
        # self.xvar('detune_gm',np.linspace(7.,10.,8))

        # self.xvar('pfrac_d1_c_gm',np.linspace(.2,.99,8))
        # self.xvar('pfrac_d1_r_gm',np.linspace(.2,.99,8))
        # self.p.pfrac_d1_c_gm = .99
        # self.p.pfrac_d1_r_gm = .91

        # self.xvar('pfrac_c_gmramp_end',np.linspace(.05,.7,8))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(.05,.7,8))
        # self.p.pfrac_c_gmramp_end = 0.14
        # self.p.pfrac_r_gmramp_end = 0.142
        # self.xvar('pfrac_gm',np.linspace(0.2,0.9,8))

        # self.xvar('v_zshim_current_gm',np.linspace(.4,1.,10))
        # self.p.v_zshim_current_gm = .83
        # self.xvar('v_xshim_current_gm',np.linspace(0.,.8,10))
        # self.p.v_xshim_current_gm = .14
        # self.xvar('v_yshim_current_gm',np.linspace(0.,7.,12))
        # self.p.v_yshim_current_gm = 2.545

        # self.p.v_yshim_current_gm = 1.2
        # self.xvar('dumdum',[0]*100)

        self.xvar('t_tof',np.linspace(13.,20.,10)*1.e-3)
        # self.xvar('t_tof',np.linspace(200.,1500.,10)*1.e-6)
        
        self.p.amp_imaging = .17
        self.p.imaging_state = 2.
        self.p.t_tof = 100.e-6
        self.p.t_mot_load = 1.
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging)
        
        self.switch_d2_2d(1)
        
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
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)