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

        self.i_initial = 10.
        self.v_pid_setpoint = .205

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
        delay(100.e-3)

        # trigger scope and turn on PID
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.dac.inner_coil_pid.set(0.)
        self.dac.outer_coil_pid.set(v=self.v_pid_setpoint)
        self.ttl.outer_coil_pid_enable.on()

        # wait
        delay(1.3)

        self.outer_coil.off()
        self.outer_coil.discharge()
        self.ttl.outer_coil_pid_enable.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)