from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.control.slm.slm import SLM
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        # self.xvar('frequency_detuned_imaging',np.arange(320.,360.,3)*1.e6)
        self.p.frequency_detuned_imaging = 346.e6
        # self.xvar('beans',[0]*10)

        self.xvar('t_tof',np.linspace(100.,1200.,10)*1.e-6)
        self.p.t_tof = 1500.e-6

        # self.xvar('t_feshbach_field_rampup',np.linspace(15.,100.,10)*1.e-3)
        # self.t_feshbach_field_rampup = 100.e-3
        
        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(6.5,9.9,6))
        # self.p.v_pd_lightsheet_rampup_end = 9.9

        # self.xvar('t_magtrap',np.linspace(.5,3.,20))

        # self.xvar('i_lf_lightsheet_evap1_current',np.linspace(12.,17.,10))
        # self.p.i_lf_lightsheet_evap1_current = 13.1
        
        # self.xvar('t_lightsheet_rampdown',np.linspace(.1,1.5,8))
        # self.p.t_lightsheet_rampdown = .4
 
        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(.5,1.5,10))
        # self.p.v_pd_lightsheet_rampdown_end = 1.

        # self.xvar('t_lightsheet_hold',np.linspace(1.,5000.,5)*1.e-3)
        # self.p.t_lightsheet_hold = .1

        # self.xvar('i_lf_tweezer_load_current',np.linspace(12.,17.,8))
        # self.p.i_lf_tweezer_load_current = 15.5

        # self.xvar('t_tweezer_hold',np.linspace(1.,500.,10)*1.e-3)
        self.p.t_tweezer_hold = 10.e-3

        # self.xvar('v_lf_tweezer_paint_amp_max',np.linspace(-2.,6.,15))
        # self.p.v_lf_tweezer_paint_amp_max = 4.5

        # self.xvar('v_pd_lf_tweezer_1064_ramp_end', np.linspace(5.,9.4,10))
        # self.p.v_pd_lf_tweezer_1064_ramp_end = 9.4

        # self.xvar('t_tweezer_1064_ramp', np.linspace(15.,1000.,10)*1.e-3)
        # self.p.t_tweezer_1064_ramp = .5

        # self.xvar('i_lf_tweezer_evap1_current',np.linspace(12.5,14.5,8))
        # self.p.i_lf_tweezer_evap1_current = 12.7

        # self.xvar('v_pd_lf_tweezer_1064_rampdown_end',np.linspace(.2,3.,8)) 
        # self.p.v_pd_lf_tweezer_1064_rampdown_end = .8

        # self.xvar('t_lf_tweezer_1064_rampdown',np.linspace(0.02,.3,8))
        # self.p.t_lf_tweezer_1064_rampdown = 180.e-3

        # self.xvar('i_lf_tweezer_evap2_current',np.linspace(12.5,14.,8))
        # self.p.i_lf_tweezer_evap2_current = 13.8

        # self.xvar('v_pd_lf_tweezer_1064_rampdown2_end',np.linspace(.07,.2,10))
        # self.p.v_pd_lf_tweezer_1064_rampdown2_end = .11

        # self.xvar('t_lf_tweezer_1064_rampdown2',np.linspace(0.1,.8,8))
        # self.p.t_lf_tweezer_1064_rampdown2 = 400.e-3

        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(.5,4.5,10))
        # self.p.v_pd_tweezer_1064_rampdown3_end = 1.

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.2,.7,10))
        # self.p.t_tweezer_1064_rampdown3 = .4

        self.p.frequency_tweezer_list = [74.e6]
        a_list = [.2]
        self.p.amp_tweezer_list = a_list

        # self.xvar('beans',[0,1])

        self.p.t_mot_load = 1.
        self.p.N_repeats = 1

        # self.camera_params.amp_imaging = .12
        # self.camera_params.exposure_time = 10.e-6
        # self.p.t_imaging_pulse = self.camera_params.exposure_time

        # self.xvar('amp_imaging',np.linspace(.05,.2,10))

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.slm.write_phase_mask_kernel()
        self.set_high_field_imaging(i_outer=self.p.i_lf_tweezer_evap2_current,
                                    pid_bool=False)
        # self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging)
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
        # delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_lf_lightsheet_evap1_current)
        
        self.set_shims(v_zshim_current=0.,
                        v_yshim_current=0.,
                        v_xshim_current=0.)

        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lf_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lf_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_lightsheet_evap1_current,
                             i_end=self.p.i_lf_tweezer_load_current)
        
        
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_lf_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False,
                          v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)
        
        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lf_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lf_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        # delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_tweezer_load_current,
                             i_end=self.p.i_lf_tweezer_evap1_current)

        
        # # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_lf_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_lf_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True,
                          v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_tweezer_evap1_current,
                             i_end=self.p.i_lf_tweezer_evap2_current)
        
        # # # # tweezer evap 2 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_rampdown2,
        #                   v_start=self.p.v_pd_lf_tweezer_1064_rampdown_end,
        #                   v_end=self.p.v_pd_lf_tweezer_1064_rampdown2_end,
        #                   paint=True,keep_trap_frequency_constant=True,
        #                   v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)
        
        # delay(2.e-3)
        # # tweezer evap 3 with constant trap frequency
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_rampdown3,
        #                   v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_lf_tweezer_1064_rampdown2_end),
        #                   v_end=self.p.v_pd_lf_tweezer_1064_rampdown3_end,
        #                   paint=True,keep_trap_frequency_constant=True,low_power=True,v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        # self.outer_coil.stop_pid()
        # delay(50.e-3)

        self.abs_image()
        
        self.outer_coil.off()
        self.outer_coil.discharge()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)