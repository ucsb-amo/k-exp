from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

class tof_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        # self.p.imaging_state = 1.
        # self.xvar('frequency_detuned_imaging',np.arange(410.,440.,3)*1.e6)
        # self.p.frequency_detuned_imaging = 413.e6
        # self.p.frequency_detuned_imaging = 420.e6
        self.p.frequency_detuned_imaging = 429.e6
        # self.xvar('dummy',[1.]*50)

        self.p.t_mot_load = .75

        # self.xvar('detune_gm',np.linspace(7,12.,8))
        # self.xvar('t_gm',np.linspace(.05,5.,8)*1.e-3)
        # self.xvar('pfrac_d1_c_gm',np.linspace(.7,.99,8))
        # self.xvar('pfrac_d1_r_gm',np.linspace(.3,.99,8))

        # self.xvar('pfrac_c_gmramp_end',np.linspace(.05,.4,10))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(.03,.4,10))
        # self.xvar('t_gmramp',np.linspace(3.,8.,20)*1.e-3)

        # self.xvar('i_magtrap_init',np.linspace(20.,38.,8))
        # self.xvar('i_magtrap_ramp_end',np.linspace(28.,95.,8))
        # self.xvar('t_magtrap',np.linspace(0.1,500.,10)*1.e-3)
        # self.xvar('t_magtrap_ramp',np.linspace(10.,800.,8)*1.e-3)
        # self.xvar('t_magtrap_rampdown',np.linspace(100.,250.,5)*1.e-3)

        # self.p.t_magtrap = .1
        # self.p.t_magtrap_ramp = .1

        # self.xvar('v_zshim_current_magtrap',np.linspace(10.,800.,8)*1.e-3)
        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,2.,10))
        # self.xvar('v_yshim_current_magtrap',np.linspace(3.,8.,20))

        # self.xvar('t_lightsheet_rampup',np.linspace(20.,800.,6)*1.e-3)
        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(6.,9.99,6))
        # self.p.v_pd_lightsheet_rampup_end = 9.99

        # self.xvar('t_feshbach_field_rampup',np.linspace(.005,.5,12))

        # self.p.t_feshbach_field_rampup = .3

        # self.p.t_rf_state_xfer_sweep = 100.e-3
        # self.p.n_rf_state_xfer_sweep_steps = 2000
        # # self.p.frequency_rf_sweep_state_prep_center = 459.3543e6
        # self.p.frequency_rf_sweep_state_prep_fullwidth = 1000.e3

        # self.xvar('frequency_rf_sweep_state_prep_center',154.2e6 + np.linspace(-40.,40.,80)*1.e6)
        # self.p.do_sweep = 1

        # self.xvar('i_evap1_current',np.linspace(190.,194.,8))
        # self.xvar('i_evap1_current',np.linspace(144.,163.,8))

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(2.,5.,8))
        # self.p.v_pd_lightsheet_rampdown_end = 4.5
        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,8))
        # self.p.t_lightsheet_rampdown = .05
        # self.p.i_evap1_current = 191.5

        # self.xvar('i_evap2_current',np.linspace(179.,187.,8))
        # self.xvar('i_evap2_current',np.linspace(133.,160.,8))
        # self.xvar('i_evap2_current', np.linspace(28.,34.,10))
        # self.xvar('i_evap2_current',np.linspace(7.,70.,40))
        # self.p.i_evap2_current = 181.3
        # self.p.i_evap2_current = 180.

        # self.xvar('v_pd_tweezer_1064_ramp_end', np.linspace(5.,9.9,6))
        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,200.,6)*1.e-3)
        # self.xvar('t_tweezer_hold',np.linspace(1.,20.,20)*1.e-3)
        # self.p.v_pd_tweezer_1064_ramp_end = 7.9
        # self.p.t_tweezer_1064_ramp = .124

        # self.xvar('v_pd_lightsheet_rampdown2_end',np.linspace(0.01,2.,6))
        # self.xvar('t_lightsheet_rampdown2',np.linspace(.5,.01,6))
        # self.p.v_pd_lightsheet_rampdown2_end = .2
        # self.p.t_lightsheet_rampdown2 = .2    

        # self.xvar('v_pd_lightsheet_rampdown3_end',np.linspace(0.,4.,8))
        # self.xvar('t_lightsheet_rampdown3',np.linspace(0.02,1.5,8))
        # self.p.v_pd_lightsheet_rampdown3_end = 0.
        # self.p.t_lightsheet_rampdown3 = .01

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(.2,2.,8))
        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.001,.5,8))
        # self.p.v_pd_tweezer_1064_rampdown_end = 1.6
        # self.p.v_pd_tweezer_1064_rampdown_end = .7
        # self.p.t_tweezer_1064_rampdown = 72.e-3

        # self.xvar('i_tweezer_evap_current',np.linspace(185.,192.,6))

        # self.p.i_tweezer_evap_current = 190.6
        # self.p.i_tweezer_evap_current = 180.

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(.025,.04,5)) 
        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(.05,.11,5))
        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.01,.4,6))
        # self.p.t_tweezer_1064_rampdown2 = .322
        # self.p.v_pd_tweezer_1064_rampdown2_end = .025

        self.xvar('i_forced_evap_ramp_end',np.linspace(20.,50.,10))
        self.xvar('t_forced_evap_ramp',np.linspace(.1,1.5,10))

        self.p.n_tweezers = 1
        # self.xvar('frequency_tweezer_array_width',np.linspace(.2e6,1.e6,6))
        # self.p.frequency_tweezer_array_width = .7e6
        # self.p.amp_tweezer_auto_compute = False
        # self.xvar('amp_tweezer_list')
        self.p.amp_tweezer_list = [.17]

        # self.xvar('t_tof',np.linspace(100.,550.,15)*1.e-6)
        self.p.t_tof = 100.e-6
        self.p.N_repeats = [1]

        # self.p.t_magtrap = 200.e-3

        # self.p.n_lightsheet_rampup_steps = 100
        # self.p.t_lightsheet_rampup = 200.e-3
        # self.xvar('t_lightsheet_hold',np.linspace(30.,1000.,6)*1.e-3)
        self.p.t_lightsheet_hold = 100.e-3
        
        # self.xvar('dummy_z',[0]*500)

        # self.xvar('amp_imaging',np.linspace(.03,.08,15))
        # self.xvar('amp_imaging',np.linspace(.04,.09,20))
        self.camera_params.amp_imaging = 0.058
        self.camera_params.exposure_time = 10.e-6
        self.params.t_imaging_pulse = self.camera_params.exposure_time

        # self.p.N_repeats = 2

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(amp=self.p.amp_imaging)
        # self.set_high_field_imaging(i_outer = self.p.i_evap2_current)

        self.outer_coil.discharge()

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
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.inner_coil.on()

        # ramp up lightsheet over magtrap
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)

        delay(self.p.t_magtrap)

        for i in self.p.magtrap_rampdown_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_rampdown)

        # self.inner_coil.off()
        
        self.outer_coil.on()
        delay(1.e-3)
        self.outer_coil.set_voltage(v_supply=70.)

        for i in self.p.feshbach_field_rampup_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_rampup)
        delay(20.e-3)

        self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampdown)
        
        for i in self.p.feshbach_field_ramp_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_ramp)
        delay(20.e-3)

        self.tweezer.vva_dac.set(v=0.)
        self.tweezer.on()
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)

        self.lightsheet.ramp_down2(t=self.p.t_lightsheet_rampdown2)

        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,v_ramp_list=self.p.v_pd_tweezer_1064_rampdown_list)

        for i in self.p.feshbach_field_ramp2_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_ramp2)
        delay(20.e-3)

        for i in self.p.forced_evap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_forced_evap_ramp)
        delay(30.e-3)

        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,v_ramp_list=self.p.v_pd_tweezer_1064_rampdown2_list)
        
        # self.outer_coil.set_current(i_supply=180.)
        # delay(30.e-3)

        # self.ttl.pd_scope_trig.on()
        # self.outer_coil.off()
        # delay(self.p.t_feshbach_field_decay)
        # self.ttl.pd_scope_trig.off()

        self.lightsheet.off()
        self.tweezer.off()
    
        delay(self.p.t_tof)
        # self.flash_repump()
        self.abs_image()

        self.inner_coil.off()
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