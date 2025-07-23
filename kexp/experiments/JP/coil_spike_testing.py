from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp import Base, img_types, cameras

T32 = 1<<32

class coil_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)
        # self.xvar('do_discharge',[0,1]*5)
        self.p.do_discharge = 1

        n = 20
        i_max = 10.
        v = self.outer_coil.current_to_supply_vdac(np.array([i*i_max/(n-1) for i in range(n)]))
        print(v)
        self.xvar('v',[v[-2]])

        self.finish_prepare(shuffle=False)
        
    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    @kernel
    def scan_kernel(self):

        if self.p.do_discharge:
            self.outer_coil.discharge()
            # self.outer_coil.discharge_igbt_ttl.on()
            # self.outer_coil.rampdown()
            # self.outer_coil.set_voltage(0.)
            # self.outer_coil.set_supply(0.)
            # delay(100.e-3)
            # self.outer_coil.discharge_igbt_ttl.off()

        delay(100.e-3)

        self.outer_coil.on()
        # self.outer_coil.set_voltage(10.)
        v_0 = 0.
        v_f = 10.
        n = 100
        t = 100.e-3
        # for i in range(n):
        #     dt = t/n
        #     dv_supply = (v_f - v_0)/(n-1)
        #     v_i = self.outer_coil.supply_voltage_to_dac_voltage(v_0 + i*dv_supply)
        #     self.outer_coil.v_control_dac.set(v=v_i)
        #     delay(dt)
        self.outer_coil.set_voltage(10.)
        self.outer_coil.set_supply(0.)
        delay(100.e-3)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.outer_coil.ramp_supply(t=1000.e-3, i_start=0., i_end=30.)
        self.outer_coil.set_supply(self.p.v)
        delay(100.e-3)
        # self.outer_coil.rampdown()
        # delay(100.e-3)
        self.outer_coil.igbt_ttl.off()