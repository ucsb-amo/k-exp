import numpy as np

from artiq.coredevice import ad53xx
from artiq.experiment import kernel, portable
from artiq.language.core import delay_mu

from wax.control.artiq.DDS import DDS
from wax.control.artiq.dummy_core import DummyCore

from kexp.config.dac_id import dac_frame
from kexp.config.shuttler_id import shuttler_frame
from kexp.config.dds_calibration import DDS_Amplitude_Calibration
from kexp.config.dds_calibration import DDS_VVA_Calibration

# from jax import AD9910Manager, RAMProfile, RAMType
from artiq.coredevice import ad9910

from kexp.config.expt_params import ExptParams

N_uru = 6
N_ch = 4
shape = (N_uru,N_ch)

RAMP_STEP_TIME = 100 * 4.e-9

# default_dac_dds_amplitude = 0.3

dv = -0.1
d_exptparams = ExptParams()

def dds_empty_frame(x=None):
    return [[x for _ in range(N_ch)] for _ in range(N_uru)]

class dds_frame():
    '''
    Associates each dds with a instance of the DDS class for use in experiments.
    Also, records the AO order, DAC channels associated with VVA/PID set points,
    associated transition for detuning calulations, and default
    frequency/amplitudes.
    '''
    def __init__(self, expt_params:ExptParams=d_exptparams,
                  dac_frame_obj:dac_frame = [],
                  shuttler_frame_obj:shuttler_frame = [],
                  core = DummyCore()):
        
        self.p = expt_params

        self._N_uru = N_uru
        self._N_ch = N_ch
        self._shape = shape

        if dac_frame_obj:
            self._dac_frame = dac_frame_obj
        else:
            self._dac_frame = dac_frame()

        self.dds_array = [[DDS(uru,ch,dac_device=self._dac_frame.dac_device) for ch in range(N_ch)] for uru in range(N_uru)]

        # self.aom_name = self.dds_assign(urukul_idx,ch_idx,ao_order,transition,dac_ch_vpd)
        self.antenna_rf = self.dds_assign(0,0,default_freq=200.e6,default_amp=self.p.amp_rf_source)
        self.push = self.dds_assign(2,0, ao_order = 1, transition = 'D2',
                                    default_detuning = self.p.detune_push,
                                    default_amp = self.p.amp_push)
        # old 2d MOT AOs
        self.d2_2dv_r = self.dds_assign(2,1, ao_order = 1, transition = 'D2',
                                    default_detuning = self.p.detune_d2v_r_2dmot,
                                    default_amp = self.p.amp_d2v_r_2dmot)
        self.d2_2dv_c = self.dds_assign(2,2, ao_order = -1, transition = 'D2',
                                    default_detuning = self.p.detune_d2v_c_2dmot,
                                    default_amp = self.p.amp_d2v_c_2dmot)
        # old 3d MOT AOs
        self.d2_2dh_r = self.dds_assign(2,3, ao_order = 1, transition = 'D2',
                                    default_detuning = self.p.detune_d2h_r_2dmot,
                                    default_amp = self.p.amp_d2h_r_2dmot)
        self.d2_2dh_c = self.dds_assign(3,0, ao_order = -1, transition = 'D2',
                                    default_detuning = self.p.detune_d2h_c_2dmot,
                                    default_amp = self.p.amp_d2h_c_2dmot)
        self.mot_killer = self.dds_assign(3,1, ao_order = -1, transition = 'D2',
                                    default_detuning = 0.,
                                    default_amp = 0.188)
        self.beatlock_ref = self.dds_assign(3,2,
                                            default_freq=42.26e6,
                                            default_amp=0.1)
        self.d1_3d_c = self.dds_assign(3,3, ao_order = -1, transition = 'D1',
                                    dac_ch_vpd = self._dac_frame.vva_d1_3d_c.ch,
                                    default_detuning = self.p.detune_d1_c_gm,
                                    default_amp = self.p.amp_d1_3d_c)
        self.d1_3d_r = self.dds_assign(4,0, ao_order = 1, transition = 'D1',
                                    dac_ch_vpd = self._dac_frame.vva_d1_3d_r.ch,
                                    default_detuning = self.p.detune_d1_r_gm,
                                    default_amp = self.p.amp_d1_3d_r)
        self.imaging = self.dds_assign(4,1, ao_order = 1,
                                    default_freq = self.p.frequency_ao_imaging,
                                    default_amp = 1.0) #0.54)
        # self.op_r = self.dds_assign(4,2, ao_order = 1, transition = 'D1',
        #                             default_detuning = self.p.detune_optical_pumping_op,
        #                             default_amp = self.p.amp_optical_pumping_op)

        self.raman_minus = self.dds_assign(4,2, ao_order = 1,
                                    default_freq = self.p.frequency_raman_minus,
                                    default_amp = self.p.amp_raman)
        self.raman_plus = self.dds_assign(5,3, ao_order = 1,
                                    default_freq = self.p.frequency_raman_plus,
                                    default_amp = self.p.amp_raman)
        
        self.optical_pumping = self.dds_assign(4,3, ao_order = -1, transition = 'D1',
                                    default_detuning = self.p.detune_optical_pumping_r_op,
                                    default_amp = self.p.amp_optical_pumping_r_op)
        self.tweezer_pid_1 = self.dds_assign(0,3, ao_order = 1,
                                    default_freq = 80.e6,
                                    dac_ch_vpd = self._dac_frame.v_pd_tweezer_pid1.ch,
                                    default_amp = self.p.amp_tweezer_pid1)
        self.tweezer_pid_2 = self.dds_assign(1,0, ao_order = 1,
                                    default_freq = 200.e6,
                                    dac_ch_vpd = self._dac_frame.v_pd_tweezer_pid2.ch,
                                    default_amp = self.p.amp_tweezer_pid2)
        self.imaging_eo = self.dds_assign(1,1,
                                    default_freq = 1.e6,
                                    default_amp = 0.)
        self.d1_probe = self.dds_assign(5,0,
                                    default_freq=100.e6,
                                    default_amp=0.21)
        self.d1_beatlock_ref = self.dds_assign(5,1,
                                    default_freq=42.26e6,
                                    default_amp=0.1)
        self.d1_blueshield = self.dds_assign(5,2,
                                    default_freq=150.e6,
                                    default_amp=0.21)
        self.d2_3d_c = self.dds_assign(1,2, ao_order = -1, transition = 'D2',
                                    default_detuning = self.p.detune_d2_c_mot,
                                    default_amp = self.p.amp_d2_c_mot)
        self.d2_3d_r = self.dds_assign(1,3, ao_order = 1, transition = 'D2',
                                    default_detuning = self.p.detune_d2_r_mot,
                                    default_amp = self.p.amp_d2_r_mot)

        self.core = core
        # self.dds_manager = [DDSManager]
        self.dds_amp_calibration = DDS_Amplitude_Calibration()
        self.dds_vva_calibration = DDS_VVA_Calibration()
        self.ramp_dt = RAMP_STEP_TIME

        self.write_dds_keys()
        self.make_dds_array()
        self.dds_list = np.array(self.dds_array).flatten()

        self.stash_defaults()

    def dds_assign(self, uru, ch, 
                   default_freq=dv, default_detuning=dv, default_amp=dv, 
                   ao_order=0, double_pass = True, transition='None', dac_ch_vpd=-1) -> DDS:
        """Instantiates and returns a DDS object for the given urukul and channel.

        Args:
            uru (int): The urukul card index. 0-indexed.
            ch (int): The channel of this DDS. 0-indexed.
            default_freq (float, optional): The default frequency (in Hz) to
            which this DDS channel should turn on.
            default_detuning (float, optional): The default detuning (in
            linewidths) to which this DDS channel should turn on.
            default_amp (_type_, optional): The default amplitude (0 to 1) to
            which this DDS channel should turn on.
            ao_order (int, optional): Specifies the AO order (if applicable) as
            either +1 or -1.
            double_pass (bool, optional): Specifies if the AO is set up as a
            double pass for detuning calculations. Defaults to True.
            transition (str, optional): If the AO controls near-resonant light,
            specify the transition ('D1' or 'D2'). Defaults to 'None'.
            dac_ch_vpd (int, optional): If controlling an AO with a VVA in line
            with the DDS, this should specify the DAC channel number which
            controls that VVA. For no DAC control, leave as -1.

        Returns:
            DDS
        """        

        dds0 = DDS(urukul_idx=uru,ch=ch,
                   frequency=default_freq,
                   amplitude=default_amp,
                   v_pd=5.0)
        dds0.aom_order = ao_order
        dds0.transition = transition
        dds0.dac_ch = dac_ch_vpd
        dds0.dac_device = self._dac_frame.dac_device
        dds0.double_pass = double_pass

        # set the frequency according to detuning if default_detuning was specified instead of default_freq
        if default_detuning != dv and default_freq == dv:
            freq = dds0.detuning_to_frequency(default_detuning)
            dds0.frequency = freq
        elif default_detuning != dv and default_freq != dv:
            raise ValueError("Only one of default_detuning and default_freq must be set in dds_id.py.")

        self.dds_array[uru][ch] = dds0

        return dds0
    
    def write_dds_keys(self):
        """Adds the assigned keys to the DDS objects so that the user-defined
        names (keys) are available with the DDS objects."""
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],DDS):
                self.__dict__[key].key = key
    
    def make_dds_array(self):
        """Creates an array of shape (N_uru,N_ch) containing DDS objects for
        each channel.

        First loops through the DDS objects that were explicitly assigned as
        attributes using dds_assign, then fills in the remaining DDS channels.
        """        
        dds_linlist = [self.__dict__[key] for key in self.__dict__.keys() if isinstance(self.__dict__[key],DDS)]
        for dds in dds_linlist:
            self.dds_array[dds.urukul_idx][dds.ch] = dds

        all_idx = [(uru,ch) for uru in range(N_uru) for ch in range(N_ch)]
        key_idx = [(dds.urukul_idx,dds.ch) for dds in dds_linlist]
        non_key_idx = list(set(all_idx).difference(key_idx))
        for idx in non_key_idx:
            uru = idx[0]
            ch = idx[1]
            freq, amp, v_pd = 0., 0., 0.
            this_dds = DDS(uru,ch,freq,amp,v_pd,dac_device=self._dac_frame.dac_device)
            self.dds_array[uru][ch] = this_dds

    @portable
    def reset_defaults(self):
        for dds in self.dds_list:
            dds._restore_defaults()

    @portable
    def stash_defaults(self):
        for dds in self.dds_list:
            dds._stash_defaults()

