from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

class tof_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=False)

        self.p.imaging_state = 1.
        # self.xvar('imaging_state',[2,1])
        # self.xvar('frequency_detuned_imaging',np.arange(400.,440.,3)*1.e6)
        # self.p.frequency_detuned_imaging = 421.e6
        # self.xvar('dummy',[1.]*2)

        self.xvar('beans',[1,2]*300)

        self.p.t_mot_load = .75

        self.p.t_tof = 200.e-6
        self.p.t_magtrap_tof = 20.e-6
        self.p.t_lightsheet_tof = 10.e-6
        self.p.t_tweezer_tof = 20.e-6

        self.p.t_lightsheet_hold = 100.e-3

        self.camera_params.amp_imaging = 0.078
        self.camera_params.exposure_time = 5.e-6
        self.params.t_imaging_pulse = self.camera_params.exposure_time

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

            delay(self.p.t_magtrap_tof)

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

            self.outer_coil.on()
            delay(1.e-3)
            self.outer_coil.set_voltage(v_supply=70.)

            for i in self.p.feshbach_field_rampup_list:
                self.outer_coil.set_current(i_supply=i)
                delay(self.p.dt_feshbach_field_rampup)
            delay(20.e-3)

            self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampdown)

            self.lightsheet.off()
    
            delay(self.p.t_lightsheet_tof)

        elif self.p.beans == 2:

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
            
            self.outer_coil.on()
            delay(1.e-3)
            self.outer_coil.set_voltage(v_supply=70.)

            for i in self.p.feshbach_field_rampup_list:
                self.outer_coil.set_current(i_supply=i)
                delay(self.p.dt_feshbach_field_rampup)
            delay(20.e-3)

            self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampdown)
            
            for i in self.p.feshbach_field_ramp_list:
                self.outer_coil.set_current(i_supply=i)
                delay(self.p.dt_feshbach_field_ramp)
            delay(20.e-3)

            self.tweezer.vva_dac.set(v=0.)
            self.tweezer.on()
            self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)

            self.lightsheet.ramp_down2(t=self.p.t_lightsheet_rampdown2)

            self.ttl.pd_scope_trig.on()
            self.outer_coil.off()
            delay(self.p.t_feshbach_field_decay)
            self.ttl.pd_scope_trig.off()

            self.lightsheet.off()
            self.tweezer.off()
        
            delay(self.p.t_tweezer_tof)

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