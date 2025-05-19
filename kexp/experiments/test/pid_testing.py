from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from kexp.calibrations.magnets import compute_pid_overhead

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,save_data=False)

        self.xvar('dummy',[0])

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        self.outer_coil.set_voltage()

        # self.outer_coil.ramp_supply(t=100.e-3,i_start=0.,i_end=20.)

        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.outer_coil.start_pid()

        # self.outer_coil.start_pid(i_pid=0.)
        # self.outer_coil.set_pid(i_pid=0.)
        # self.outer_coil.pid_ttl.on()

        self.outer_coil.set_supply(i_supply=18.) # pid will eat all of this as it ramps
        delay(200.e-3)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.start_pid_no_overhead(i_pid = 18.)
        self.outer_coil.ramp_supply(t=100.e-3,i_start=18.,i_end=26.)


        # self.outer_coil.pid_ttl.on()

        # 
        # self.outer_coil.ramp_pid(t=self.p.t_feshbach_field_rampup,
        #                      i_start=0.,
        #                      i_end=self.p.i_lf_lightsheet_evap1_current)
        
       
        delay(300.e-3)
        self.outer_coil.stop_pid(i_supply=19.)
        delay(100.e-3)
        self.outer_coil.off()
        self.outer_coil.discharge()

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,
                         dds_off=False,
                         dds_set=False,
                         init_shuttler=False,
                         init_lightsheet=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)