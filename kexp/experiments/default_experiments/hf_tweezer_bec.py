
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras, Adjust


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=0)

        self.p.t_mot_load = 1.0
        self.p.t_tweezer_hold = 100.e-3

        # self.xvar('t_tof',np.linspace(1000.,4000.,10)*1.e-6)
        # self.p.t_tof = 4.e-3
        self.p.t_tof = 20.e-6

        self.data.apd = self.data.add_data_container(1)

        self.p.N_repeats = 1000
        # self.xvar('beans',np.linspace(1,1000,1000))

        self.scanning()
        self.adjust('frequency_detuned_hf_midpoint',min_val=-530.e6,max_val=-500.e6,step=1.e6)
        self.adjust('phase_slm_mask',min_val=0.,max_val=np.pi,step=0.1*np.pi)
        self.finish_prepare(shuffle=True)


    def scanning(self):

        # self.p.v_hf_tweezer_paint_amp_max = 2.
        # self.p.v_pd_hf_tweezer_1064_rampdown2_end = 4.

        # self.xvar('v_pd_hf_tweezer_1064_rampdown2_end',np.linspace(4.0,8.,4))

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(0.,4.9,7))
        # self.p.v_hf_tweezer_paint_amp_max = 3.25


        # self.xvar('t_tof',np.linspace(100.e-6,3000.e-6,9))
        # self.p.i_hf_tweezer_evap1_current= 193.75
        # self.xvar('i_hf_tweezer_evap1_current',np.linspace(192.,194.,9))
        

        # self.p.i_hf_lightsheet_evap1_current = 194.3
        # self.p.t_hf_lightsheet_rampdown = 1.3

        # self.xvar('v_pd_hf_tweezer_1064_rampdown_end',np.linspace(0.16,0.5,5))

        # self.xvar('do_compresPsion',[0,1])
        # self.p.do_compression = 0
        pass

    @kernel
    def scan_kernel(self):
        # self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)

        self.prepare_hf_tweezers(do_tweezer_evap_2=False)
         
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

