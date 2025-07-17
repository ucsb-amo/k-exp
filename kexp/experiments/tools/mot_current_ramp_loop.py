from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.base.base import Base
import numpy as np
import msvcrt

class MOTCurrentRamp(EnvExperiment,Base):
    def prepare(self):
        Base.__init__(self,setup_camera=False)
        self.core_dma = self.get_device("core_dma")
        self.ch = self.dac.inner_coil_supply_current.ch

        v0 = 1.17
        V1 = v0 - 0.3
        V2 = v0 + 0.5
        T_half = 2
        fs = 50
        self.N = int(2 * T_half * fs)
        self.dt = 1/fs

        Nhalf = int(self.N/2)
        self.vs = np.linspace(V1,V2,Nhalf)
        self.vs = np.append(self.vs, np.linspace(V2,V1,Nhalf))

        self.keep_running = True

    @kernel
    def record(self):
        with self.core_dma.record("ramp"):

            for vidx in range(self.N):
                
                v = self.vs[vidx]
                self.dac.dac_device.write_dac(self.ch,v)
                self.dac.dac_device.load()

                if vidx != 0:
                    delay(self.dt * s)

    @kernel
    def run(self):
        self.init_kernel()
        self.core.break_realtime()
        self.mot_observe()

        self.record()

        ramp_handle = self.core_dma.get_handle("ramp")
        self.core.break_realtime()
        
        for i in range(30):
            self.core_dma.playback_handle(ramp_handle)