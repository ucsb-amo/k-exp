import numpy as np

from artiq.coredevice import ad53xx
from artiq.experiment import kernel

import kexp.config.dds_state as dds_state
from kexp.control import DDS, DummyCore
from kexp.config.dac_id import dac_frame
from kexp.config.dds_calibration import DDS_Amplitude_Calibration
from kexp.config.dds_calibration import DDS_VVA_Calibration

from jax import AD9910Manager, RAMProfile, RAMType
from artiq.coredevice import ad9910

N_uru = 4
N_ch = 4
shape = (N_uru,N_ch)

RAMP_STEP_TIME = 100 * 4.e-9

default_dac_dds_amplitude = 0.3

def dds_empty_frame(x=None):
    return [[x for _ in range(N_ch)] for _ in range(N_uru)]

class dds_frame():
    '''
    Associates each dds in the dds_state file with a variable to be referenced in
    artiq experiments. Also, records the AOM order so that AOM frequencies can be
    determined from detunings.
    '''
    def __init__(self, dds_state = dds_state, dac_frame_obj:dac_frame = [], core = DummyCore()):

        self.core = core
        self.dds_manager = [DDSManager]
        self.dds_amp_calibration = DDS_Amplitude_Calibration()
        self.dds_vva_calibration = DDS_VVA_Calibration()
        self.ramp_dt = RAMP_STEP_TIME

        self._N_uru = N_uru
        self._N_ch = N_ch
        self._shape = shape
        self._default_dac_dds_amplitude = default_dac_dds_amplitude

        self._dds_state = dds_state

        if dac_frame_obj:
            self._dac_frame = dac_frame_obj
        else:
            self._dac_frame = dac_frame()

        self.dds_array = [[DDS(uru,ch,dac_device=self._dac_frame.dac_device) for ch in range(N_ch)] for uru in range(N_uru)]

        # self.aom_name = self.dds_assign(urukul_idx,ch_idx,ao_order,transition,dac_ch_vpd)
        self.push = self.dds_assign(0,0, ao_order = 1, transition = 'D2')
        self.d2_2d_r = self.dds_assign(0,1, ao_order = 1, transition = 'D2')
        self.d2_2d_c = self.dds_assign(0,2, ao_order = -1, transition = 'D2')
        self.d2_3d_r = self.dds_assign(0,3, ao_order = 1, transition = 'D2')
        self.d2_3d_c = self.dds_assign(1,0, ao_order = -1, transition = 'D2')
        self.optical_pumping = self.dds_assign(1,1, ao_order = -1, transition = 'D1')
        self.d1_3d_c = self.dds_assign(1,2, ao_order = -1, transition = 'D1',
                                        dac_ch_vpd = self._dac_frame.vva_d1_3d_c.ch)
        self.d1_3d_r = self.dds_assign(1,3, ao_order = 1, transition = 'D1',
                                        dac_ch_vpd = self._dac_frame.vva_d1_3d_r.ch)
        self.tweezer = self.dds_assign(2,0, 
                                       dac_ch_vpd = self._dac_frame.vva_tweezer.ch)
        self.beatlock_ref = self.dds_assign(2,1)
        self.imaging = self.dds_assign(2,2, ao_order = 1)
        self.lightsheet_paint = self.dds_assign(2,3)
        self.op_r = self.dds_assign(3,0, ao_order = 1, transition = 'D1')
        self.second_imaging = self.dds_assign(3,1, ao_order = -1, transition = 'D2')

        self.write_dds_keys()
        self.make_dds_array()
        self.dds_list = np.array(self.dds_array).flatten()
        
    def read_dds_state(self, uru, ch):
        try:
            idx = dds_state.ch.index((uru,ch))
            freq = dds_state.freq[idx] * 1.e6
            v_dac = dds_state.v_dac[idx]
            amplitude = dds_state.amplitude[idx]
        except:
            freq = 0.0
            amplitude = 0.0
            v_dac = 0.0
        return freq, amplitude, v_dac

    def dds_assign(self, uru, ch, ao_order=0, double_pass = True, transition='None', dac_ch_vpd=-1) -> DDS:
        '''
        Gets the DDS() object from the dds_state vector, sets the aom order, and
        returns the DDS() object.

        Returns
        -------
        DDS
        '''
        
        freq, amplitude, v_dac = self.read_dds_state(uru,ch)
        dds0 = DDS(urukul_idx=uru,ch=ch,frequency=freq,amplitude=amplitude,v_pd=v_dac)
        dds0.aom_order = ao_order
        dds0.transition = transition
        dds0.dac_ch = dac_ch_vpd
        dds0.dac_device = self._dac_frame.dac_device
        dds0.double_pass = double_pass

        self.dds_array[uru][ch] = dds0

        return dds0
    
    def write_dds_keys(self):
        '''Adds the assigned keys to the DDS objects so that the user-defined
        names (keys) are available with the DDS objects.'''
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],DDS):
                self.__dict__[key].key = key
    
    def make_dds_array(self):
        dds_linlist = [self.__dict__[key] for key in self.__dict__.keys() if isinstance(self.__dict__[key],DDS)]
        for dds in dds_linlist:
            self.dds_array[dds.urukul_idx][dds.ch] = dds

        all_idx = [(uru,ch) for uru in range(N_uru) for ch in range(N_ch)]
        key_idx = [(dds.urukul_idx,dds.ch) for dds in dds_linlist]
        non_key_idx = list(set(all_idx).difference(key_idx))
        for idx in non_key_idx:
            uru = idx[0]
            ch = idx[1]
            freq, amp, v_pd = self.read_dds_state(idx[0],idx[1])
            this_dds = DDS(uru,ch,freq,amp,v_pd,dac_device=self._dac_frame.dac_device)
            self.dds_array[uru][ch] = this_dds
            
    # def get_amplitude_ramp_list(self, t_ramp, power_i, power_f):
    #     dt = RAMP_STEP_TIME
    #     N = round(t_ramp / dt)
    #     if N > 1024:
    #         N = 1024
    #         self.ramp_dt = round( ( t_ramp / 1024 ) / 4.e-9 ) * 4.e-9
    #     p_list = np.linspace(power_i,power_f,N)
    #     amp_list = self.dds_amp_calibration.power_fraction_to_dds_amplitude(p_list).tolist()
    #     return amp_list
        
    # def set_amplitude_profile(self, dds:DDS, t_ramp:float, amp=-1., p_i=-1., p_f=-1., dwell_end=1):

    #     _power_specified = p_i > 0. and p_f > 0.
    #     _amp_specified = amp > 0.
    #     if (_power_specified and _amp_specified) or not (_power_specified or _amp_specified):
    #         raise ValueError("Either initial and final power, or constant amplitude should be specified. \
    #                           Either both or none were specified.")
        
    #     if _amp_specified and not _power_specified:
    #         amp_list = [amp]
    #     if _power_specified and not _amp_specified:
    #         amp_list = self.get_amplitude_ramp_list(t_ramp,p_i,p_f)

    #     this_profile = RAMProfile(
    #         dds.dds_device, amp_list, self.ramp_dt, RAMType.AMP, ad9910.RAM_MODE_RAMPUP, dwell_end=dwell_end)

    #     self.dds_manager.append(dds.dds_device, frequency_src=dds.frequency, amplitude_src=this_profile)
    
    # @kernel
    # def enable_profile(self):
    #     self.dds_manager.enable()
    #     self.dds_manager.commit_enable()

    # @kernel
    # def disable_profile(self):
    #     self.dds_manager.disable()
    #     self.dds_manager.commit_disable()
    
    # def get_ramp_dt(self, t_ramp):
    #     '''
    #     Returns the number of points to use in a ramp and the corresponding
    #     minimum timestep dt.
    #     '''
    #     dt = RAMP_STEP_TIME
    #     N_points = round(t_ramp / dt)
    #     if N_points > 1024:
    #         N_points = 1024
    #         ramp_dt = round( ( t_ramp / 1024 ) / 4.e-9 ) * 4.e-9
    #     else:
    #         ramp_dt = dt
    #     return N_points, ramp_dt

    def set_frequency_ramp_profile(self, dds:DDS, freq_list, t_ramp:float, dwell_end=True, dds_mgr_idx=0):
        """Define an amplitude ramp profile and append to the specified DDSManager object.

        Args:
            dds (DDS): the DDS object corresponding to the channel to be ramped.
            freq_list (ArrayLike): An ndarray or list of values over which to ramp.
            t_ramp (float): The time (in seconds) for the complete ramp.
            dwell_end (bool, optional): If True, after completing the ramp, the
            DDS will remain at the final value in freq_list. Otherwise, switches
            back to freq_list[0]. Defaults to True. 
            dds_mgr_idx (int, optional): The index of the DDSManager to use. By
            specifying different indices, one can define multiple ramp sequences
            to be used at different times during a sequence. Defaults to 0.
        """
        freq_list, dt_ramp = self.handle_ramp_input(freq_list,t_ramp,dds_mgr_idx)
        this_profile = RAMProfile(
            dds.dds_device, freq_list, dt_ramp, RAMType.FREQ, ad9910.RAM_MODE_RAMPUP, dwell_end=dwell_end)
        self.dds_manager[dds_mgr_idx].append_ramp(dds, frequency_src=this_profile, amplitude_src=dds.amplitude)
        
    def set_amplitude_ramp_profile(self, dds:DDS, amp_list, t_ramp:float, dwell_end=True, dds_mgr_idx=0):
        """Define an amplitude ramp profile and append to the specified DDSManager object.

        Args:
            dds (DDS): the DDS object corresponding to the channel to be ramped.
            amp_list (ArrayLike): An ndarray or list of values over which to ramp.
            t_ramp (float): The time (in seconds) for the complete ramp.
            dwell_end (bool, optional): If True, after completing the ramp, the
            DDS will remain at the final value in amp_list. Otherwise, switches
            back to amp_list[0]. Defaults to True. 
            dds_mgr_idx (int, optional): The index of the DDSManager to use. By
            specifying different indices, one can define multiple ramp sequences
            to be used at different times during a sequence. Defaults to 0.
        """        
        amp_list, dt_ramp = self.handle_ramp_input(amp_list,t_ramp,dds_mgr_idx)
        this_profile = RAMProfile(
            dds.dds_device, amp_list, dt_ramp, RAMType.AMP, ad9910.RAM_MODE_RAMPUP, dwell_end=dwell_end)
        self.dds_manager[dds_mgr_idx].append_ramp(dds, frequency_src=dds.frequency, amplitude_src=this_profile)

    def handle_ramp_input(self,value_list,t_ramp,dds_mgr_idx):
        if isinstance(value_list,np.ndarray):
            value_list = list(value_list)
        self.populate_dds_mgrs(dds_mgr_idx)
        N_points = len(value_list)
        if N_points > 1024:
            raise ValueError("Too many points!")
        dt_ramp = round( ( t_ramp / N_points ) / 4.e-9 ) * 4.e-9
        return value_list, dt_ramp

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
        
    def cleanup_dds_profiles(self):
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