from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp.util.artiq.async_print import aprint

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class tof_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        # self.p.imaging_state = 1.
        # self.xvar('frequency_detuned_imaging',np.arange(400.,450.,3)*1.e6)
        self.p.frequency_detuned_imaging = 427.e6 # 150a0
        # self.p.frequency_detuned_imaging = 412.e6 # NI

        self.p.t_mot_load = .75

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(3.,6.5,20))
        self.p.v_pd_lightsheet_rampdown_end = 5.358

        # self.xvar('freq_tweezer_modulation',np.linspace(100.e3,536.e3,20))
        # self.xvar('freq_tweezer_modulation',[])
        self.xvar('v_lightsheet_paint_amp_max',np.linspace(-7.,6.,20))
        # self.p.freq_tweezer_modulation = 2.15e3

        # self.xvar('painting_bool',[0,1])
        # self.p.painting_bool = 0.

        # self.xvar('t_tof',np.linspace(10.,350.,10)*1.e-6)
        self.p.t_tof = 200.e-6
        self.p.N_repeats = [1]
        
        # self.xvar('dummy_z',[0]*5)

        # self.xvar('amp_imaging',np.linspace(.03,.08,15))
        # self.xvar('amp_imaging',np.linspace(.04,.09,20))
        # self.camera_params.amp_imaging = 0.05
        # self.camera_params.exposure_time = 10.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time

        self.sh_dds = self.get_device("shuttler0_dds0")
        self.sh_dds: DDS
        self.sh_trigger = self.get_device("shuttler0_trigger")
        self.sh_trigger: Trigger
        self.sh_relay = self.get_device("shuttler0_relay")
        self.sh_relay: Relay

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(amp=self.p.amp_imaging)
        # self.set_high_field_imaging(i_outer = self.p.i_evap2_current)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.inner_coil.set_current(i_supply=self.p.i_magtrap_init)

        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        # self.release()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
                        v_yshim_current=self.p.v_yshim_current_magtrap,
                          v_xshim_current=self.p.v_xshim_current_magtrap)

        # magtrap start
        
        self.inner_coil.on()

        # ramp up lightsheet over magtrap
        self.ttl.pd_scope_trig.pulse(1.e-6)

        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup,
                                 paint=True,keep_trap_frequency_constant=False)

        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)

        delay(self.p.t_magtrap)

        for i in self.p.magtrap_rampdown_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_rampdown)

        self.inner_coil.off()
        
        self.outer_coil.on()
        delay(1.e-3)
        self.outer_coil.set_voltage()

        for i in self.p.feshbach_field_rampup_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_rampup)
        delay(20.e-3)

        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
        #                      v_list=self.p.v_pd_lightsheet_ramp_down_list,
        #                      paint=True,
        #                      keep_trap_frequency_constant=True)

        # self.ttl.pd_scope_trig.on()
        # self.outer_coil.off()
        # delay(self.p.t_feshbach_field_decay)
        # self.ttl.pd_scope_trig.off()

        self.lightsheet.off()
        # self.tweezer.off()
    
        delay(self.p.t_tof)
        # self.flash_repump()
        self.abs_image()

        self.outer_coil.off()

        self.outer_coil.discharge()

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