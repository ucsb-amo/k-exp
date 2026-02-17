import numpy as np
from artiq.experiment import kernel, TFloat, TArray
from artiq.coredevice.sampler import Sampler

from waxx.config.sampler_id import sampler_frame as sampler_frame_waxx
from waxx.control.artiq.Sampler_CH import Sampler_CH

class sampler_frame(sampler_frame_waxx):
    def __init__(self, sampler_device = Sampler):

        self.setup(sampler_device)
        
        ### begin assignments
 
        self.reference_beam_pd = self.sampler_assign(0,gain=0)

        ### end assignments

        self.cleanup()