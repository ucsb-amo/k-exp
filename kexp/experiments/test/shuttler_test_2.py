from artiq.experiment import *
from artiq.coredevice.core import Core
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay, parallel, sequential, delay_mu

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

import numpy as np

T32 = 1 << 32

class test(EnvExperiment):

    def prepare(self):

        ch = 0

        self.core = self.get_device("core")
        self.core: Core

        self.config = self.get_device("shuttler0_config")
        self.config: Config

        self.dc = self.get_device(f"shuttler0_dcbias{ch}")
        self.dc: DCBias

        self.dds = self.get_device(f"shuttler0_dds{ch}")
        self.dds: DDS

        self.shuttler_relay = self.get_device("shuttler0_relay")
        self.shuttler_relay: Relay

        self.shuttler_trigger = self.get_device("shuttler0_trigger")
        self.shuttler_trigger: Trigger

        self.zero32 = shuttler_volt_to_mu(0.)
        self.zero64 = np.int64(shuttler_volt_to_mu(0.))

        self.a = bytearray(16)
        self.a[0] = 1

    @portable
    def vtm(self,v):
        return shuttler_volt_to_mu(v)

    @kernel
    def run(self):
        self.core.reset()

        # self.shuttler_relay.init()
        self.shuttler_relay.enable(0b0000000000000011)
        # self.shuttler_relay.enable(self.a)

        self.config.set_gain(1,np.int32(0))

        # a0 = shuttler_volt_to_mu(1.)
        # self.dc.set_waveform(a0=a0,a1=0,a2=0,a3=0)
        # self.dds.set_waveform(b0=self.vtm(4.),b1=0,b2=0,b3=0,
        #                       c0=0,c1=np.int32(2**26),c2=0)

        # slope = 1.
        # yint = 1.0

        # p0 = self.vtm(yint)
        # # p1 = self.vtm(slope)
        # p1 = 2**31
        # p2 = 0
        # p3 = 0

        # T = 34.3
        T = 8.e-9
        # a0 = np.int32(p0)
        # a1 = np.int32(p1 * T + p2 * T**2 / 2 + p3 * T**3 / 6)
        # a2 = np.int64(p2 * T**2 + p3 * T**3)
        # a3 = np.int64(p3 * T**3)

        # self.dc.set_waveform(a0,a1,a2,a3)
        # self.dds.set_waveform(0,0,0,0,0,0,0)

        frequency = 100.e3

        n0 = self.vtm(3.)
        n1 = 0.
        n2 = 0.
        n3 = 0.
        r0 = 0.
        r1 = frequency
        r2 = 0.

        T = 8.e-9
        g = 1.64676
        q0 = n0/g
        q1 = n1/g
        q2 = n2/g
        q3 = n3/g

        b0 = np.int32(q0)
        b1 = np.int32(q1 * T + q2 * T**2 / 2 + q3 * T**3 / 6)
        b2 = np.int64(q2 * T**2 + q3 * T**3)
        b3 = np.int64(q3 * T**3)

        c0 = np.int32(r0)
        c1 = np.int32((r1 * T + r2 * T**2) * T32)
        c2 = np.int32(r2 * T**2)

        self.dc.set_waveform(self.vtm(0.),0,0,0)
        self.dds.set_waveform(b0=b0, b1=b1, b2=b2, b3=b3, c0=c0, c1=c1, c2=c2)

        self.shuttler_trigger.trigger(0b0000000000000011)
        
        
        