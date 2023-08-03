import numpy as np

from artiq.coredevice import ad53xx
from artiq.experiment import kernel

from kexp.config.dds_state import dds_state
from kexp.control import DDS, DummyCore
from kexp.config.dds_calibration import DDS_Amplitude_Calibration

from jax import AD9910Manager, RAMProfile, RAMType
from artiq.coredevice import ad9910

N_uru = 3
N_ch = 4
shape = (N_uru,N_ch)

RAMP_STEP_TIME = 100 * 4.e-9

def dds_empty_frame(x=None):
    return [[x for _ in range(N_ch)] for _ in range(N_uru)]

class dds_frame():
    '''
    Associates each dds in the dds_state file with a variable to be referenced in
    artiq experiments. Also, records the AOM order so that AOM frequencies can be
    determined from detunings.
    '''
    def __init__(self, dds_state = dds_state, dac_device = []):

        self.core = DummyCore()
        # self.dds_manager = [AD9910Manager(core = self.core) for _ in range(2)]
        self.dds_manager = [AD9910Manager]
        self.dds_amp_calibration = DDS_Amplitude_Calibration()
        self.ramp_dt = RAMP_STEP_TIME

        self._N_uru = N_uru
        self._N_ch = N_ch
        self._shape = shape

        self._dds_state = dds_state

        if dac_device:
            self._dac_device = dac_device
        else:
            self._dac_device = ad53xx.AD53xx

        self.dds_array = dds_empty_frame()

        # self.aom_name = self.dds_assign(urukul_idx,ch_idx,ao_order,transition,dac_ch_vpd)
        self.push = self.dds_assign(0,0, ao_order = 1, transition = 'D2')
        self.d2_2d_r = self.dds_assign(0,1, ao_order = 1, transition = 'D2')
        self.d2_2d_c = self.dds_assign(0,2, ao_order = -1, transition = 'D2')
        self.d2_3d_r = self.dds_assign(0,3, ao_order = 1, transition = 'D2')
        self.d2_3d_c = self.dds_assign(1,0, ao_order = -1, transition = 'D2')
        self.old_imaging = self.dds_assign(1,1, ao_order = 1, transition = 'D2')
        self.d1_3d_c = self.dds_assign(1,2, ao_order = -1, transition = 'D1', dac_ch_vpd = 2)
        self.d1_3d_r = self.dds_assign(1,3, ao_order = 1, transition = 'D1', dac_ch_vpd = 1)
        self.tweezer = self.dds_assign(2,0, ao_order = 1)
        self.beatlock_ref = self.dds_assign(2,1)
        self.imaging = self.dds_assign(2,2, ao_order = 1)
        self.test_dds = self.dds_assign(2,3)

        self.write_dds_keys()
        self.dds_list = np.array(self.dds_array).flatten()

    def dds_assign(self, uru, ch, ao_order=0, transition='None', dac_ch_vpd=-1) -> DDS:
        '''
        Gets the DDS() object from the dds_state vector, sets the aom order, and
        returns the DDS() object.

        Returns
        -------
        DDS
        '''
        dds0 = self._dds_state[uru][ch]
        dds0.aom_order = ao_order
        dds0.transition = transition
        dds0.dac_ch = dac_ch_vpd
        dds0.dac_device = self._dac_device

        self.dds_array[uru][ch] = dds0

        return dds0
    
    def write_dds_keys(self):
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],DDS):
                self.__dict__[key].key = key
    
    def get_ramp_dt(self, t_ramp):
        '''
        Returns the number of points to use in a ramp and the corresponding
        minimum timestep dt.
        '''
        dt = RAMP_STEP_TIME
        N_points = round(t_ramp / dt)
        if N_points > 1024:
            N_points = 1024
            ramp_dt = round( ( t_ramp / 1024 ) / 4.e-9 ) * 4.e-9
        else:
            ramp_dt = dt
        return N_points, ramp_dt

    def set_frequency_ramp_profile(self, dds:DDS, freq_list, dt_ramp:float, dwell_end=True, dds_mgr_idx=0):
        if isinstance(freq_list,np.ndarray):
            freq_list = list(freq_list)
        this_profile = RAMProfile(
            dds.dds_device, freq_list, dt_ramp, RAMType.FREQ, ad9910.RAM_MODE_RAMPUP, dwell_end=dwell_end)
        self.dds_manager[dds_mgr_idx].append(dds.dds_device, frequency_src=this_profile, amplitude_src=dds.amplitude)
        
    def set_amplitude_ramp_profile(self, dds:DDS, amp_list, dt_ramp:float, dwell_end=True, dds_mgr_idx=0):
        if isinstance(amp_list,np.ndarray):
            amp_list = list(amp_list)
        this_profile = RAMProfile(
            dds.dds_device, amp_list, dt_ramp, RAMType.AMP, ad9910.RAM_MODE_RAMPUP, dwell_end=dwell_end)
        self.dds_manager[dds_mgr_idx].append(dds.dds_device, frequency_src=dds.frequency, amplitude_src=this_profile)
    
    @kernel
    def enable_profile(self, dds_mgr_idx=0):
        self.dds_manager[dds_mgr_idx].enable()
        self.dds_manager[dds_mgr_idx].commit_enable()

    @kernel
    def disable_profile(self, dds_mgr_idx=0):
        self.dds_manager[dds_mgr_idx].disable()
        self.dds_manager[dds_mgr_idx].commit_disable()