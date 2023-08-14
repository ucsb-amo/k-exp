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
    def __init__(self, dds_state = dds_state, dac_device = [], core = DummyCore()):

        self.core = core
        self.dds_manager = [DDSManager]
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
        self.imaging_fake = self.dds_assign(1,1, ao_order = 1, transition = 'D2')
        self.d1_3d_c = self.dds_assign(1,2, ao_order = -1, transition = 'D1', dac_ch_vpd = 2)
        self.d1_3d_r = self.dds_assign(1,3, ao_order = 1, transition = 'D1', dac_ch_vpd = 1)
        self.tweezer = self.dds_assign(2,0, dac_ch_vpd=3)
        self.beatlock_ref = self.dds_assign(2,1)
        self.imaging = self.dds_assign(2,2, ao_order = 1)
        self.light_sheet = self.dds_assign(2,3, ao_order=-1)

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
        '''Adds the assigned keys to the DDS objects so that the user-defined
        names (keys) are available with the DDS objects.'''
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
        """Define an amplitude ramp profile and append to the specified DDSManager object.

        Args:
            dds (DDS): the DDS object corresponding to the channel to be ramped.
            freq_list (ArrayLike): An ndarray or list of values over which to ramp.
            dt_ramp (float): The time step (in seconds) between ramp values.
            Obtain from get_ramp_dt. 
            dwell_end (bool, optional): If True, after completing the ramp, the
            DDS will remain at the final value in freq_list. Otherwise, switches
            back to freq_list[0]. Defaults to True. 
            dds_mgr_idx (int, optional): The index of the DDSManager to use. By
            specifying different indices, one can define multiple ramp sequences
            to be used at different times during a sequence. Defaults to 0.
        """
        if isinstance(freq_list,np.ndarray):
            freq_list = list(freq_list)
        self.populate_dds_mgrs(dds_mgr_idx)
        this_profile = RAMProfile(
            dds.dds_device, freq_list, dt_ramp, RAMType.FREQ, ad9910.RAM_MODE_RAMPUP, dwell_end=dwell_end)
        self.dds_manager[dds_mgr_idx].append_ramp(dds, frequency_src=this_profile, amplitude_src=dds.amplitude)
        
    def set_amplitude_ramp_profile(self, dds:DDS, amp_list, dt_ramp:float, dwell_end=True, dds_mgr_idx=0):
        """Define an amplitude ramp profile and append to the specified DDSManager object.

        Args:
            dds (DDS): the DDS object corresponding to the channel to be ramped.
            amp_list (ArrayLike): An ndarray or list of values over which to ramp.
            dt_ramp (float): The time step (in seconds) between ramp values.
            Obtain from get_ramp_dt. 
            dwell_end (bool, optional): If True, after completing the ramp, the
            DDS will remain at the final value in amp_list. Otherwise, switches
            back to amp_list[0]. Defaults to True. 
            dds_mgr_idx (int, optional): The index of the DDSManager to use. By
            specifying different indices, one can define multiple ramp sequences
            to be used at different times during a sequence. Defaults to 0.
        """        
        if isinstance(amp_list,np.ndarray):
            amp_list = list(amp_list)
        self.populate_dds_mgrs(dds_mgr_idx)
        this_profile = RAMProfile(
            dds.dds_device, amp_list, dt_ramp, RAMType.AMP, ad9910.RAM_MODE_RAMPUP, dwell_end=dwell_end)
        self.dds_manager[dds_mgr_idx].append_ramp(dds, frequency_src=dds.frequency, amplitude_src=this_profile)

    def populate_dds_mgrs(self,dds_mgr_idx):
        '''Create a new DDSManager and add to the list if the specified number
        of DDSManagers does not yet exist.'''
        current_max_mgr_idx = len(self.dds_manager) - 1
        if dds_mgr_idx == current_max_mgr_idx + 1:
            self.dds_manager.append(DDSManager(core=self.core))
        elif dds_mgr_idx == current_max_mgr_idx:
            pass
        else:
            raise ValueError("Must add DDSManagers sequentially with index increasing from 0.")
        
    def cleanup_dds_ramps(self):
        '''Loops over all DDSManagers and adds single-tone RAM profiles for
        non-ramped DDS channels which share a card with a ramped DDS channel.'''
        for dds_mgr in self.dds_manager:
            dds_mgr.other_dds_to_single_tone_ram(dds_array=self.dds_array)

    @kernel
    def load_profile(self, dds_mgr_idx=0):
        self.dds_manager[dds_mgr_idx].load_profile()

    @kernel
    def enable_profile(self, dds_mgr_idx=0):
        '''Enable + commit enable -- activates a RAM profile and begins
        playback. Delay is dominated by enable, so if more precise timing is
        required, call enable ahead of time and follow with commit_enable when
        you want to begin the ramp.'''
        self.dds_manager[dds_mgr_idx].enable()
        self.dds_manager[dds_mgr_idx].commit_enable()

    @kernel
    def disable_profile(self, dds_mgr_idx=0):
        '''Enable + commit disable -- activates a RAM profile and begins
        playback. Delay is dominated by disable, so if more precise timing is
        required, call disable ahead of time and follow with disable when
        you want to begin the ramp.'''
        self.dds_manager[dds_mgr_idx].disable()
        self.dds_manager[dds_mgr_idx].commit_disable()

    @kernel
    def enable(self, dds_mgr_idx=0):
        '''Sets up but does not begin a ramp. Call commit_enable to start the
        RAM profile (profile 0).'''
        self.dds_manager[dds_mgr_idx].enable()

    @kernel
    def commit_enable(self, dds_mgr_idx=0):
        '''Starts a RAM playback after enable() has been called.'''
        self.dds_manager[dds_mgr_idx].commit_enable()

    @kernel
    def disable(self, dds_mgr_idx=0):
        '''
        Sets up the termination of but does not stop a ramp. Call RAM playback
        and switch back to the single-tone profile (profile 7).
        '''
        self.dds_manager[dds_mgr_idx].disable()

    @kernel
    def commit_disable(self, dds_mgr_idx=0):
        '''Stops a RAM playback after disable() has been called.'''
        self.dds_manager[dds_mgr_idx].commit_disable()

