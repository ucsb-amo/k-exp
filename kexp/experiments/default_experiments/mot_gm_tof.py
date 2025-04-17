from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        # self.xvar('frequency_detuned_imaging',np.arange(-150.,150.,8)*1.e6)

        # self.xvar('detune_push',np.linspace(-2.,2.,10))
        # self.xvar('amp_push',np.linspace(.05,.188,8))
        # self.p.detune_push = 0.

        # self.xvar('detune_d2_c_2dmot',np.linspace(-4.,1.5,8))
        # self.xvar('detune_d2_r_2dmot',np.linspace(-6.,-2.5,10))
        # self.p.detune_d2_r_2dmot = -4.4
        # self.p.detune_d2_c_2dmot = -1.6

        # self.xvar('amp_d2_c_2dmot',np.linspace(-6.,0.,8))
        # self.xvar('amp_d2_r_2dmot',np.linspace(.1,.188,8))

        # self.xvar('detune_d2_c_mot',np.linspace(-6.,-.5,8))
        # self.xvar('detune_d2_r_mot',np.linspace(-7.,-2.,8))
        # self.p.detune_d2_r_mot = -4.4
        # self.p.detune_d2_c_mot = -2.7

        # self.xvar('v_2d_mot_current',np.linspace(0.,5.,10))
        # self.p.v_2d_mot_current = 3.3

        # self.xvar('i_mot',np.linspace(15.,35.,30))
        # self.p.i_mot = 29.

        # self.xvar('v_zshim_current',np.linspace(0.,1.4,20))
        # self.xvar('v_xshim_current',np.linspace(3.,9.99,10))
        # self.xvar('v_yshim_current',np.linspace(3.,9.99,10))

        # self.xvar('detune_d1_c_d1cmot',np.linspace(6.,13.,8))
        # self.xvar('detune_d2_r_d1cmot',np.linspace(-5.,0.,8))

        # self.xvar('pfrac_d1_c_d1cmot',np.linspace(0.,.99,10))
        # self.xvar('amp_d2_r_d1cmot',np.linspace(0.,.188,10))

        # self.xvar('detune_d1_c_gm',np.linspace(11.,16.,4))
        # self.xvar('detune_d1_r_gm',np.linspace(11.,16.,4))

        self.p.detune_d1_c_gm = 14.
        self.p.detune_d1_r_gm = 14.

        # self.xvar('pfrac_d1_c_gm',np.linspace(.1,.99,8))
        # self.xvar('pfrac_d1_r_gm',np.linspace(0.1,.99,8))
        # self.pfrac_d1_c_gm = .67
        # self.pfrac_d1_r_gm = .67

        # self.xvar('v_zshim_current_gm',np.linspace(0.,2.,8))
        # self.xvar('v_xshim_current_gm',np.linspace(0.,7.,8))
        # self.xvar('v_yshim_current_gm',np.linspace(0.,9.,8))

        # self.xvar('dumdum',[0]*5)

        # self.xvar('t_tof',np.linspace(150.,500.,10)*1.e-6)
        
        self.p.amp_imaging = .35
        self.p.imaging_state = 2.
        self.p.t_tof = 4000.e-6
        self.p.t_mot_load = .5
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging)
        
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        
        self.gm(self.p.t_gm * s)
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.gm_ramp(self.p.t_gmramp)

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