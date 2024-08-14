from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class rf_scan(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        # self.xvar('imaging_state',[2,1])

        self.xvar('beans',[0,1,2])

        # self.xvar('i_magtrap_init',np.linspace(20.,70.,20))

        self.p.t_magtrap = 30.e-3

        self.p.i_feshbach_field_ramp_start = 0.
        self.p.i_feshbach_field_ramp_end = 13.2
        self.p.t_feshbach_field_ramp = 30.e-3

        self.p.v_pd_lightsheet_rampdown_end = .84
        self.p.t_lightsheet_rampdown = 1.4*s

        self.p.v_pd_lightsheet_rampdown2_start = self.p.v_pd_lightsheet_rampdown_end
        self.p.v_pd_lightsheet_rampdown2_end = .53
        self.p.t_lightsheet_rampdown2 = 1.7*s

        self.p.evap1_current = 13.5
        self.p.evap2_current = 12.4

        # self.xvar('evap1_current',np.linspace(11.6,14.3,6))

        # self.xvar('i_feshbach_field_ramp_start',np.linspace(30.,15.,10))

        # self.p.t_lightsheet_ramp_end = 100.e-3
        # self.xvar('t_lightsheet_rampup',np.linspace(10.e-3,self.p.t_lightsheet_ramp_end,10))
        # self.xvar('t_lightsheet_rampdown',np.linspace(.5,2.,6))

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(1.2,.6,6))
        # self.xvar('v_pd_lightsheet_rampdown2_end',np.linspace(.6,.51,6))
        # self.xvar('t_lightsheet_rampdown2',np.linspace(.5,2.,6))

        # self.xvar('evap2_current',np.linspace(11.5,14.3,6))

        # self.xvar('t_tof',np.linspace(10.,1500.,15)*1.e-6)

        # self.xvar('i_magtrap_ramp_start', np.linspace(40.,90.,10))
        # self.xvar('i_magtrap_init', np.linspace(20.,40.,10))

        self.p.t_lightsheet_hold = 500.e-3

        self.p.t_tweezer_1064_ramp = 150.e-3

        self.p.t_tweezer_hold = 50.e-3

        self.p.t_lightsheet_rampup = 25.e-3

        self.camera_params.em_gain = 290.
        # self.camera_params.amp_imaging = 0.25

        self.p.t_tof = 150.e-6

        self.p.t_mot_load = 0.5
        self.p.t_bias_off_wait = 2.e-3

        self.finish_prepare(shuffle=False)

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

        # self.release()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        # self.outer_coil.igbt_ttl.on()

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=0.,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        
        self.inner_coil.igbt_ttl.on()

        self.inner_coil.set_current(i_supply=self.p.i_magtrap_ramp_start)
        delay(self.p.t_magtrap)

        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)
        
        self.outer_coil.set_current(i_supply=self.p.evap1_current)
        self.outer_coil.set_voltage(v_supply=9.)
        delay(20.e-3)

        self.inner_coil.off()

        if self.p.beans == 0:
            self.outer_coil.on(i_supply=self.p.evap1_current)

            delay(30.e-3)
            self.ttl.pd_scope_trig.on()
            self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampdown)
            self.ttl.pd_scope_trig.off()

            self.outer_coil.set_current(i_supply=self.p.evap2_current)
            self.lightsheet.ramp_down2(t=self.p.t_lightsheet_rampdown2)
            self.outer_coil.off()

            delay(1.5e-3)

        elif self.p.beans == 1:
            self.outer_coil.on(i_supply=self.p.evap1_current)

            delay(30.e-3)

            self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampdown)
            self.outer_coil.off()

            delay(1.5e-3)

        elif self.p.beans == 2:
            delay(self.p.t_lightsheet_hold)

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