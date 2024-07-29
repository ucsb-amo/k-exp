from artiq.experiment import delay, kernel, TFloat
from artiq.coredevice.sampler import Sampler
import numpy as np

class Sampler_CH():
    def __init__(self,ch,sample_array:np.ndarray):
        self.ch = ch
        self.sampler_device = Sampler
        self.key = ""
        self.samples = sample_array

    @kernel
    def sample(self) -> TFloat:
        self.sampler_device.sample(self.samples)
        return self.samples[self.ch]