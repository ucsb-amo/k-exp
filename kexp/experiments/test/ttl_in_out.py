from artiq.experiment import *
from artiq.experiment import delay
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.coredevice.ttl import TTLInOut, TTLOut
from artiq.coredevice.core import Core
from artiq.language.core import at_mu
from kexp.control.slm.slm import SLM

class trap_frequency(EnvExperiment):

    def prepare(self):

        self.core = self.get_device('core')
        self.ttl_in = self.get_device('ttl0')
        self.ttl_out = self.get_device('ttl4')

        self.core: Core
        self.ttl_in: TTLInOut
        self.ttl_out: TTLOut
        self.T = 20
        self.a = 0
        self.slm = SLM(core=self.core)

    @kernel
    def wait_until_trigger(self):
        did_a_ttl_happen = False
        while did_a_ttl_happen == False:
            self.ttl_in.watch_stay_on()
            delay(10.e-3)
            did_a_ttl_happen = not self.ttl_in.watch_done()
            delay(1.e-6)
            
    @kernel
    def run(self):
        self.core.reset()                    
        delay(1.e-3)        
        self.slm.write_phase_mask_kernel(dimension=100.e-6, phase=1., x_center=100, y_center=10, mask_type='spot')
        # delay(1.e-4)
        self.wait_for_SLM()
        delay(1.e-3)
        self.slm.write_phase_mask_kernel(dimension=1000.e-6, phase=0., x_center=900, y_center=600, mask_type='spot')
        

    @kernel
    def wait_for_SLM(self):                              
        
        for i in range(self.T):
            
           
            t_end = self.ttl_in.gate_falling(100e-3)      #opens gate for rising edges to be detected on TTL0 for 10ms
                                                        #sets variable t_end as time(in MUs) at which detection stops
                                                
            t_edge = self.ttl_in.timestamp_mu(t_end)    #sets variable t_edge as time(in MUs) at which first edge is detected
                                                        #if no edge is detected, sets
                                                        #t_edge to -1
            # aprint(i)                              
            if t_edge < 0:                          #runs if an edge has been detected
                at_mu(t_edge)                       #set time cursor to position of edge
                # delay(5*us)   
                # self.ttl6.pulse(5*ms)               #outputs 5ms pulse on TTL6
                self.a = i
                aprint("hi")
                break
            else:
                # aprint("off")
                if i == self.T:
                    raise ValueError("SLM is not ready for next uploading")
             
            delay(10*us)        
        aprint(self.a)

    def analyze(self):
        pass

    # @kernel
    # def Trigger(self):
    #     period = 10e-3
    #     duty_cycle = 1/10
    #     cycles = 1000
    #     for _ in range(cycles):
    #         self.ttl_out.on()
    #         delay(period*duty_cycle)
    #         self.ttl_out.off()
    #         delay(period*(1-duty_cycle))
            
    # @kernel
    # def Detect(self):
    #     # state = self.ttl_in.input()
    #     v = self.ttl_in.watch_stay_on()
    #     # v = self.ttl_in.sample_get()
    #     aprint(v)
    #     delay(100.e-3)
    #     # if (state):
    #     #     return 1
    #     # else:
    #     #     print('off')
    #     self.ttl_in.watch_done()

    # @kernel
    # def run(self):
    #     self.core.reset()
    #     delay(1.e-3)
    #     # self.Detect()
    #     # v = self.ttl_in.watch_stay_off()
    #     # delay(1.e-3)
    #     # self.Trigger()
    #     # self.ttl_out.on()
    #     # aprint(v)
    #     # delay(1.e-3)
    #     # self.ttl_out.off()
    #     # aprint(self.ttl_in.watch_done())

    #     # write slm command ()
    #     self.wait_until_trigger()
    #     # now experiment

