
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras, Adjust


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=4)

        self.p.t_mot_load = 1.0
        self.p.t_tweezer_hold = 100.e-3

        # self.xvar('t_tof',np.linspace(1000.,4000.,6)*1.e-6)
        self.p.t_tof = 20.e-6

        self.data.apd = self.data.add_data_container(1)

        self.p.N_repeats = 5

        self.scanning()
        self.finish_prepare(shuffle=True)

    def scanning(self):

        # self.p.v_hf_tweezer_paint_amp_max = 2.
        # self.p.v_pd_hf_tweezer_1064_rampdown2_end = 2.2

        # self.xvar('v_pd_hf_tweezer_1064_rampdown2_end',np.linspace(2.2,5.,9))

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(2.,3.0,4))
        # self.p.v_hf_tweezer_paint_amp_max = 2.5


        # self.xvar('t_tof',np.linspace(100.e-6,3000.e-6,9))
        # self.p.i_hf_tweezer_evap1_current= 193.75
        # self.xvar('i_hf_tweezer_evap1_current',np.linspace(192.,194.,9))
        

        # self.p.i_hf_lightsheet_evap1_current = 194.3
        # self.p.t_hf_lightsheet_rampdown = 1.3

        # self.xvar('amp_imaging',np.linspace(0.05,0.15,5))

        # self.xvar('do_compression',[0,1])
        # self.p.do_compression = 0
        pass

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)

        self.prepare_hf_tweezers()
         
        delay(self.p.t_tweezer_hold)
        
        self.tweezer.off()

        delay(self.p.t_tof)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath, restart_monitor=False)

