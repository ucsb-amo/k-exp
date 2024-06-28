from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tweezer_evap(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        #self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(2,3.5,5))
        self.v_pd_lightsheet_rampdown_end = 3
        # self.xvar('t_tof',np.linspace(1.,50.,6)*1.e-6)
        self.xvar('frequency_detuned_imaging',np.linspace(0.,60.,20)*1.e6)
        self.p.t_tof = 50.e-6

        self.p.t_lightsheet_rampup = 200.e-3

        self.finish_build(shuffle=False)

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

        self.set_shims(v_zshim_current=0.,
                        v_yshim_current=self.p.v_yshim_current_gm,
                        v_xshim_current=self.p.v_xshim_current_gm)
        
        self.ttl.pd_scope_trig.on()
        self.inner_coil.igbt_ttl.on()

        # ramp up lightsheet
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        # rampdown magtrap
        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)

        self.outer_coil.set_current(i_supply=self.p.i_evap1_current)
        self.outer_coil.set_voltage(v_supply=9.)

        delay(self.p.t_magtrap)
        self.inner_coil.off()

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

        # self.outer_coil.set_current(i_supply=self.p.i_evap2_current)
        # delay(20.e-3)
        
        # self.lightsheet.ramp_down2(t=self.p.t_lightsheet_rampdown2)

        self.outer_coil.off()
        self.ttl.pd_scope_trig.off()
        delay(self.p.t_feshbach_field_decay)

        self.lightsheet.off()
        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()
        #


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