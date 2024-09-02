from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from artiq.language.core import kernel_from_string, now_mu
from kexp.control import objective_stages

class stage_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.os_control = objective_stages.controller()

        self.p.imaging_state = 1.
        # self.xvar('imaging_state',[2,1])
        # self.xvar('frequency_detuned_imaging',np.linspace(1370.,1530.,13)*1.e6)
        # self.xvar('frequency_detuned_imaging',np.arange(400.,500.,6)*1.e6)
        # self.p.frequency_detuned_imaging = 528.e6
        # self.xvar('dummy',[1.]*500)

        self.scan_x = np.linspace(-2000.,2000.,20)
        self.scan_y = np.linspace(-2000.,2000.,20)
        self.scan_z = np.linspace(-2000.,2000.,20)

        self.xvar('n_steps_x',self.scan_x)
        self.xvar('n_steps_y',self.scan_y)
        self.xvar('n_steps_z',self.scan_z)

        self.p.t_mot_load = .5

        # self.xvar('t_tof',np.linspace(5.,15.,20)*1.e-6) 
        self.p.t_tof = 5.e-6

        # self.p.N_repeats = 2

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.core.wait_until_mu(now_mu())
        self.os_control.translate_together_x(N_steps=self.p.n_steps_x)
        self.os_control.translate_together_y(N_steps=self.p.n_steps_y)
        self.os_control.translate_together_z(N_steps=self.p.n_steps_z)
        self.core.break_realtime()

        self.set_high_field_imaging(i_outer=self.p.i_evap3_current)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet()

        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_evap1_current)
        
        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_evap1_current,
                             i_end=self.p.i_evap2_current)
        
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=False,keep_trap_frequency_constant=False)
        
        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        self.lightsheet.off()

        self.tweezer.off()
    
        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()
        self.outer_coil.discharge()

        # revert stages to origin before next shot
        self.core.wait_until_mu(now_mu())
        self.os_control.translate_together_x(N_steps=-(self.p.n_steps_x))
        self.os_control.translate_together_y(N_steps=-(self.p.n_steps_y))
        self.os_control.translate_together_z(N_steps=-(self.p.n_steps_z))
        self.core.break_realtime()

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