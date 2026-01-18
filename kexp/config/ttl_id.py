import numpy as np
from artiq.experiment import kernel
from artiq.coredevice.ttl import TTLOut, TTLInOut

from waxx.config.ttl_id import ttl_frame as ttl_frame_waxx
from waxx.control.artiq.TTL import TTL, TTL_IN, TTL_OUT

from kexp.util.db.device_db import device_db

N_TTL = 88

class ttl_frame(ttl_frame_waxx):
    def __init__(self):

        self._db = device_db

        self.setup(N_TTL)
        
        self.img_beam_sw = self.assign_ttl_out(0)
        self.tweezer_pid2_enable = self.assign_ttl_out(1)
        self.inner_coil_pid_ttl = self.assign_ttl_out(2)
        self.outer_coil_pid_ttl = self.assign_ttl_out(3)
        self.lightsheet_sw = self.assign_ttl_out(4)
        self.basler = self.assign_ttl_out(5)
        self.inner_coil_igbt = self.assign_ttl_out(6)
        self.andor = self.assign_ttl_out(7)
        self.outer_coil_igbt = self.assign_ttl_out(8)
        self.hbridge_helmholtz = self.assign_ttl_out(9)
        self.z_basler = self.assign_ttl_out(10)
        self.tweezer_pid1_int_hold_zero = self.assign_ttl_out(11)
        self.lightsheet_pid_int_hold_zero = self.assign_ttl_out(12)
        self.aod_rf_sw = self.assign_ttl_out(13)
        self.awg_trigger = self.assign_ttl_out(14)
        self.zshim_hbridge_flip = self.assign_ttl_out(15)
        self.pd_scope_trig = self.assign_ttl_out(16)
        self.pd_scope_trig_2 = self.assign_ttl_out(17)
        self.imaging_shutter_xy = self.assign_ttl_out(18)
        self.imaging_shutter_x = self.assign_ttl_out(19)
        self.basler_2dmot = self.assign_ttl_out(20)
        self.test_trig = self.assign_ttl_out(21)
        self.raman_shutter = self.assign_ttl_out(22)
        self.pd_scope_trig3 = self.assign_ttl_out(24)

        self.keithley_trigger = self.assign_ttl_out(48)
        self.imaging_pid_int_clear_hold = self.assign_ttl_out(49)
        self.b_field_stab_SRS_blanking_input = self.assign_ttl_out(50)
        self.imaging_pid_manual_override = self.assign_ttl_out(51)
        self.ry_980_sw = self.assign_ttl_out(52)

        self.z_shim_pid_int_hold_zero = self.assign_ttl_out(56)

        self.line_trigger = self.assign_ttl_in(40)

        self.test_2 = self.assign_ttl_out(55)

        self.cleanup()