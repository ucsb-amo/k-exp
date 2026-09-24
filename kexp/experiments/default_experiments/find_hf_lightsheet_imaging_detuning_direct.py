from artiq.experiment import *
from artiq.language.core import delay, now_mu, at_mu
from kexp import Base, Adjust
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      save_data=True,
                      camera_select=cameras.xy_basler,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=0)

        self.p.t_tof = 150.e-6
        # self.xvar('t_tof',np.linspace(20.e-6, 400.e-6, 5))

        self.xvar('i_hf_lightsheet_evap1_current',np.linspace(184,220.,9))
        self.p.i_hf_lightsheet_evap1_current = 220.

        self.p.hf_imaging_detuning = -620.25e6
        # self.xvar('hf_imaging_detuning', f0 + np.arange(-f_range,f_range+df,df))
        # self.xvar('hf_imaging_detuning', np.arange(-700., -575., 2.) * 1.e6)

        self.p.frequency_offset_hf_detuning = 0.
        self.xvar('frequency_offset_hf_detuning', np.linspace(-13.,13.,11)*1e6)

        # self.adjust('i_hf_lightsheet_evap1_current')
        # self.adjust('hf_imaging_detuning', -680.e6, -550.e6, step=3.e6, dtype=float)

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.

        self.data.f_center = self.data.add_data_container()

        self.finish_prepare(shuffle=True)
        
    @kernel
    def scan_kernel(self):

        f_center = -4.175e6 * self.p.i_hf_lightsheet_evap1_current + 187.e6
        self.data.f_center.put_data(f_center)
        f_this_shot = f_center + self.p.frequency_offset_hf_detuning

        self.set_imaging_detuning(frequency_detuned=f_this_shot)

        # self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False,do_magtrap_rampdown=True)

        # feshbach field on, ramp up to field 1
        self.outer_coil.on()
        self.outer_coil.set_voltage()
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_hf_lightsheet_evap1_current)
        self.set_shims(0.,0.,0.)

        delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
