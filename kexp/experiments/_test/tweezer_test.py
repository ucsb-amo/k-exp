from artiq.experiment import *
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint
from artiq.language.core import kernel_from_string, now_mu

RPC_DELAY = 10.e-3

import numpy as np

class test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.xvar('dummy',[1]*2)

        self.f_list = np.linspace(70.,80.,5)*1.e6
        self.amp_list = np.linspace(.2,.2,5)

        self.f_list2 = np.linspace(71.,79.,5)*1.e6
        self.amp_list2 = np.linspace(.05,.05,5)

        self.f_list3 = np.linspace(73.,77.,5)*1.e6
        self.amp_list0 = np.linspace(.0,.0,5)

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.tweezer.sw_ttl.on()
        self.tweezer.vva_dac.set(5.)
        self.core.wait_until_mu(now_mu())
        self.tweezer.set_static_tweezers(self.f_list,self.amp_list)
        self.core.break_realtime()

        self.tweezer.awg_trg_ttl.pulse(t=1.e-6)

        delay(2.)

        self.core.wait_until_mu(now_mu())
        self.tweezer.set_static_tweezers(self.f_list2,self.amp_list)
        self.core.break_realtime()

        self.tweezer.awg_trg_ttl.pulse(t=1.e-6)

        delay(2.)

        self.core.wait_until_mu(now_mu())
        self.tweezer.set_static_tweezers(self.f_list3,self.amp_list)
        self.core.break_realtime()

        self.tweezer.awg_trg_ttl.pulse(t=1.e-6)

        delay(2.)

        self.tweezer.sw_ttl.off()

    @kernel
    def run(self):

        self.init_kernel()

        self.scan()

        self.core.wait_until_mu(now_mu())
        self.tweezer.close()
        delay(RPC_DELAY)

        delay(1*s)