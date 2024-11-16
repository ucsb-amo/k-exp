from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,camera_select='andor',save_data=False)

        self.i_initial = 192.3
        self.i_pid = 196.23 # equivalent ot 192.3 from power supply

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.outer_coil.on()
        delay(1.e-3)
        self.outer_coil.set_voltage()
        delay(50.e-3)

        # # ramp up field
        self.outer_coil.ramp_supply(t=200.e-3,
                             i_start=0.,
                             i_end=self.i_initial)
        
        # wait for supply to finish ramping
        delay(180.e-3)

        # trigger scope and turn on PID
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.start_pid(i_pid=self.i_pid)

        # wait
        delay(0.6)

        self.ttl.outer_coil_pid_enable.off()
        delay(50.e-3)
        self.outer_coil.off()
        

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)