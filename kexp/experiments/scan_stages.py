from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

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

        self.xvar('n_steps_x',np.linspace(0.,2000.,20))
        self.xvar('n_steps_y',np.linspace(0.,2000.,20))
        self.xvar('n_steps_z',np.linspace(0.,2000.,20))

        self.p.t_mot_load = .5

        # self.xvar('t_tof',np.linspace(5.,15.,20)*1.e-6) 
        
        self.p.t_tof = 5.e-6

        # self.p.t_magtrap = 200.e-3

        # self.p.n_lightsheet_rampup_steps = 100
        # self.p.t_lightsheet_rampup = 200.e-3
        # self.xvar('t_lightsheet_hold',np.linspace(30.,1000.,6)*1.e-3)
        self.p.t_lightsheet_hold = 300.e-3
        
        # self.xvar('dummy_z',[0]*500)

        self.camera_params.amp_imaging = .09
        # self.camera_params.amp_imaging = .085
        # self.xvar('amp_imaging',np.linspace(0.06,0.1,10))
        # self.p.t_imaging_pulse = 20.e-6
        # self.camera_params.exposure_time = 20.e-6
        # self.camera_params.em_gain = 290.

        # self.p.N_repeats = 2

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.os_control.translate(N_steps=self.p.n_steps_x, obj='n',axis='+x')
        self.os_control.translate(N_steps=self.p.n_steps_x, obj='s',axis='-x')

        self.os_control.translate(N_steps=self.p.n_steps_y, obj='n',axis='+y')
        self.os_control.translate(N_steps=self.p.n_steps_y, obj='s',axis='-y')

        self.os_control.translate(N_steps=self.p.n_steps_z, obj='n',axis='+z')
        self.os_control.translate(N_steps=self.p.n_steps_z, obj='s',axis='-z')

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
        self.ttl.pd_scope_trig.pulse(1*us)
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

        # delay(self.p.t_lightsheet_hold)

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