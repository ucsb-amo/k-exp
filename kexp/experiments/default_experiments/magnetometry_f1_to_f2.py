from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class rf_scan(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.imaging_state = 2.
        # self.xvar('imaging_state',[2,1])
        self.xvar('frequency_detuned_imaging',np.arange(-200.,2000.,6)*1.e6)

        self.p.t_rf_state_xfer_sweep = 50.e-3
        self.p.n_rf_state_xfer_sweep_steps = 1000
        self.p.frequency_rf_sweep_state_prep_fullwidth = 102.6e3
        self.p.do_sweep = 1

        # self.xvar('i_evap1_current',np.linspace(0.,200.,100))
        # self.xvar('frequency_rf_sweep_state_prep_center', 140.e6 + np.linspace(0.,20.,60)*1.e6)
        # self.xvar('frequency_rf_sweep_state_prep_center', np.linspace(464.,468.,40)*1.e6)

        self.p.t_feshbach_field_decay = 20.e-3

        self.p.i_evap1_current = 147.

        self.p.t_mot_load = 0.5
        self.p.t_bias_off_wait = 2.e-3

        self.p.t_tof = 5.e-6

        self.finish_prepare()

    @kernel
    def scan_kernel(self):        

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
        # self.ttl.pd_scope_trig.pulse(1*us)
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
        self.outer_coil.on()

        for i in self.p.feshbach_field_rampup_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_rampup)
        delay(20.e-3)

        self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampdown)

        self.tweezer.vva_dac.set(v=0.)
        self.tweezer.on()
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)

        self.lightsheet.ramp_down2(t=self.p.t_lightsheet_rampdown2)
        # self.lightsheet.off()

        # delay(100*ms)
        
        # if self.p.do_sweep:
        #     self.rf.sweep(frequency_sweep_list=self.p.frequency_rf_sweep_state_prep_list)

        delay(20*ms)

        # self.ttl.pd_scope_trig.on()
        # self.outer_coil.off()
        # delay(self.p.t_feshbach_field_decay)
        # self.ttl.pd_scope_trig.off()
        
        self.lightsheet.off()
        self.tweezer.off()

        delay(self.p.t_tof)
        # self.flash_repump()
        self.abs_image()

        self.outer_coil.off()

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