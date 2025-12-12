from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=False,
                      camera_select='xy_basler',
                      save_data=False)
        
        self.p.i_current_ramp_min = 15.
        self.p.i_current_ramp_max = 60.

        # self.xvar('amp_imaging',np.linspace(0.1,.4,15))
        self.p.amp_imaging = .18
        # self.p.imaging_state = 1.
        self.p.imaging_state = 2.
        self.p.t_tof = 20.e-6
        self.p.t_mot_load = .5
        self.p.N_repeats = 1000

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging)
        
        self.mot(self.p.t_mot_load)

        for _ in range(1000):
            self.inner_coil.ramp_supply(t=1.,
                                        i_start=self.p.i_current_ramp_min,
                                        i_end=self.p.i_current_ramp_max,
                                        n_steps=100,
                                        t_analog_delay=0.)
            self.inner_coil.ramp_supply(t=1.,
                                        i_start=self.p.i_current_ramp_max,
                                        i_end=self.p.i_current_ramp_min,
                                        n_steps=100,
                                        t_analog_delay=0.)

        # self.dds.push.off()
        # self.cmot_d1(self.p.t_d1cmot)
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.gm(self.p.t_gm,
        #         detune_d1=self.p.detune_d1_gm)
        # self.gm_ramp(self.p.t_gmramp,detune_d1=self.p.detune_d1_gm)

        # self.release()

        # delay(self.p.t_tof)
        # self.flash_repump()
        # self.abs_image()
       
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