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

        self.xvar('dummy',[0]*1000)

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.outer_coil.ttl_blanking.off()

        self.outer_coil.set_supply(0.)
        self.outer_coil.set_voltage(20.)
        self.outer_coil.on()

        i = 182.

        self.outer_coil.ramp_supply(t=300.e-3, i_end=i, n_steps=100)

        # self.outer_coil.ttl_blanking.on()

        self.outer_coil.start_pid(i)
        

        delay(1.)
        self.ttl.pd_scope_trig.pulse(1.e-6)

        self.outer_coil.stop_pid()
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