from artiq.experiment import delay, kernel, TFloat
from artiq.coredevice.sampler import Sampler
import numpy as np

di = -1

class Sampler_CH():
    def __init__(self,ch,
                 gain=0,
                 sample_array=np.zeros(8,dtype=float)):
        self.ch = ch
        self.gain = gain
        self.sampler_device = Sampler
        self.key = ""
        self.samples = sample_array

    @kernel
    def sample(self) -> TFloat:
        self.sampler_device.sample(self.samples)
        return self.samples[self.ch]
    
    @kernel
    def set_gain(self,gain=di):
        self.gain = gain if gain !=  di else self.gain
        self.sampler_device.set_gain_mu(self.ch,gain=self.gain)