from artiq.experiment import *
from artiq.experiment import delay
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.coredevice.ttl import TTLInOut, TTLOut
from artiq.coredevice.core import Core
from artiq.language.core import at_mu, now_mu
from artiq.coredevice.sampler import Sampler
import csv
import os

class trap_frequency(EnvExperiment):

    def prepare(self):

        self.core = self.get_device('core')
        self.ttl_in = self.get_device('ttl0')
        self.ttl_out = self.get_device('ttl4')

        self.sampler = self.get_device("sampler0")
        self.sampler: Sampler
        self.data = np.zeros(8)

        self.dt = 25.e-6
        T = 100.e-3
        self.N = int(T/self.dt)
        self.readings = np.zeros(self.N)
        self.t = np.zeros(self.N,dtype=np.int64)

        self.core: Core
        self.ttl_in: TTLInOut
        self.ttl_out: TTLOut

    @kernel
    def run(self):
        self.core.reset()

        for i in range(len(self.data)):
            self.sampler.set_gain_mu(i,0)

        self.core.break_realtime()

        t0 = now_mu()

        for i in range(self.N):
            self.t[i] = now_mu() - t0
            self.sampler.sample(self.data)
            self.readings[i] = self.data[0]
            delay(self.dt)
        
    def analyze(self):

        # Define output CSV path
        output_path = os.path.join(os.getcwd(), "readings.csv")

        # Write to CSV
        with open(output_path, mode="w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["timestamp", "reading"])
            for timestamp, reading in zip(self.t, self.readings):
                writer.writerow([timestamp, reading])
        print(f"Data written to {output_path}")