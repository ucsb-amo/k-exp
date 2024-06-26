from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tof_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.imaging_state = 2.

        self.p.t_mot_load = .75

        self.p.v_pd_tweezer_1064_rampdown2_end = 0.126 
        # self.p.t_tof = 2.e-6

        self.camera_params.amp_imaging = .079
        self.p.t_imaging_pulse = 25.e-6
        self.camera_params.exposure_time = 25.e-6
        self.camera_params.em_gain = 290.

        self.p.t_feshbach_field_decay = 20.e-3

        # self.xvar('amp_imaging',np.linspace(0.03, 0.125, 20))
        # self.xvar('amp_imaging',np.logspace( np.log10(0.03), np.log10(0.125), 25))

        # self.xvar('frequency_detuned_imaging',np.linspace(0.,40.,20)*1.e6)

        self.xvar('t_tof', np.linspace(2,15,15)*1.e-6)

        self.p.N_repeats = 1

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(amp=self.p.amp_imaging)

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
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)
        
        self.outer_coil.set_current(i_supply=self.p.i_feshbach_field_rampup_start)
        self.outer_coil.set_voltage(v_supply=70.)

        delay(self.p.t_magtrap)

        self.inner_coil.off()
        # delay(self.p.t_lightsheet_hold)
        self.outer_coil.on()

        for i in self.p.feshbach_field_rampup_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_rampup)
        delay(20.e-3)
        self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampdown)

        
        for i in self.p.feshbach_field_ramp_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_ramp)
        delay(20.e-3)
        
        # delay(10.e-3)
        self.tweezer.vva_dac.set(v=0.)
        self.tweezer.on()
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)

        self.lightsheet.ramp_down2(t=self.p.t_lightsheet_rampdown2)

        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,v_ramp_list=self.p.v_pd_tweezer_1064_rampdown_list)

        # self.outer_coil.set_current(i_supply=self.p.i_tweezer_evap_current)

        # self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampdown3, v_ramp_list=self.p.v_pd_lightsheet_ramp_down3_list)
        # delay(10.e-3)

        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,v_ramp_list=self.p.v_pd_tweezer_1064_rampdown2_list)
        self.ttl.pd_scope_trig.on()
        self.outer_coil.off()
        delay(self.p.t_feshbach_field_decay)
        self.ttl.pd_scope_trig.off()

        self.lightsheet.off()
        self.tweezer.off()
    
        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

        # self.outer_coil.off()

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