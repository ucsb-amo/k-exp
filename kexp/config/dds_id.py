import numpy as np

from artiq.coredevice import ad53xx
from artiq.experiment import kernel, portable
from artiq.language.core import delay_mu

from waxx.control.artiq.DDS import DDS
from waxx.config.dds_id import dds_frame as dds_frame_waxx
from waxx.control.artiq.dummy_core import DummyCore

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
                  shuttler_frame_obj = shuttler_frame(),
                  core = DummyCore()):
        
        from kexp.util.db.device_db import device_db
        self._db = device_db
        
        self.setup(expt_params, core, N_uru, N_ch, shape, dac_frame_obj)
        self.p:ExptParams
        self._dac_frame:dac_frame

        self.dds_amp_calibration = DDS_Amplitude_Calibration()
        self.dds_vva_calibration = DDS_VVA_Calibration()

        # self.aom_name = self.dds_assign(urukul_idx,ch_idx,ao_order,transition,dac_ch_vpd)
        self.antenna_rf = self.dds_assign(0,0,
                                    default_freq=200.e6,
                                    default_amp=self.p.amp_rf_source)
        self.tweezer_pid_1 = self.dds_assign(0,3, ao_order = 1,
                                    default_freq = 80.e6,
                                    dac_ch_vpd = self._dac_frame.v_pd_tweezer_pid1.ch,
                                    default_amp = self.p.amp_tweezer_pid1)
        self.tweezer_pid_2 = self.dds_assign(1,0, ao_order = 1,
                                    default_freq = 200.e6,
                                    dac_ch_vpd = self._dac_frame.v_pd_tweezer_pid2.ch,
                                    default_amp = self.p.amp_tweezer_pid2)
        self.ry_405_sw = self.dds_assign(1,1,
                                    default_freq = 80.e6,
                                    default_amp = 0.188,
                                    ao_order = 1)
        self.d2_3d_c = self.dds_assign(1,2, ao_order = -1, transition = 'D2',
                                    default_detuning = self.p.detune_d2_c_mot,
                                    default_amp = self.p.amp_d2_c_mot)
        self.d2_3d_r = self.dds_assign(1,3, ao_order = 1, transition = 'D2',
                                    default_detuning = self.p.detune_d2_r_mot,
                                    default_amp = self.p.amp_d2_r_mot)

        self.push = self.dds_assign(2,0, ao_order = 1, transition = 'D2',
                                    default_detuning = self.p.detune_push,
                                    default_amp = self.p.amp_push)
        self.d2_2dv_r = self.dds_assign(2,1, ao_order = 1, transition = 'D2',
                                    default_detuning = self.p.detune_d2v_r_2dmot,
                                    default_amp = self.p.amp_d2v_r_2dmot)
        self.d2_2dv_c = self.dds_assign(2,2, ao_order = -1, transition = 'D2',
                                    default_detuning = self.p.detune_d2v_c_2dmot,
                                    default_amp = self.p.amp_d2v_c_2dmot)
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
                                    default_freq = 350.e6,
                                    default_amp = 0.5,
                                    dac_ch_vpd=self._dac_frame.imaging_pid.ch)
        self.raman_80_plus = self.dds_assign(4,2, ao_order = 1,
                                    default_freq = 80.e6,
                                    default_amp = 0.277)
        self.optical_pumping = self.dds_assign(4,3, ao_order = -1, transition = 'D1',
                                    default_detuning = self.p.detune_optical_pumping_r_op,
                                    default_amp = self.p.amp_optical_pumping_r_op)
        
        self.raman_150_minus = self.dds_assign(5,0,
                                ao_order=-1,
                                default_freq=150.e6,
                                default_amp=0.324)
        self.d1_beatlock_ref = self.dds_assign(5,1,
                                    default_freq=42.26e6,
                                    default_amp=0.1)
        self.imaging_x_switch = self.dds_assign(5,2,
                                        ao_order=1,
                                        default_freq=100.e6,
                                        default_amp=0.3)
        self.raman_150_plus = self.dds_assign(5,3, ao_order = 1,
                                    default_freq = 150.e6,
                                    default_amp = 0.324)
        
        self.cleanup()