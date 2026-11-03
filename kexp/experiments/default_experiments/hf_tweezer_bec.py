
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
                      diagnostic_images=True,
                      warmup_shots=1,
                      mot_preload=True)

        # self.p.t_mot_load = 1.0
        # self.p.v_pd_hf_tweezer_1064_rampdown2_end
        # self.p.t_tweezer_hold = 100.e-3
        # self.p.t_tweezer_hold = 900.e-3 #87461 (20 ms gave +20-40 % vs 100 ms), 2026-10-20

        self.xvar('t_tof',np.linspace(150.,2500.,7)*1.e-6)
        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-2.,4.99,9))
        # self.xvar('v_pd_hf_tweezer_1064_rampdown2_end',np.linspace(0.5,1.0,8))
        self.p.v_pd_hf_tweezer_1064_rampdown2_end = 0.5 # 0.5
        # self.xvar('i_hf_lightsheet_evap2_current', np.linspace(192.7, 193.8, 7))
        # self.p.t_hf_lightsheet_rampdown = 300.e-3
        # self.p.v_pd_hf_tweezer_1064_rampdown_end = 0.16
    
        # self.xvar('t_hf_tweezer_1064_rampdown2',np.linspace(0.1,0.7,7))
        self.p.t_hf_tweezer_1064_rampdown2=0.3
        # self.p.v_pd_hf_tweezer_1064_rampdown2_end = 0.9
        # self.p.v_hf_tweezer_paint_amp_max = 4.9

        # self.p.t_tof = 4.e-3
        self.p.t_tof = 800.e-6

        # self.data.apd = self.data.add_data_container(1)
        # self.xvar('t_tweezer_hold',np.linspace(0.,0.8,6))
        self.p.N_repeats = 2
        # self.xvar('beans',np.linspace(1,10,10))

        # self.p.amp_tweezer_list = [0.5]

        self.scanning()

        Adjust.__init__(self)
        self.finish_prepare(shuffle=True)


    def scanning(self):

        # self.p.v_hf_tweezer_paint_amp_max = 2.
        # self.p.v_pd_hf_tweezer_1064_rampdown2_end = 4.

        # self.xvar('v_pd_hf_tweezer_1064_rampdown2_end',np.linspace(4.0,8.,4))

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(2.0,4.9,7))
        # self.p.v_hf_tweezer_paint_amp_max = 3.25


        # self.xvar('t_tof',np.linspace(800.e-6,2000.e-6,5))
        # self.p.i_hf_tweezer_evap1_current= 193.75
        # self.xvar('i_hf_tweezer_evap1_current',np.linspace(192.,194.,9))
        

        # self.p.i_hf_lightsheet_evap1_current = 194.3
        # self.p.t_hf_lightsheet_rampdown = 1.3

        # self.xvar('v_pd_hf_tweezer_1064_rampdown_end',np.linspace(0.16,0.5,5))

        # self.xvar('do_compression',[0,1])
        # self.p.do_compression = 0
        pass

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)

        self.prepare_hf_tweezers(do_tweezer_evap_2=False)
        # self.prepare_hf_tweezers()
         
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

