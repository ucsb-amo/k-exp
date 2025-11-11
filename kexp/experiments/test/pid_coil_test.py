from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class mot_kill_405(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.p.i_non_inter = 182.0
        self.p.i_overhead = 70.0

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.ttl.b_field_stab_SRS_blanking_input.on()
        delay(1.e-3)
        
        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_hf_lightsheet_evap1_current)
        
        delay(self.p.t_hf_lightsheet_rampdown)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_lightsheet_evap1_current,
                             i_end=self.p.i_hf_tweezer_load_current)
    
        delay(self.p.t_hf_tweezer_1064_ramp)
        delay(self.p.t_lightsheet_rampdown3)

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_tweezer_load_current,
                             i_end=self.p.i_hf_tweezer_evap1_current)
        
        delay(self.p.t_hf_tweezer_1064_rampdown)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_tweezer_evap1_current,
                             i_end=self.p.i_hf_tweezer_evap2_current)
        
        delay(self.p.t_hf_tweezer_1064_rampdown2)

        self.outer_coil.ramp_supply(t=30.e-3,
                             i_end=self.p.i_non_inter)

        self.ttl.b_field_stab_SRS_blanking_input.off()
        delay(100.e-3)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.start_pid(i_overhead=self.p.i_overhead)

        delay(500.e-3)

        self.outer_coil.stop_pid()

        self.outer_coil.off()
       
    @kernel
    def run(self):
        self.init_kernel(dds_off=False,dds_set=False,init_dds=False,
                         init_shuttler=False,init_lightsheet=False,
                         init_dac=False,setup_awg=False,
                         setup_slm=False)
        self.scan()

        self.outer_coil.off()
        
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)