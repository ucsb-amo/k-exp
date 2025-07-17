from artiq.experiment import *
from artiq.experiment import delay
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.coredevice.ttl import TTLInOut, TTLOut
from artiq.coredevice.core import Core
from artiq.language.core import at_mu, now_mu
import csv
import os

class trap_frequency(EnvExperiment):

    def prepare(self):

        self.core = self.get_device('core')
        self.ttl_in = self.get_device('ttl0')
        self.ttl_out = self.get_device('ttl4')
        self.ttl_trig = self.get_device('ttl5')

        self.core: Core
        self.ttl_in: TTLInOut
        self.ttl_out: TTLOut
        self.ttl_trig: TTLOut
        self.T = 10
        self.a = 0

        self.t = np.zeros(1000, dtype=np.int64)
        self.idx = 0

    @kernel
    def get_time(self):
        self.t[self.idx] = now_mu()
        self.idx = self.idx + 1

    @kernel
    def run(self):
        self.core.reset()                    
        delay(1.e-3)        
        #self.slm.write_phase_mask_kernel(dimension=100.e-6, phase=1., x_center=100, y_center=10, mask_type='spot')
        # delay(1.e-4)
        self.ttl_in.input()
        self.ttl_out.output()
        delay(1.e-6)
        self.ttl_trig.pulse(1.e-6)  
        for _ in range(self.T):
            self.wait_for_TTL()
            delay(30.e-3)
        delay(1.e-3)
        #self.slm.write_phase_mask_kernel(dimension=1000.e-6, phase=0., x_center=900, y_center=600, mask_type='spot')

    @kernel
    def wait_for_TTL(self):          

                          
        
        # for i in range(self.T):
            
        t_end = self.ttl_in.gate_rising(50e-3)     #opens gate for rising edges to be detected on TTL0 for 10ms
                                                    #sets variable t_end as time(in MUs) at which detection stops
                                            
        t_edge = self.ttl_in.timestamp_mu(t_end)    #sets variable t_edge as time(in MUs) at which first edge is detected
        #                                             #if no edge is detected, sets
        #                                             #t_edge to -1
        # # aprint(i)                              
        if t_edge > 0:                          #runs if an edge has been detected
            at_mu(t_edge)                       #set time cursor to position of edge
            # self.get_time()
            delay(5.e-6)
            self.ttl_out.pulse(3.e-3)
        else:
            pass
        # t_edge = 1

        # while t_edge > 0:
        #     t_edge = self.ttl_in.timestamp_mu(t_end)
        #     if t_edge > 0:
        #         self.t[self.idx] = t_edge
        #         self.idx += 1
             
            # delay(10*us)        
        # aprint(self.a)

    # def analyze(self):
        # print(np.diff(self.t[:self.idx]))

        # # Define output CSV path
        # output_path = os.path.join(os.getcwd(), "trig_timestamps.csv")

        # # Write to CSV
        # with open(output_path, mode="w", newline="") as csvfile:
        #     writer = csv.writer(csvfile)
        #     writer.writerow(["idx", "time"])
        #     for idx, time in zip(range(self.idx),self.t):
        #         writer.writerow([idx, time])
        # print(f"Data written to {output_path}")
        
