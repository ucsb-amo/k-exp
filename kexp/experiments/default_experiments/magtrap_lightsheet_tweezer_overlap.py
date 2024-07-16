from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

class tof_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=False)

        self.p.imaging_state = 1.
        # self.xvar('imaging_state',[2,1])
        # self.xvar('frequency_detuned_imaging',np.arange(400.,440.,3)*1.e6)
        # self.p.frequency_detuned_imaging = 421.e6
        # self.xvar('dummy',[1.]*2)

        self.xvar('beans',[0,1]*300)

        self.p.t_mot_load = .75

        self.p.t_tof = 30.e-6

        self.p.t_lightsheet_hold = 100.e-3

        self.camera_params.amp_imaging = 0.5
        # self.camera_params.exposure_time = 25.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time

        # self.p.N_repeats = 2

        self.finish_build(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.outer_coil.discharge()

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

        if self.p.beans == 0:

            self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
                            v_yshim_current=self.p.v_yshim_current_magtrap,
                            v_xshim_current=self.p.v_xshim_current_magtrap)

            # magtrap start
            self.ttl.pd_scope_trig.pulse(1.e-6)
            self.inner_coil.on()

            delay(self.p.t_lightsheet_rampup)

            for i in self.p.magtrap_ramp_list:
                self.inner_coil.set_current(i_supply=i)
                delay(self.p.dt_magtrap_ramp)

            delay(self.p.t_magtrap)

            self.inner_coil.off()

        elif self.p.beans == 1:

            self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
                            v_yshim_current=self.p.v_yshim_current_magtrap,
                            v_xshim_current=self.p.v_xshim_current_magtrap)

            # magtrap start
            self.ttl.pd_scope_trig.pulse(1.e-6)
            self.inner_coil.on()

            # ramp up lightsheet over magtrap
            self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

            for i in self.p.magtrap_ramp_list:
                self.inner_coil.set_current(i_supply=i)
                delay(self.p.dt_magtrap_ramp)

            delay(self.p.t_magtrap)

            for i in self.p.magtrap_rampdown_list:
                self.inner_coil.set_current(i_supply=i)
                delay(self.p.dt_magtrap_rampdown)

            self.inner_coil.off()

            delay(self.p.t_lightsheet_hold)

            self.lightsheet.off()
        # self.tweezer.off()
    
        delay(self.p.t_tof)
        # self.flash_repump()
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