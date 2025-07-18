from artiq.experiment import *
from artiq.experiment import delay
from artiq.coredevice.ttl import TTLInOut, TTLOut
from artiq.coredevice.core import Core, rtio_get_counter
from artiq.language.core import at_mu, now_mu
import numpy as np

class line_trigger(EnvExperiment):

    def prepare(self):

        # self.core = self.get_device('core')
        # self.ttl_in = self.get_device('ttl0')
        # self.ttl_out = self.get_device('ttl4')
        # self.ttl_trig = self.get_device('ttl5')

        self.core = self.get_device('core')
        self.ttl_in = self.get_device('ttl40')
        self.ttl_out = self.get_device('ttl21')
        self.ttl_trig = self.get_device('ttl16')

        self.core: Core
        self.ttl_in: TTLInOut
        self.ttl_out: TTLOut
        self.ttl_trig: TTLOut

        self.N = 1

        self.t = np.zeros(10000,dtype=np.int64)
        self.t2 = np.zeros(1000,dtype=np.int64)
        self.idx = 0
        self.idx2 = 0

        self.tries = np.ones(self.N,dtype=int)
        self.idx3 = 0

    @kernel
    def get_time(self):
        self.t[self.idx] = now_mu()
        self.idx = self.idx + 1

    @kernel
    def get_slack(self):
        self.t2[self.idx2] = now_mu() - rtio_get_counter()
        self.idx2 = self.idx2 + 1

    @kernel
    def run(self):

        self.core.reset()     

        self.get_slack()

        self.core.break_realtime()

        self.get_slack()

        delay(1.e-6)
        self.ttl_trig.pulse(1.e-6)  
        for _ in range(self.N):
            self.get_time()

            self.wait_for_TTL()

            self.get_time()
            self.get_slack()

            self.core.break_realtime()
            self.idx3 = self.idx3 + 1
        delay(1.e-3)

    @kernel
    def wait_for_TTL(self):          
        edge = False
        while not edge:
            t = now_mu()
            t_end = self.ttl_in.gate_rising(30e-3)      #opens gate for rising edges to be detected on TTL0 for 10ms
                                                        #sets variable t_end as time(in MUs) at which detection stops
                                                
            t_edge = self.ttl_in.timestamp_mu(t_end)    #sets variable t_edge as time(in MUs) at which first edge is detected
                                                        #if no edge is detected, sets
                                                        #t_edge to -1
            print(t_edge - t)
            if t_edge > 0:                          #runs if an edge has been detected
                edge = True
                at_mu(t_edge)                       #set time cursor to position of edge
                delay(5.e-6)
                # self.ttl_out.pulse(5.e-3)
            else:
                # print('hi')
                self.tries[self.idx3] = self.tries[self.idx3] + 1

    def analyze(self):
        dt = np.diff(self.t[self.t>0])
        print(dt)
        print(self.t2[self.t2!=0])
        print(self.tries)