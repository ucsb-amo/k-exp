from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=True,
                      camera_select=cameras.xy_basler,
                      save_data=True)

        

        # self.xvar('do_hybrid',[0,1])
        self.p.do_hybrid = 1

        # self.xvar('t_tof',np.linspace(0.1,1.2,7)*1.e-3)

        self.p.t_tof = 0.5e-3

        self.p.imaging_state = 2.
        self.xvar('t_mot_load',np.linspace(1.,2.5,7))
        self.p.t_mot_load = 1.
        self.p.N_repeats = 5

        # self.xvar('detune_d1_c_mot',np.linspace(9.5,11.,5))
        # self.xvar('v_pd_d1_c_mot',np.linspace(1.,4.,10))
        # self.xvar('detune_d1_r_mot',np.linspace(6.,9.5,5))
        # self.xvar('v_pd_d1_r_mot',np.linspace(1.,4.,10))

        self.p.detune_d1_c_mot = 11.
        self.p.detune_d1_r_mot = 7.5

        # self.xvar('detune_d1',np.linspace(7.,11.,5))
        self.p.detune_d1 = 9.
        # self.xvar('vpd_d1',np.linspace(0.,3.,11))
        self.p.vpd_d1 = 3.

        # self.xvar('detune_d2', np.linspace(-3.,2.,5))
        # self.p.detune_d2 = -2.

        # self.xvar('detune_d2_c_hmot', np.linspace(-2.4,-1.,5))
        # self.xvar('detune_d2_r_hmot', np.linspace(-5,-1.,5))
        self.p.detune_d2_c_hmot = -1.7
        self.p.detune_d2_r_hmot = -3.2

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging)     
        self.imaging.set_power(self.camera_params.amp_imaging)

        # self.p.detune_d1_c_mot = self.p.detune_d1
        # self.p.detune_d1_r_mot = self.p.detune_d1
        self.p.v_pd_d1_c_mot = self.p.vpd_d1
        self.p.v_pd_d1_r_mot = self.p.vpd_d1

        # self.p.detune_d2_c_hmot = self.p.detune_d2
        # self.p.detune_d2_r_hmot = self.p.detune_d2 * 2
        
        if self.p.do_hybrid:
            self.hybrid_mot(self.p.t_mot_load)
        else:
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