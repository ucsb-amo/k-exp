from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class rf_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        # self.xvar('imaging_state',[2,1])
        self.p.t_rf_state_xfer_sweep = 20.e-3
        self.p.n_rf_state_xfer_sweep_steps = 1000
        self.p.frequency_rf_sweep_state_prep_center = 459.38e6
        self.p.frequency_rf_sweep_state_prep_fullwidth = 122.448e3
        self.p.do_sweep = 1

        self.p.i_magtrap_ramp_start = 74.
        self.p.i_magtrap_ramp_end = 0.

        self.p.i_feshbach_field_ramp_start = 20.
        # self.p.i_feshbach_field_ramp_end = 90.

        self.p.evap2_current = 18.9

        # self.xvar('i_feshbach_field_ramp_end',np.linspace(32.,70.,80))

        # self.xvar('i_feshbach_field_ramp_start',np.linspace(30.,15.,10))

        self.p.t_lightsheet_ramp_end = 100.e-3
        # self.xvar('t_lightsheet_rampup',np.linspace(10.e-3,self.p.t_lightsheet_ramp_end,10))

        # self.xvar('paint_fraction',np.linspace(0.,.36,20))

        # self.xvar('v_pd_lightsheet_rampdown2_end',np.linspace(.75,.1,20))

        # self.xvar('evap2_current',np.linspace(20.,15.,10))

        # self.xvar('t_tof',np.linspace(100.,2000.,10)*1.e-6)

        # self.xvar('i_magtrap_ramp_start', np.linspace(40.,90.,10))
        # self.xvar('i_magtrap_init', np.linspace(20.,40.,10))

        self.p.i_magtrap_init = 30.

        self.p.t_magtrap = 30.e-3

        self.p.t_lightsheet_hold = 500.e-3

        self.p.t_lightsheet_rampup = 25.e-3

        # self.xvar('t_tof',np.linspace(10,500,10)*1.e-6)
        self.p.t_tof = 400.e-6

        self.xvar('t_mot_load', np.linspace(50.e-3,2.5,8))
        self.p.t_mot_load = 0.5

        self.p.t_bias_off_wait = 2.e-3

        self.finish_build(shuffle=True)

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

        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        # self.flash_cooler()

        # self.dds.power_down_cooling()

        # self.set_shims(v_zshim_current=0.,
        #                 v_yshim_current=self.p.v_yshim_current_gm,
        #                   v_xshim_current=self.p.v_xshim_current_gm)
        
        # self.ttl.pd_scope_trig.on()
        # self.inner_coil.igbt_ttl.on()

        # delay(10.e-3)

        # self.inner_coil.set_current(i_supply=self.p.i_magtrap_ramp_start)
        # delay(self.p.t_magtrap)

        # # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        # # for i in self.p.magtrap_ramp_list:
        # #     self.inner_coil.set_current(i_supply=i)
        #     # delay(self.p.dt_magtrap_ramp)
        
        # delay(30.e-3)

        # self.inner_coil.off()

        # self.ttl.pd_scope_trig.off()

        # # self.lightsheet.off()

        # self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
        #                 v_yshim_current=self.p.v_yshim_current_gm,
        #                   v_xshim_current=self.p.v_xshim_current_gm)
    
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