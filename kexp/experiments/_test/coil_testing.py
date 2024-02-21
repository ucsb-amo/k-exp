from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint

import numpy as np

class test(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False)

        self.v_list = np.linspace(0.,9.99,100)
        self.vi_list = np.linspace(0.,3.00,100)

        self.v_list0 = zip(self.v_list,self.vi_list)

        # self.vs = np.linspace(0.,6.,7)
        self.vs = [9., 9.]
        self.ts = [0.1,1.,3.,6.]
        # self.ts = [1.]

        # self.t_dumps = np.linspace(0.5,5.,5) * 1.e-3
        # self.t_offs = np.linspace(1,10.,5) * 1.e-3
        # self.t_offs = 7.e-3

        self.finish_build(shuffle=False)

    @kernel
    def contactor_close(self,t):
        '''
        Closes the contactor time t. Minimum close time is t_close, otherwise
        the contactor does nothing.

        Leaves the timeline cursor at the now_mu() + t.
        '''
        t_close = t
        t_on_delay_max = 25*ms
        t_off_delay = 6*ms
        if t_close < 6*ms:
            aprint("pulse time is too short for the contactor, probably didn't close")
        t_ttl = t + t_on_delay_max - t_off_delay
        delay(-t_on_delay_max)
        self.ttl.inner_coil_contactor.pulse(t_ttl)
        delay(t_off_delay)

    @kernel
    def run(self):
        
        self.init_kernel()

        for _ in range(1):

            self.dac.inner_coil_supply_voltage.set(0.0)
            self.dac.inner_coil_supply_current.set(0.0)
            
            self.ttl.pd_scope_trig.on()
            self.ttl.inner_coil_igbt.on()

            self.dac.inner_coil_supply_voltage.set(9.)
            self.dac.inner_coil_supply_current.set(1.)
            delay(40*ms)
            self.ttl.inner_coil_igbt.off()
            self.ttl.pd_scope_trig.off()

            delay(20*ms)
            
            delay(-15*ms)
            self.dac.inner_coil_supply_current.set(0.0)
            self.dac.inner_coil_supply_voltage.set(0.0)
            delay(15*ms)
                
            self.ttl.pd_scope_trig.on()
            self.contactor_close(6*ms)
            # delay(6*ms)
            self.ttl.pd_scope_trig.off()

            delay(5*ms)

            self.ttl.pd_scope_trig.on()
            self.ttl.inner_coil_igbt.on()
            delay(10*ms)
            self.ttl.inner_coil_igbt.off()
            self.ttl.pd_scope_trig.off()

            delay(1.5*s)
        
        
    def analyze(self):

        print("Done!")