#     def set_frequency_ramp_profile(self, dds:DDS, freq_list, t_ramp:float, dwell_end=True, dds_mgr_idx=0):
#         """Define an amplitude ramp profile and append to the specified DDSManager object.

#         Args:
#             dds (DDS): the DDS object corresponding to the channel to be ramped.
#             freq_list (ArrayLike): An ndarray or list of values over which to ramp.
#             t_ramp (float): The time (in seconds) for the complete ramp.
#             dwell_end (bool, optional): If True, after completing the ramp, the
#             DDS will remain at the final value in freq_list. Otherwise, switches
#             back to freq_list[0]. Defaults to True. 
#             dds_mgr_idx (int, optional): The index of the DDSManager to use. By
#             specifying different indices, one can define multiple ramp sequences
#             to be used at different times during a sequence. Defaults to 0.
#         """
#         freq_list, dt_ramp = self.handle_ramp_input(freq_list,t_ramp,dds_mgr_idx)
#         this_profile = RAMProfile(
#             dds.dds_device, freq_list, dt_ramp, RAMType.FREQ, ad9910.RAM_MODE_RAMPUP, dwell_end=dwell_end)
#         self.dds_manager[dds_mgr_idx].append_ramp(dds, frequency_src=this_profile, amplitude_src=dds.amplitude)
        
