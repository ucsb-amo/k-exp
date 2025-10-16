import numpy as np
from artiq.experiment import kernel, TFloat, TArray
from artiq.coredevice.sampler import Sampler
from wax.control.artiq.Sampler_CH import Sampler_CH

class sampler_frame():
    def __init__(self, sampler_device = Sampler):

        self.sampler_device = sampler_device
        self.samples = np.zeros(8,dtype=float)
        self.gains = np.zeros(8,dtype=int)
        
        ### begin assignments
 
        self.test = self.sampler_assign(0,gain=3)

        ### end assignments

        self._write_sampler_keys()

    def sampler_assign(self,ch,gain=0) -> Sampler_CH:
        this_ch = Sampler_CH(ch,gain=gain,sample_array=self.samples)
        this_ch.sampler_device = self.sampler_device
        self.gains[ch] = gain
        return this_ch
    
    def _write_sampler_keys(self):
        '''Adds the assigned keys to the DDS objects so that the user-defined
        names (keys) are available with the DDS objects.'''
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],Sampler_CH):
                self.__dict__[key].key = key
                
    @kernel
    def sample(self):
        self.sampler_device.sample(self.samples)
    
    @kernel
    def init(self):
        self.sampler_device.init()
        for ch in range(8):
            self.sampler_device.set_gain_mu(ch,self.gains[ch])