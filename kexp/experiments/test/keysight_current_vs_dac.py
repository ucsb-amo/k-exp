from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from artiq.coredevice.sampler import Sampler

import vxi11
import time

class tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,save_data=False,setup_camera=False,camera_select='xy_basler')

        self.sampler = self.get_device("sampler0")
        self.sampler: Sampler

        self.N = 500
        self.sample = [0.]*8

        self.v_dac_scan = np.linspace(0.,1.,self.N)

        self.xvar('keysight_500A_dac',self.v_dac_scan)
        
        self.results = np.zeros(self.N,dtype=float)
        self.idx = 0
        
        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.core.break_realtime()
        
        self.outer_coil.i_control_dac.set(self.p.keysight_500A_dac)
        delay(100*ms)
        self.ttl.pd_scope_trig.on()
        self.core.break_realtime()
        self.sampler.sample(self.sample)
        self.core.break_realtime()
        print(self.sample[0])
        self.core.break_realtime()
        self.results[self.idx] = self.sample[0]
        self.ttl.pd_scope_trig.off()
        self.core.break_realtime()
        self.idx += 1

    @kernel
    def run(self):
        self.init_kernel()
        self.sampler.init()

        n_ch = 8
        for i in range(n_ch):
            self.sampler.set_gain_mu(i,0)
        self.core.break_realtime()
        
        self.inner_coil.off()
        self.outer_coil.igbt_ttl.on()
        self.outer_coil.i_control_dac.set(0.)
        self.outer_coil.v_control_dac.set(9.)
        delay(1*s)
        self.scan()
        self.outer_coil.v_control_dac.set(0.)
        self.outer_coil.i_control_dac.set(0.)
        delay(1*s)
        self.outer_coil.off()

    def analyze(self):

        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

        import pandas as pd

        current_measured = self.results * 60 # transfer ratio 60 A
        self.accuracy = (0.00005) * self.results + (0.000015 + 0.00001) * 600 # accuracy from datasheet

        df = pd.DataFrame({"voltage": self.v_dac_scan, "voltage_measured":self.results, "current":current_measured, "accuracy":self.accuracy})
        output_file = "keysight500A_DAC_calibration.csv"
        df.to_csv(output_file,index=False)

        print('Done!')


