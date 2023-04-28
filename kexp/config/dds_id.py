import numpy as np

from artiq.coredevice import ad9910
from artiq.experiment import kernel

from kexp.config.dds_state import dds_state
from kexp.control.artiq.DDS import DDS
from kexp.config.dds_calibration import DDS_Calibration

from jax import AD9910Manager, RAMProfile, RAMType

N_uru = 2
N_ch = 4
shape = (N_uru,N_ch)

RAMP_STEP_TIME = 100 * 4.e-9

def dds_empty_frame():
    return [[None for _ in range(N_ch)] for _ in range(N_uru)]

class dds_frame():
    '''
    Associates each dds in the dds_state file with a variable to be referenced in
    artiq experiments. Also, records the AOM order so that AOM frequencies can be
    determined from detunings.
    '''
    def __init__(self, dds_state = dds_state):

        self.dds_manager = AD9910Manager
        self.dds_calibration = DDS_Calibration()

        self._N_uru = N_uru
        self._N_ch = N_ch
        self._shape = shape

        self._dds_state = dds_state

        self._aom_order = dds_empty_frame()
        # self._aom_order[urukul_idx][ch_idx] = order
        self._aom_order[0][0] = 1
        self._aom_order[0][1] = 1
        self._aom_order[0][2] = -1
        self._aom_order[0][3] = 1
        self._aom_order[1][0] = -1
        self._aom_order[1][1] = 1
        self._aom_order[1][2] = -1
        self._aom_order[1][3] = 1

        self._transition = dds_empty_frame()
        self._transition[0][0] = 'D2'
        self._transition[0][1] = 'D2'
        self._transition[0][2] = 'D2'
        self._transition[0][3] = 'D2'
        self._transition[1][0] = 'D2'
        self._transition[1][1] = 'D2'
        self._transition[1][2] = 'D1'
        self._transition[1][3] = 'D1'

        # self.aom_name = self.dds_assign(urukul_idx,ch_idx)
        self.push = self.dds_assign(0,0)
        self.d2_2d_r = self.dds_assign(0,1)
        self.d2_2d_c = self.dds_assign(0,2)
        self.d2_3d_r = self.dds_assign(0,3)
        self.d2_3d_c = self.dds_assign(1,0)
        self.imaging = self.dds_assign(1,1)
        self.d1_3d_c = self.dds_assign(1,2)
        self.d1_3d_r = self.dds_assign(1,3)

    def dds_assign(self, uru, ch) -> DDS:
        '''
        Gets the DDS() object from the dds_state vector, sets the aom order, and
        returns the DDS() object.

        Returns
        -------
        DDS
        '''
        dds0 = self._dds_state[uru][ch]
        dds0.aom_order = self._aom_order[uru][ch]
        dds0.transition = self._transition[uru][ch]
        return dds0
    
    def dds_list(self):
        '''
        Returns a list of all dds objects in 
        '''
        return [self.__dict__[key] for key in self.__dict__.keys() if isinstance(self.__dict__[key],DDS)]
        
    def set_amplitude_profile(self, dds:DDS, t_ramp:float, amp=-1., p_i=-1., p_f=-1., dwell_end=1):

        _power_specified = p_i < 0. and p_f < 0.
        _amp_specified = amp < 0.
        if (_power_specified and _amp_specified) or not (_power_specified or _amp_specified):
            raise ValueError("Either initial and final power, or constant amplitude should be specified. \
                              Either both or none were specified.")
        
        if _amp_specified and not _power_specified:
            amp_list = [amp]
        if _power_specified and not _amp_specified:
            amp_list = self.get_amplitude_ramp_list(t_ramp,p_i,p_f)
        
        this_profile = RAMProfile(
            dds, amp_list, RAMP_STEP_TIME, RAMType.AMP, ad9910.RAM_MODE_RAMPUP, dwell_end=dwell_end)

        self.dds_manager.append(dds.dds_device, frequency_src=dds.frequency, amplitude_src=this_profile)
        
    def get_amplitude_ramp_list(self, t_ramp, power_i, power_f):
      dt = RAMP_STEP_TIME
      N = round(t_ramp / dt)
      p_list = np.linspace(power_i,power_f,N)
      amp_list = self.dds_calibration.power_fraction_to_dds_amplitude(p_list).tolist()
      return amp_list
    
    @kernel
    def enable_profile(self):
        self.dds_manager.enable()
        self.dds_manager.commit_enable()

    @kernel
    def disable_profile(self):
        self.dds_manager.disable()
        self.dds_manager.commit_disable()
        

        