class DDSManager(AD9910Manager):
    def __init__(self,core=DummyCore()):
        super().__init__(core=core)
        self.DDS_with_ramps = []

    def append_ramp(self, dds:DDS, frequency_src=0.0, phase_src=0.0, amplitude_src=1.0):
        self.append(dds.dds_device, frequency_src=frequency_src, phase_src=phase_src, amplitude_src=amplitude_src)
        self.DDS_with_ramps.append(dds)

    def other_dds_to_single_tone_ram(self, dds_array):
        '''For DDS channels that are not being ramped which live on the same
        urukul card as one that has a ramp profile set in this DDSManager,
        define a RAM profile which is single-frequency, single-amplitude to
        maintain that channel's output when the RAM profiles for this DDSManager
        are enabled.'''

        # figure out which dds channels are being ramped on this DDSManager
        ch_with_ram = [(dds.urukul_idx,dds.ch) for dds in self.DDS_with_ramps]
        uru_with_ram = set([ch[0] for ch in ch_with_ram])

        # loop over the urukul cards which have a DDS being ramped
        for uru in uru_with_ram:
            all_ch = set([0,1,2,3])
            # figure out which channels on this urukul are being ramped
            ch_with_ram_on_this_uru = [ch[1] for ch in ch_with_ram if ch[0] == uru]
            # figure out which channels on this urukul are not being ramped
            ch_without_ram_on_this_uru = all_ch.difference(ch_with_ram_on_this_uru)
            # loop over those not being ramped
            for ch in ch_without_ram_on_this_uru:
                dds = dds_array[uru][ch]
                # append a single-frequency, single-amplitude RAM profile.
                self.append(dds.dds_device, frequency_src=dds.frequency, amplitude_src=dds.amplitude)