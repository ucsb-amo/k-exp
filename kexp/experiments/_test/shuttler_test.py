from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class shuttler_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,camera_select='andor',save_data=False)

        # self.xvar('freq_tweezer_modulation',np.linspace(100.e3,1000.e3,30))
        self.p.freq_tweezer_modulation = 215.e3
        self.p.v_modulation_depth = 6.

        self.sh_dds = self.get_device("shuttler0_dds0")
        self.sh_dds: DDS
        self.sh_dds1 = self.get_device("shuttler0_dds1")
        self.sh_dds1: DDS
        self.sh_trigger = self.get_device("shuttler0_trigger")
        self.sh_trigger: Trigger
        self.sh_relay = self.get_device("shuttler0_relay")
        self.sh_relay: Relay

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        frequency = self.p.freq_tweezer_modulation

        n0 = shuttler_volt_to_mu(self.p.v_modulation_depth)
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

        self.sh_dds.set_waveform(b0=b0, b1=b1, b2=b2, b3=b3, c0=c0, c1=c1, c2=c2)
        self.sh_dds1.set_waveform(b0=b0, b1=b1, b2=b2, b3=b3, c0=c0, c1=c1, c2=c2)
        self.sh_trigger.trigger(0b11)

        self.tweezer.vva_dac.set(v=.0)
        self.tweezer.on()
        self.tweezer.vva_dac.set(v=5.)

        self.sh_relay.init()
        delay(1.)
        self.sh_relay.enable(0b11)
        self.ttl.pd_scope_trig.pulse(1.e-3)

        delay(2.)

        self.sh_relay.enable(0b00)
        # self.tweezer.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)