import numpy as np

from artiq.coredevice import ad53xx
from artiq.experiment import kernel, portable
from artiq.language.core import delay_mu

from waxx.control.artiq.DDS import DDS
from waxx.config.dds_id import dds_frame as dds_frame_waxx
from waxx.control.artiq.dummy_core import DummyCore

from kexp.config.dac_id import dac_frame

# from jax import AD9910Manager, RAMProfile, RAMType
from artiq.coredevice import ad9910

from kexp.config.expt_params import ExptParams

N_uru = 1
N_ch = 4
shape = (N_uru,N_ch)

# default_dac_dds_amplitude = 0.3

dv = -0.1

class dds_frame(dds_frame_waxx):
    '''
    Associates each dds with a instance of the DDS class for use in experiments.
    Also, records the AO order, DAC channels associated with VVA/PID set points,
    associated transition for detuning calulations, and default
    frequency/amplitudes.
    '''
    def __init__(self, expt_params = ExptParams(),
                  dac_frame_obj = dac_frame(),
                  core = DummyCore()):
        
        from kexp.util.db.device_db import device_db
        self._db = device_db
        
        self.setup(expt_params, core, N_uru, N_ch, shape, dac_frame_obj)
        self.p:ExptParams
        self._dac_frame:dac_frame

        self.antenna_rf = self.dds_assign(0,0,
                                    default_freq=200.e6,
                                    default_amp=self.p.amp_rf_source)
        
        self.cleanup()