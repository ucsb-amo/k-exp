from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp.util.artiq.async_print import aprint

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class tof_scan(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.camera_params.amp_imaging = 0.5
        
        self.p.t_mot_load = .5

        # self.p.v_lightsheet_paint_amp_max = 4

        self.p.beans = 0
        # self.xvar("beans", [0,1]*200)

        self.xvar('v_lightsheet_paint_amp_max',np.linspace(-7.,6.,20))

        self.p.t_tof = 10.e-6
        self.p.t_lightsheet_hold = .1
        self.p.N_repeats = [10]

        self.sh_dds = self.get_device("shuttler0_dds0")
        self.sh_dds: DDS
        self.sh_trigger = self.get_device("shuttler0_trigger")
        self.sh_trigger: Trigger
        self.sh_relay = self.get_device("shuttler0_relay")
        self.sh_relay: Relay

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(amp=self.p.amp_imaging)
        # self.set_high_field_imaging(i_outer = self.p.i_evap2_current)

        # self.switch_d2_2d(1)
        # self.mot(self.p.t_mot_load)
        # self.dds.push.off()
        # self.cmot_d1(self.p.t_d1cmot * s)
        
        # self.inner_coil.set_current(i_supply=self.p.i_magtrap_init)

        # self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
        #                 v_yshim_current=self.p.v_yshim_current_gm,
        #                   v_xshim_current=self.p.v_xshim_current_gm)
        # self.gm(self.p.t_gm * s)
        # self.gm_ramp(self.p.t_gmramp)

        # # self.release()
        # self.switch_d2_3d(0)
        # self.switch_d1_3d(0)

        # self.flash_cooler()

        # self.dds.power_down_cooling()

        # self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
        #                 v_yshim_current=self.p.v_yshim_current_magtrap,
        #                   v_xshim_current=self.p.v_xshim_current_magtrap)

        # # magtrap start
        
        # self.inner_coil.on()

        # # ramp up lightsheet over magtrap
        # self.ttl.pd_scope_trig.pulse(1.e-6)

        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup,
        #                          paint=True,keep_trap_frequency_constant=True)

        # self.inner_coil.ramp(t=self.p.t_magtrap_ramp,
        #                 i_start=self.p.i_magtrap_init,
        #                 i_end=self.p.i_magtrap_ramp_end)

        # delay(self.p.t_magtrap)

        # self.inner_coil.ramp(t=self.p.t_magtrap_rampdown,
        #                 i_start=self.p.i_magtrap_ramp_end,
        #                 i_end=0.)

        # self.inner_coil.off()
        
        # self.outer_coil.on()
        # delay(1.e-3)
        # self.outer_coil.set_voltage()

        # self.outer_coil.ramp(t=self.p.t_feshbach_field_rampup,
        #                      i_start=0.,
        #                      i_end=self.p.i_evap1_current)


        # # self.ttl.pd_scope_trig.on()
        # # self.outer_coil.off()
        # # delay(self.p.t_feshbach_field_decay)
        # # self.ttl.pd_scope_trig.off()

        # self.lightsheet.off()
        # # self.tweezer.off()l
    
        # delay(self.p.t_tof)
        # self.flash_repump()
        # self.abs_image()

        # self.outer_coil.off()

        # self.outer_coil.discharge()
        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        if self.p.beans == 0:
            self.magtrap_and_load_lightsheet_paint()
        elif self.p.beans == 1: 
            self.magtrap_and_load_lightsheet()
        
        delay(self.p.t_lightsheet_hold)

        self.lightsheet.off()
    
        delay(self.p.t_tof)
        self.flash_repump()
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