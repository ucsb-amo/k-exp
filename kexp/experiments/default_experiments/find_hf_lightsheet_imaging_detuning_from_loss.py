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
                      save_data=False,
                      camera_select=cameras.xy_basler,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=0)

        self.p.t_tof = 150.e-6
        # self.xvar('t_tof',np.linspace(20.e-6, 400.e-6, 5))

        # self.xvar('i_hf_lightsheet_evap1_current',np.linspace(192.5,194.,5))
        self.p.i_hf_lightsheet_evap1_current = 193.8
 
        # self.adjust('amp_imaging',0.3,0.6)
        self.p.amp_imaging = 2.

        self.p.hf_imaging_detuning = -620.25e6
        f0 = self.p.hf_imaging_detuning
        f_range = 3.e6
        df = 1.e6
        # self.xvar('hf_imaging_detuning', f0 + np.arange(-f_range,f_range+df,df))

        self.p.N_repeats = 100
        self.p.t_mot_load = 1.

        self.p.t_pulse = 3.e-6
        self.T = 20.e-3
        self.adjust('t_pulse',10.e-6,self.T,dtype=float)
        self.adjust('hf_imaging_detuning', -620.25e6 - 10.e6, -620.25e6 + 10.e6, dtype=float)

        self.finish_prepare(shuffle=True)
        
    @kernel
    def scan_kernel(self):

        # f0 = high_field_imaging_detuning(self.p.i_hf_lightsheet_evap1_current)
        f0 = -620.25e6
        self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        # self.set_high_field_imaging(i_outer=self.p.i_hf_lightsheet_evap1_current)
        self.imaging.set_power(power_control_parameter=self.p.amp_imaging)

        # self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False,do_magtrap_rampdown=True)
        # self.inner_coil.snap_off()

        # feshbach field on, ramp up to field 1
        self.outer_coil.on()
        self.outer_coil.set_voltage()
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_hf_lightsheet_evap1_current)
        self.set_shims(0.,0.,0.)

        
        delay(80.e-3)
        self.ttl.imaging_shutter_x.on()
        delay(5.e-3)

        # self.lightsheet.off_and_hold_pid()
        # delay(2.e-6)

        # t = now_mu()
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # at_mu(t)

        self.imaging.pulse(self.p.t_pulse)
        
        # self.lightsheet.on_and_end_hold()

        self.ttl.imaging_shutter_x.off()
        delay(self.T - self.p.t_pulse)
        delay(5.e-3)
        
        self.set_imaging_detuning(f0)
        self.imaging.set_power(0.25)

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
