from artiq.experiment import *
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint

import numpy as np

class test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,save_data=False)
        self.finish_prepare(shuffle=False)

    @kernel
    def run(self):

        coil = self.outer_coil

        v = 70.
        i = 50.

        self.init_kernel(init_dac=True,init_dds=True)
        ##
        
        coil.on()
        coil.set_voltage(v)
        coil.set_current(i)
        delay(2.)
        # coil.set_voltage(0.)
        # coil.set_current(0.)
        # delay(30.e-3)
        coil.off()

        delay(50.e-3)

        # coil.discharge_igbt_ttl.on()
        coil.on()
        # coil.set_voltage(v)
        # coil.set_current(i)
        coil.set_voltage(0.)
        coil.set_current(0.)
        delay(30.e-3)
        # coil.discharge_igbt_ttl.off()
        coil.off()

        delay(1.)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        coil.on()
        coil.set_voltage(v)
        coil.set_current(i)
        delay(2.)
        coil.set_voltage(0.)
        coil.set_current(0.)
        delay(30.e-3)
        coil.off()
