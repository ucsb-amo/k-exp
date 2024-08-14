from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class rf_scan(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        # self.xvar('imaging_state',[2,1])

        self.p.t_magtrap = 30.e-3

        self.p.t_tof = 20.e-6
        # self.xvar('t_tof',np.linspace(10.,200.,10)*1.e-6)

        self.p.i_outer_coil = 50.
        self.xvar('i_outer_coil',np.linspace(0.,100.,20))

        self.p.v_pd_lightsheet_rampup_end = 2.0
        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(1.5,3.25,10))

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.dds.init_cooling()

        self.core.break_realtime()

        if self.p.imaging_state == 1.:
            self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)
        else:
            self.set_imaging_detuning()

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.inner_coil.set_current(i_supply=self.p.i_magtrap_init)
        self.inner_coil.set_voltage(v_supply=9.)
        self.outer_coil.set_current(i_supply=self.p.i_outer_coil)
        self.outer_coil.set_voltage(v_supply=9.)

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
        
        # magtrap start
        self.inner_coil.igbt_ttl.on()
        self.inner_coil.set_current(i_supply=self.p.i_magtrap_ramp_start)
        delay(self.p.t_magtrap)

        # ramp up ligthsheet over magtrap
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        
        # ramp down magtrap
        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)
        delay(30*ms)
        self.inner_coil.off()
    
        delay(self.p.t_lightsheet_hold)

        # outer coil on
        self.ttl.pd_scope_trig.on()
        self.outer_coil.igbt_ttl.on()
        delay(200.e-3)
        self.outer_coil.off()
        delay(5.e-3)
        self.ttl.pd_scope_trig.off()

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