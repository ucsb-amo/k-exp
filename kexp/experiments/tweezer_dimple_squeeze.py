from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

T32 = 1<<32

class tweezer_dimple_squeeze(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        # self.p.imaging_state = 1.
        # self.xvar('frequency_detuned_imaging',np.arange(-630.,-500.,10)*1.e6)
        # self.p.frequency_detuned_imaging = -614.6e6 # i = 193., from 1,-1 sigma-
        # self.p.frequency_detuned_imaging = -610.9e6 # i = 191.9., for 1,-1 sigma-
        # self.p.frequency_detuned_imaging = -565.e6 # i = 181., for 1,-1 sigma-
        # self.p.frequency_detuned_imaging = -552.35e6 # i = 178., for 1,-1 sigma-
        # self.p.frequency_detuned_imaging = -505.e6 # i = 193., from 1,0 sigma-
        
        # self.p.frequency_detuned_imaging = 424.e6 # 
        # self.p.frequency_detuned_imaging = 412.e6 # NI

        self.p.t_mot_load = .75

        # self.xvar('v_lightsheet_paint_amp_max',np.arange(-7.,6.,1))

        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(8.5,9.99,5))

        # self.xvar('i_evap1_current',np.linspace(190.,194.,8))
        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,8))

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(1.,6.,10))
        self.p.v_pd_lightsheet_rampdown_end = 3.

        # self.xvar('freq_tweezer_modulation',np.linspace(100.e3,536.e3,20))
        # self.xvar('freq_tweezer_modulation',[])
        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-4.,6.,5))
        # self.p.freq_tweezer_modulation = 2.15e3
        self.p.v_tweezer_paint_amp_max = 6.

        # self.xvar('i_evap2_current',np.linspace(191.,194.,8))
        self.p.i_evap2_current = 191.9

        ## v_pd 6.5, paint amp 6. gives long lifetime at 200-300 kHz painting
        # self.xvar('v_pd_tweezer_1064_ramp_end', np.linspace(4.,9.9,6))
        self.p.v_pd_tweezer_1064_ramp_end = 4.

        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,200.,10)*1.e-3)
        self.p.t_tweezer_1064_ramp = .09

        self.p.t_dimple_squeeze = 0.01
        # self.xvar('t_dimple_squeeze',np.linspace(0.01,0.1,5))

        # self.xvar('v_awg_paint_amp_dimple_squeeze_end',np.linspace(-6.,v_initial_squeeze,10))
        # self.p.v_awg_paint_amp_dimple_squeeze_end = 4.666
        self.p.v_awg_paint_amp_dimple_squeeze_end = 6.

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

        self.p.i_sqeeze_current = 178.
        # self.xvar('i_sqeeze_current',np.linspace(178.,193.,8))

        # self.xvar('t_tweezer_hold',np.linspace(1.,1000.,10)*1.e-3)
        self.p.t_tweezer_hold = 125.e-3

        # self.xvar('v_pd_tweezer_1064_adiabatic_stretch_ramp_end',np.linspace())

        self.xvar('t_tof',np.linspace(25.,150.,10)*1.e-6)
        # self.xvar('t_tof',np.linspace(0.1,10.,10)*1.e-3)
        self.p.t_tof = 10.e-6
        self.p.N_repeats = [1]
        
        # self.xvar('dummy_z',[0]*500)

        self.p.n_tweezers = 1
        # self.xvar('frequency_tweezer_array_width',np.linspace(.2e6,1.e6,6))
        # self.p.frequency_tweezer_array_width = .7e6
        # self.p.amp_tweezer_auto_compute = False
        # self.xvar('amp_tweezer_list')
        self.p.amp_tweezer_list = [.17]

        self.p.t_magtrap_ramp = 0.01
        self.p.t_magtrap = 0.
        self.p.t_magtrap_rampdown = 0.01

        # self.xvar('amp_imaging',np.linspace(.06,.2,15))
        # self.xvar('amp_imaging',np.linspace(.04,.09,20))
        # self.camera_params.amp_imaging = 0.106
        # # self.camera_params.amp_imaging = 0.248
        # self.camera_params.exposure_time = 20.e-6
        # self.camera_params.exposure_time = 10.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        self.camera_params.em_gain = 300

        self.p.n_tweezer_ramp_steps = 100

        self.p.t_lightsheet_hold = 100.e-3

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(amp=self.p.amp_imaging)
        self.set_high_field_imaging(i_outer = self.p.i_sqeeze_current)

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

        # magtrap + lightsheet hold
        delay(self.p.t_magtrap)

        # mag trap ramp down
        self.inner_coil.ramp(t=self.p.t_magtrap_rampdown,
                             i_start=self.p.i_magtrap_ramp_end,
                             i_end=0.)
        self.inner_coil.off()

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

        # tweezer ramp up, constant paint amplitude
        self.ttl.pd_scope_trig.pulse(t=1.e-6)
        self.tweezer.on(paint=True)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # make scattering length even smaller - feshbach field ramp again
        self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_evap2_current,
                             i_end=self.p.i_sqeeze_current)
        delay(self.p.t_feshbach_field_ramp)

        # squeezing
        self.tweezer.paint_amp_dac.linear_ramp(t=self.p.t_dimple_squeeze,
                                               v_start=self.p.v_tweezer_paint_amp_max,
                                               v_end=self.p.v_awg_paint_amp_dimple_squeeze_end,
                                               n=1000)

        # delay(self.p.t_dimple_squeeze)

        # # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        # # tweezer evap 1 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
        #                   v_start=self.p.v_pd_tweezer_1064_ramp_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   paint=True,keep_trap_frequency_constant=True)

        # # feshbach field ramp to field 3
        # self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp2,
        #                      i_start=self.p.i_evap2_current,
        #                      i_end=self.p.i_evap3_current)
        
        # # tweezer evap 2 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
        #                   v_start=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
        #                   paint=True,keep_trap_frequency_constant=True)
        
        # # tweezer evap 3 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
        #                   v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
        #                   paint=True,keep_trap_frequency_constant=True,low_power=True)

        # self.outer_coil.ramp(t=30.e-3,
        #                      i_start=self.p.i_sqeeze_current,
        #                      i_end=178.)
        # self.lightsheet.off()

        delay(self.p.t_tweezer_hold)

        self.lightsheet.off()
        
        self.tweezer.off()
    
        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

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

