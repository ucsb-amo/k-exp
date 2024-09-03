from artiq.experiment import *
from artiq.coredevice.core import Core
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay, parallel, sequential, delay_mu

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

import numpy as np

T16 = 1 << 16
T32 = 1 << 32
T48 = 1 << 48
T64 = 1 << 64

class test(EnvExperiment):

    def build(self):
        idx = 1

        self.core = self.get_device("core")
        self.core: Core

        self.config = self.get_device("shuttler0_config")
        self.config: Config

        self.dc = self.get_device(f"shuttler0_dcbias{idx}")
        self.dc: DCBias

        self.dds = self.get_device(f"shuttler0_dds{idx}")
        self.dds: DDS

        self.shuttler_relay = self.get_device("shuttler0_relay")
        self.shuttler_relay: Relay

        self.shuttler_trigger = self.get_device("shuttler0_trigger")
        self.shuttler_trigger: Trigger

        self.zero32 = shuttler_volt_to_mu(0.)
        self.zero64 = np.int64(shuttler_volt_to_mu(0.))

        self.a = bytearray(16)
        self.a[0] = 1

        self.ttl = self.get_device("ttl16")

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

        ###

        # slope = -1./(0.050)
        slope = 0.
        yint = 0.

        p0 = yint
        p1 = slope
        # p2 = 2 * (-2) / (50.e-3)**2
        p2 = 0
        p3 = 0

        # T = 34.3
        T = 8.e-9
        a0 = round( p0 * T16 / 20 ) & 0xffff
        a1 = round( (p1 * T + p2 * T**2 / 2 + p3 * T**3 / 6) * T32 / 20 ) & 0xffffffff
        a2 = round( (p2 * T**2 + p3 * T**3) * T48 / 20 ) & 0xffffffffffff
        a3 = round( (p3 * T**3) * T48 / 20 ) & 0xffffffffffff

        # a2 = 2
        a1 = 1

        print((p2 * T**2 + p3 * T**3) * T48 / 20)
        print(a1)
        self.core.break_realtime()

        self.dc.set_waveform(a0,a1,a2,a3)
        self.dds.set_waveform(0,0,0,0,0,0,0)

        ###

        n0 = 1.
        n1 = 0.
        n2 = 0.
        n3 = 0.
        r0 = 0.
        r1 = 1.e3 # frequency
        r2 = 0.

        T = 8.e-9
        g = 1.64676
        q0 = n0/g
        q1 = n1/g
        q2 = n2/g
        q3 = n3/g

        b0 = round(q0 * T16 / 20) & 0xffff
        b1 = round((q1 * T + q2 * T**2 / 2 + q3 * T**3 / 6) * T32 / 20) & 0xffffffff
        b2 = round((q2 * T**2 + q3 * T**3) * T48 / 20) & 0xffffffffffff
        b3 = round((q3 * T**3) * T48 / 20) & 0xffffffffffff

        c0 = round( r0 * T16 ) & 0xffff
        c1 = round( (r1 * T + r2 * T**2) * T32) & 0xffffffff
        c2 = round( (r2 * T**2) * T32 ) & 0xffffffff

        # print(c2)
        # self.core.break_realtime()

        self.dc.set_waveform(0,0,0,0)
        self.dds.set_waveform(b0=b0, b1=b1, b2=b2, b3=b3, c0=c0, c1=c1, c2=c2)

        ### trigger coeff change, turn on
        
        self.shuttler_trigger.trigger(0b0000000000000011)
        self.ttl.pulse(1.e-6)
        delay(50.e-3)
        self.shuttler_relay.enable(0b0000000000000000)
        
        
        