#     def set_amplitude_ramp_profile(self, dds:DDS, amp_list, t_ramp:float, dwell_end=True, dds_mgr_idx=0):
#         """Define an amplitude ramp profile and append to the specified DDSManager object.

#         Args:
#             dds (DDS): the DDS object corresponding to the channel to be ramped.
#             amp_list (ArrayLike): An ndarray or list of values over which to ramp.
#             t_ramp (float): The time (in seconds) for the complete ramp.
#             dwell_end (bool, optional): If True, after completing the ramp, the
#             DDS will remain at the final value in amp_list. Otherwise, switches
#             back to amp_list[0]. Defaults to True. 
#             dds_mgr_idx (int, optional): The index of the DDSManager to use. By
#             specifying different indices, one can define multiple ramp sequences
#             to be used at different times during a sequence. Defaults to 0.
#         """        
#         amp_list, dt_ramp = self.handle_ramp_input(amp_list,t_ramp,dds_mgr_idx)
#         this_profile = RAMProfile(
#             dds.dds_device, amp_list, dt_ramp, RAMType.AMP, ad9910.RAM_MODE_RAMPUP, dwell_end=dwell_end)
#         self.dds_manager[dds_mgr_idx].append_ramp(dds, frequency_src=dds.frequency, amplitude_src=this_profile)

#     def handle_ramp_input(self,value_list,t_ramp,dds_mgr_idx):
#         if isinstance(value_list,np.ndarray):
#             value_list = list(value_list)
#         self.populate_dds_mgrs(dds_mgr_idx)
#         N_points = len(value_list)
#         if N_points > 1024:
#             raise ValueError("Too many points!")
#         dt_ramp = round( ( t_ramp / N_points ) / 4.e-9 ) * 4.e-9
#         return value_list, dt_ramp

