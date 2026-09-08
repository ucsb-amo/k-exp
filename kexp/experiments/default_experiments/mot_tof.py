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

        # self.xvar('frequency_detuned_imaging',np.arange(-50.,50.,5)*1.e6)

        # self.xvar('dumdum',np.linspace(1.,50.,50))

        self.xvar('t_tof',np.linspace(0.03,1.2,10)*1.e-3)

        self.p.t_tof = 0.05e-3
        # self.xvar('detune_d2_r_hmot', np.linspace(-7., -1.,8))
        # self.xvar('detune_d2_c_hmot', np.linspace(-3.4, -1.,8))
        self.detune_d2_r_mot = -6.14
        self.detune_d2_c_mot = -2.2
        self.detune_d2_c_hmot = -1.7
        self.detune_d2_r_hmot = -4.5
        # self.amp_d2_r_mot = 0.1
        # self.amp_d2_r_mot = 0.14
        # self.adjust('t_tof',min_val=20.e-6, max_val=2.e-3)

        # self.adjust('i_mot',min_val=0., max_val=80.)

        # self.adjust('v_xshim_current',min_val=0.,max_val=9.9)
        # self.adjust('v_yshim_current',min_val=0.,max_val=9.9)
        # self.adjust('v_zshim_current',min_val=0.,max_val=9.9)
        self.v_xshim_current=2.
        self.v_xshim_current=1.
        self.v_xshim_current=0.45
        # self.xvar('amp_imaging',np.linspace(.06,.5,15))
        # self.p.amp_imaging = .15
        self.p.imaging_state = 2.
        # self.p.t_tof = 20e-6
        self.p.t_mot_load = 1.
        self.p.N_repeats = 1


        # self.camera_params.gain = 28.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.dds.imaging.set_dds(amplitude=self.camera_params.amp_imaging)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging)     
        # self.imaging.set_power(self.camera_params.amp_imaging)
        
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