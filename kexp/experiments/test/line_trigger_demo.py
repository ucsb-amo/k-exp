from artiq.experiment import *
from artiq.experiment import delay
from artiq.coredevice.ttl import TTLInOut, TTLOut
from artiq.coredevice.core import Core
from artiq.language.core import at_mu

class line_trigger(EnvExperiment):

    def prepare(self):

        self.core = self.get_device('core')
        self.ttl_in = self.get_device('ttl0')
        self.ttl_out = self.get_device('ttl4')
        self.ttl_trig = self.get_device('ttl5')

        self.core: Core
        self.ttl_in: TTLInOut
        self.ttl_out: TTLOut
        self.ttl_trig: TTLOut

    @kernel
    def run(self):
        self.core.reset()          
        delay(1.e-6)
        self.ttl_trig.pulse(1.e-6)  
        for _ in range(10):
            self.wait_for_TTL()
            delay(30.e-3)
        delay(1.e-3)

    @kernel
    def wait_for_TTL(self):          

        t_end = self.ttl_in.gate_rising(50e-3)     #opens gate for rising edges to be detected on TTL0 for 10ms
                                                    #sets variable t_end as time(in MUs) at which detection stops
                                            
        t_edge = self.ttl_in.timestamp_mu(t_end)    #sets variable t_edge as time(in MUs) at which first edge is detected
        #                                             #if no edge is detected, sets
        #                                             #t_edge to -1

        if t_edge > 0:                          #runs if an edge has been detected
            at_mu(t_edge)                       #set time cursor to position of edge
            delay(5.e-6)
            self.ttl_out.pulse(3.e-3)
        else:
            pass