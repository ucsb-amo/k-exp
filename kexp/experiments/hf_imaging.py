from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

T32 = 1<<32

class hf_imaging(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        # self.p.imaging_state = 1.
        # self.xvar('frequency_detuned_imaging',np.arange(400.,450.,3)*1.e6)
        # self.xvar('frequency_detuned_imaging',np.arange(-160.,950.,10)
        #*1.e6)
        self.xvar('frequency_detuned_imaging',np.linspace(-650.,-560.,40)*1.e6)
        # self.xvar('frequency_detuned_imaging',np.arange(-140.,-80.,10)*1.e6)
        # self.p.frequency_detuned_imaging = -28.e6 # i=80, from 1,-1, sigma- transition
        # self.p.frequency_detuned_imaging = 427.e6 # i = 193.
        # self.p.frequency_detuned_imaging = 424.e6 # 
        # self.p.frequency_detuned_imaging = 412.e6 # NI
        self.p.frequency_detuned_imaging = -110.e6

        self.p.t_mot_load = .75

        # self.xvar('v_lightsheet_paint_amp_max',np.arange(-7.,6.,1))

        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(8.5,9.99,5))

        # self.xvar('i_evap1_current',np.linspace(190.,194.,8))
        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,8))

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(1.,6.,10))
        self.p.v_pd_lightsheet_rampdown_end = 3.

        # self.xvar('freq_tweezer_modulation',np.linspace(100.e3,536.e3,20))
        # self.xvar('freq_tweezer_modulation',[])
        # self.xvar('v_tweezer_paint_amp_max',np.linspace(0.,6.,6))
        # self.p.freq_tweezer_modulation = 2.15e3
        self.p.v_tweezer_paint_amp_max = 4.

        # self.xvar('i_evap2_current',np.linspace(191.,194.,8))
        # self.p.i_evap2_current = 191.9
        i = 193.
        # i = 80
        self.p.i_evap1_current = i
        self.p.i_evap2_current = i

        # self.xvar('v_pd_tweezer_1064_ramp_end', np.linspace(5.,9.9,6))
        self.p.v_pd_tweezer_1064_ramp_end = 6.9

        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,200.,10)*1.e-3)
        self.p.t_tweezer_1064_ramp = .09

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(.1,3.,8)) 
        self.p.v_pd_tweezer_1064_rampdown_end = .9

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.01,.1,8))
        self.p.t_tweezer_1064_rampdown = .02

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(.04,.09,8)) 
        self.p.v_pd_tweezer_1064_rampdown2_end = .07

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.01,.15,8))
        self.p.t_tweezer_1064_rampdown2 = .11

        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(.16,.9,6)) 
        self.p.v_pd_tweezer_1064_rampdown3_end = .16

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.06,.4,10))
        self.p.t_tweezer_1064_rampdown3 = .35
        
        # self.xvar('i_evap3_current',np.linspace(191.,194.5,8))
        self.p.i_evap3_current = 193.
        # self.p.t_feshbach_field_ramp2 = .5

        # self.xvar('t_tweezer_hold',np.linspace(.05,1.,5))
        self.p.t_tweezer_hold = 100.e-3

        # self.xvar('t_tof',np.linspace(700.,1500.,8)*1.e-6)
        # self.xvar('t_tof',np.linspace(0.1,10.,10)*1.e-3)
        self.p.t_tof = 25.e-6
        self.p.N_repeats = [1]
        
        # self.xvar('dummy_z',[0]*500)

        self.p.n_tweezers = 1
        # self.xvar('frequency_tweezer_array_width',np.linspace(.2e6,1.e6,6))
        # self.p.frequency_tweezer_array_width = .7e6
        # self.p.amp_tweezer_auto_compute = False
        # self.xvar('amp_tweezer_list')
        self.p.amp_tweezer_list = [.17]

        # self.xvar('amp_imaging',np.linspace(.06,.2,15))
        # self.xvar('amp_imaging',np.linspace(.04,.09,20))
        self.camera_params.amp_imaging = 0.14
        # # self.camera_params.amp_imaging = 0.248
        # self.camera_params.exposure_time = 20.e-6
        # self.camera_params.exposure_time = 10.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        self.camera_params.em_gain = 300

        self.p.n_tweezer_ramp_steps = 100

        self.p.t_lightsheet_hold = 100.e-3

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(amp=self.p.amp_imaging)

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
        self.lightsheet.ramp(self.p.t_lightsheet_rampup,
                             self.p.v_pd_lightsheet_rampup_start,
                             self.p.v_pd_lightsheet_rampup_end)

        # mag trap ramp up
        self.inner_coil.ramp(t=self.p.t_magtrap_ramp,
                             i_start=self.p.i_magtrap_init,
                             i_end=self.p.i_magtrap_ramp_end)

        delay(self.p.t_magtrap)

        self.ttl.pd_scope_trig.pulse(t=1.e-6)
        # mag trap ramp down
        self.inner_coil.ramp(t=self.p.t_magtrap_rampdown,
                             i_start=self.p.i_magtrap_ramp_end,
                             i_end=0.,
                             n_steps=self.p.n_magtrap_ramp_steps)
        self.inner_coil.off()
        
        # feshbach field on, ramp up to field 1
        self.outer_coil.on()
        delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_evap1_current)

        # ligthsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_evap1_current,
                             i_end=self.p.i_evap2_current)

        # tweezer ramp up, constant paint amplitude
        self.ttl.pd_scope_trig.pulse(t=1.e-6)
        self.tweezer.on(paint=True)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)

        ## lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        ## tweezer evap 1 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
        #                   v_start=self.p.v_pd_tweezer_1064_ramp_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   paint=True,keep_trap_frequency_constant=True)

        ## feshbach field ramp to field 3
        # self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp2,
        #                      i_start=self.p.i_evap2_current,
        #                      i_end=self.p.i_evap3_current)
        
        ## tweezer evap 2 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
        #                   v_start=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
        #                   paint=True,keep_trap_frequency_constant=True)
        
        ## tweezer evap 3 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
        #                   v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
        #                   paint=True,keep_trap_frequency_constant=True,low_power=True)

        self.lightsheet.off()
        self.tweezer.off()
    
        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

        # mitigate spike for next run
        self.outer_coil.discharge()

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

