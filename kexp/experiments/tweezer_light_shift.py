from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tweezer_lightshift(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.imaging_state = 1.

        self.p.t_mot_load = .75

        self.p.v_pd_lightsheet_rampdown_end = 6.
        self.p.v_pd_tweezer_1064_ramp_end = 5.8

        self.camera_params.amp_imaging = 0.09
        self.p.t_imaging_pulse = 25.e-6
        self.camera_params.exposure_time = 25.e-6
        self.camera_params.em_gain = 290.

        self.xvar('tweezer_on_during_imaging_bool',[0,1])

        self.p.f0 = self.p.frequency_detuned_imaging_F1
        self.xvar('frequency_detuned_imaging_F1',self.p.f0 + np.arange(100.,200.,6)*1.e6)

        # self.xvar('t_tof', np.linspace(2,15,15)*1.e-6)

        self.p.N_repeats = 1

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)

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

        self.ttl.pd_scope_trig.on()
        self.outer_coil.off()
        delay(self.p.t_feshbach_field_decay)
        self.ttl.pd_scope_trig.off()

        if not self.p.tweezer_on_during_imaging_bool:
            self.tweezer.off()
        self.lightsheet.off()
    
        delay(self.p.t_tof)
        self.abs_image()

        if self.p.tweezer_on_during_imaging_bool:
            self.tweezer.off()

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