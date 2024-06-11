from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tof_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.imaging_state = 2.
        # self.xvar('imaging_state',[2,1])
        # scanrange1 = self.p.frequency_detuned_imaging_F1 + np.arange(-125.,-75.,2.)*1.e6
        # scanrange2 = self.p.frequency_detuned_imaging_F1 + np.arange(-320.,-250.,2.)*1.e6
        # scanrange = np.concatenate((scanrange1,scanrange2))
        # scanrange = 348.e6 + np.arange(-15.,15.,1.)*1.e6
        # scanrange = 410.e6 + np.arange(-20.,20.,1.)*1.e6
        # scanrange = 600.54e6 + np.arange(-25.,25.,1)*1.e6
        # self.xvar('frequency_detuned_imaging_F1',scanrange)
        # self.p.frequency_detuned_imaging_F1 = 437.e6
        # self.xvar('dummy',[1.]*2)

        self.p.t_mot_load = .75

        # self.xvar('t_lightsheet_rampup',np.linspace(10.,1000.,8)*1.e-3)
        # self.xvar('t_lightsheet_hold',np.linspace(30.,1000.,10)*1.e-3)
        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(1.,9.,30))

        # self.xvar('t_feshbach_field_rampup',np.linspace(.005,.5,12))

        # self.xvar('i_evap1_current',np.linspace(10.,13.,8))
        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(1.,5.,6))
        # self.p.v_pd_lightsheet_rampdown_end = 2.8
        # self.xvar('t_lightsheet_rampdown',np.linspace(2.,.02,30))
        # self.p.t_lightsheet_rampdown = .6
        # self.p.i_evap1_current = 9.5

        # self.xvar('i_evap2_current',np.linspace(100.,110.,3))
        # self.xvar('i_evap2_current', np.linspace(28.,34.,10))
        # self.xvar('i_evap2_current',np.linspace(7.,70.,40))
        # self.p.i_evap2_current = 31.3

        # self.xvar('v_pd_tweezer_1064_ramp_end',np.linspace(2.,8.,8))
        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,1000.,6)*1.e-3)
        # self.xvar('t_tweezer_hold',np.linspace(1.,20.,20)*1.e-3)
        # self.p.v_pd_tweezer_1064_ramp_end = 5.8
        # self.p.t_tweezer_1064_ramp = 500.e-3

        # self.xvar('v_pd_lightsheet_rampdown2_end',np.linspace(0.01,.9,6))
        # self.xvar('t_lightsheet_rampdown2',np.linspace(.5,.01,6))
        # self.p.v_pd_lightsheet_rampdown2_end = .2
        # self.p.t_lightsheet_rampdown2 = .2    

        # self.xvar('v_pd_lightsheet_rampdown3_end',np.linspace(0.,4.,8))
        # self.xvar('t_lightsheet_rampdown3',np.linspace(0.02,1.5,8))
        # self.p.v_pd_lightsheet_rampdown3_end = 0.
        # self.p.t_lightsheet_rampdown3 = .01

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(.1,1.5,6))
        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.002,.5,6))
        # self.p.v_pd_tweezer_1064_rampdown_end = 1.6
        # self.p.v_pd_tweezer_1064_rampdown_end = .8
        # self.p.t_tweezer_1064_rampdown = 100.e-3

        # self.xvar('i_tweezer_evap_current',np.linspace(23.,28.,10))

        # self.p.i_tweezer_evap_current = 25.

        self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(.033,.07,6))
        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.02,.4,6))
        # self.p.t_tweezer_1064_rampdown2 = 250.e-3
        self.p.v_pd_tweezer_1064_rampdown2_end = 0.034

        # self.xvar('t_tweezer_hold',np.linspace(.0,3.,20))

        # self.xvar('t_feshbach_field_decay',np.linspace(.5,3.,20)*1.e-3)
        # self.p.t_feshbach_field_decay = 3.e-3

        # self.xvar('dummy',[0]*200)

        # self.p.n_tweezers = 2
        # self.xvar('frequency_tweezer_array_width',np.linspace(.2e6,1.e6,6))
        # self.p.frequency_tweezer_array_width = .7e6
        # self.p.amp_tweezer_auto_compute = False
        # self.p.amp_tweezer_list = [.2,.215]

        # self.xvar('i_magtrap_shim',np.linspace(0.,2.,20))

        self.xvar('t_tof',np.linspace(5.,120.,10)*1.e-6)

        # self.p.i_magtrap_ramp_end = 47.
        
        self.p.t_tof = 100.e-6

        # self.p.t_magtrap = 200.e-3

        # self.p.n_lightsheet_rampup_steps = 100
        # self.p.t_lightsheet_rampup = 200.e-3
        # self.p.t_lightsheet_hold = 50.e-3
        
        # self.xvar('dummy_z',[0]*500)

        self.camera_params.amp_imaging = .07
        # self.xvar('amp_imaging',np.linspace(0.00,0.10,2))
        self.p.t_imaging_pulse = 6.e-6
        self.camera_params.exposure_time = 6.e-6
        self.camera_params.em_gain = 290.

        self.p.N_repeats = 1

        self.finish_build(shuffle=True)

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
        self.dds.tweezer.on()
        self.ttl.awg.on()
        self.tweezer.zero_and_pause_pid()
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)

        self.lightsheet.ramp_down2(t=self.p.t_lightsheet_rampdown2)

        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,v_ramp_list=self.p.v_pd_tweezer_1064_rampdown_list)

        self.outer_coil.set_current(i_supply=self.p.i_tweezer_evap_current)

        self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampdown3, v_ramp_list=self.p.v_pd_lightsheet_ramp_down3_list)
        delay(10.e-3)

        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,v_ramp_list=self.p.v_pd_tweezer_1064_rampdown2_list)
        
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