#     def populate_dds_mgrs(self,dds_mgr_idx):
#         '''Create a new DDSManager and add to the list if the specified number
#         of DDSManagers does not yet exist.'''
#         current_max_mgr_idx = len(self.dds_manager) - 1
#         if dds_mgr_idx == current_max_mgr_idx + 1:
#             self.dds_manager.append(DDSManager(core=self.core))
#         elif dds_mgr_idx == current_max_mgr_idx:
#             pass
#         else:
#             raise ValueError("Must add DDSManagers sequentially with index increasing from 0.")
        
#     def cleanup_dds_profiles(self):
#         '''Loops over all DDSManagers and adds single-tone RAM profiles for
#         non-ramped DDS channels which share a card with a ramped DDS channel.'''
#         for dds_mgr in self.dds_manager:
#             dds_mgr.other_dds_to_single_tone_ram(dds_array=self.dds_array)

#     @kernel
#     def load_profile(self, dds_mgr_idx=0):
#         self.dds_manager[dds_mgr_idx].load_profile()

#     @kernel
#     def enable_profile(self, dds_mgr_idx=0):
#         '''Enable + commit enable -- activates a RAM profile and begins
#         playback. Delay is dominated by enable, so if more precise timing is
#         required, call enable ahead of time and follow with commit_enable when
#         you want to begin the ramp.'''
#         self.dds_manager[dds_mgr_idx].enable()
#         self.dds_manager[dds_mgr_idx].commit_enable()

#     @kernel
#     def disable_profile(self, dds_mgr_idx=0):
#         '''Enable + commit disable -- activates a RAM profile and begins
#         playback. Delay is dominated by disable, so if more precise timing is
#         required, call disable ahead of time and follow with disable when
#         you want to begin the ramp.'''
#         self.dds_manager[dds_mgr_idx].disable()
#         self.dds_manager[dds_mgr_idx].commit_disable()

#     @kernel
#     def enable(self, dds_mgr_idx=0):
#         '''Sets up but does not begin a ramp. Call commit_enable to start the
#         RAM profile (profile 0).'''
#         self.dds_manager[dds_mgr_idx].enable()

#     @kernel
#     def commit_enable(self, dds_mgr_idx=0):
#         '''Starts a RAM playback after enable() has been called.'''
#         self.dds_manager[dds_mgr_idx].commit_enable()

#     @kernel
#     def disable(self, dds_mgr_idx=0):
#         '''
#         Sets up the termination of but does not stop a ramp. Call RAM playback
#         and switch back to the single-tone profile (profile 7).
#         '''
#         self.dds_manager[dds_mgr_idx].disable()

#     @kernel
#     def commit_disable(self, dds_mgr_idx=0):
#         '''Stops a RAM playback after disable() has been called.'''
#         self.dds_manager[dds_mgr_idx].commit_disable()

# class DDSManager(AD9910Manager):
#     def __init__(self,core=DummyCore()):
#         super().__init__(core=core)
#         self.DDS_with_ramps = []

#     def append_ramp(self, dds:DDS, frequency_src=0.0, phase_src=0.0, amplitude_src=1.0):
#         self.append(dds.dds_device, frequency_src=frequency_src, phase_src=phase_src, amplitude_src=amplitude_src)
#         self.DDS_with_ramps.append(dds)

#     def other_dds_to_single_tone_ram(self, dds_array):
#         '''For DDS channels that are not being ramped which live on the same
#         urukul card as one that has a ramp profile set in this DDSManager,
#         define a RAM profile which is single-frequency, single-amplitude to
#         maintain that channel's output when the RAM profiles for this DDSManager
#         are enabled.'''

#         # figure out which dds channels are being ramped on this DDSManager
#         ch_with_ram = [(dds.urukul_idx,dds.ch) for dds in self.DDS_with_ramps]
#         uru_with_ram = set([ch[0] for ch in ch_with_ram])

#         # loop over the urukul cards which have a DDS being ramped
#         for uru in uru_with_ram:
#             all_ch = set([0,1,2,3])
#             # figure out which channels on this urukul are being ramped
#             ch_with_ram_on_this_uru = [ch[1] for ch in ch_with_ram if ch[0] == uru]
#             # figure out which channels on this urukul are not being ramped
#             ch_without_ram_on_this_uru = all_ch.difference(ch_with_ram_on_this_uru)
#             # loop over those not being ramped
#             for ch in ch_without_ram_on_this_uru:
#                 dds = dds_array[uru][ch]
#                 # append a single-frequency, single-amplitude RAM profile.
#                 self.append(dds.dds_device, frequency_src=dds.frequency, amplitude_src=dds.amplitude)