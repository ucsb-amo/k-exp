from artiq.experiment import *
from artiq.language.core import delay, now_mu
from kexp import Base, img_types, cameras
import numpy as np
from kexp.util.artiq.async_print import aprint
# from kexp.control.slm.slm import SLM
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      save_data=True)

        # self.xvar('frequency_detuned_imaging',np.arange(300.,390.,5)*1.e6)
        # self.p.frequency_detuned_imaging = 325.e6 # 13.9 A
        self.p.frequency_detuned_imaging = 353.e6 # 13.2 A
        # self.p.frequency_detuned_imaging = 256.e6
        # self.p.frequency_detuned_imaging = -150.e6
        

        # self.xvar('hf_imaging_detuning', [272.e6,336.e6]*50)
        # self.xvar('frequency_detuned_imaging', [342.e6,364.e6]*1) # 13.1 A

        # self.xvar('beans',[0]*5)
        self.p.beans = 1
        
        self.xvar('t_tof',np.linspace(10.,100.,2)*1.e-6)
        # self.p.t_tof = 10.e-6

        # self.xvar('t_magtrap',np.linspace(500.,2500.,10)*1.e-6)

        # self.xvar('i_lf_lightsheet_evap1_current',np.linspace(11.,18.,15))
        # self.p.i_lf_lightsheet_evap1_current = 13.6

        # self.p.v_pd_lightsheet_rampup_end = 7.5
        
        # self.xvar('t_lf_lightsheet_rampdown',np.linspace(.1,1.5,8))
        # self.p.t_lf_lightsheet_rampdown = .5
 
        # self.xvar('v_pd_lf_lightsheet_rampdown_end',np.linspace(.25,1.,8))
        # self.p.v_pd_lf_lightsheet_rampdown_end = 1.

        # self.xvar('v_pd_lf_tweezer_1064_ramp_end',np.linspace(4.,9.3,10))
        # self.p.v_pd_lf_tweezer_1064_ramp_end = 7.5

        # self.xvar('t_lf_tweezer_1064_ramp',np.linspace(.02,.8,8))
        # self.p.t_lf_tweezer_1064_ramp = .28

        # self.xvar('i_lf_tweezer_load_current',np.linspace(12.5,16.,20))
        # self.p.i_lf_tweezer_load_current = 15.

        # self.xvar('t_tweezer_soak',np.linspace(0.,500.,15)*1.e-3)
        # self.p.t_tweezer_soak = 35.e-3

        # self.xvar('v_lf_tweezer_paint_amp_max',np.linspace(-6.,6.,10))
        # self.xvar('v_lf_tweezer_paint_amp_max',[-.6,3.6])
        self.p.v_lf_tweezer_paint_amp_max = 3.6

        # self.xvar('i_lf_tweezer_evap1_current',np.linspace(11.5,13.8,20))
        # self.p.i_lf_tweezer_evap1_current = 13.

        # self.xvar('v_pd_lf_tweezer_1064_rampdown_end',np.linspace(.9,3.,15)) 
        # self.p.v_pd_lf_tweezer_1064_rampdown_end = 1.25

        # self.xvar('t_lf_tweezer_1064_rampdown',np.linspace(0.02,.4,20))
        # self.p.t_lf_tweezer_1064_rampdown = .14

        # self.xvar('i_lf_tweezer_evap2_current',np.linspace(12.4,14.,8))
        # self.p.i_lf_tweezer_evap2_current = 13.

        # self.xvar('v_pd_lf_tweezer_1064_rampdown2_end',np.linspace(.08,.2,20))
        # self.p.v_pd_lf_tweezer_1064_rampdown2_end = .18

        # self.xvar('t_lf_tweezer_1064_rampdown2',np.linspace(0.1,.7,20))
        # self.p.t_lf_tweezer_1064_rampdown2 =360.6e-3

        # self.xvar('frequency_detuned_imaging_m1',self.p.frequency_detuned_imaging_m1 + np.linspace(-3.,3.,12)*1.e6)

        # self.xvar('t_ramp_down_painting_amp',np.linspace(15.,400.,10)*1.e-3)
        self.p.t_ramp_down_painting_amp = 200.e-3

        # self.xvar('v_paint_amp_end',np.linspace(-7.,-4.,2))
        self.p.v_paint_amp_end = -5.

        self.p.frequency_tweezer_list = [75.4e6]
        a_list = [.15]
        self.p.amp_tweezer_list = a_list

        # self.xvar('t_tweezer_hold',np.linspace(0.,60.,10)*1.e-3)
        self.p.t_tweezer_hold = 1.0e-3

        # self.xvar('beans',[0,1])

        self.p.t_mot_load = 1.
        self.p.N_repeats = 1

        # self.camera_params.amp_imaging = .12
        self.camera_params.exposure_time = 20.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time
        # self.camera_params.amp_imaging = 0.54

        # self.xvar('amp_imaging',np.linspace(.2,.45,10))
        self.p.amp_imaging = .25

        # self.xvar('phase_slm_mask',np.linspace(0.,1.,10)*np.pi)
        # self.xvar('phase_slm_mask',[1.745,3.14]*50)
        self.p.phase_slm_mask = 0.

        # self.xvar('imaging_polarization_h',[0,1])

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        # self.set_high_field_imaging(i_outer=self.p.i_lf_tweezer_load_current,
        #                             pid_bool=False)
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging_m1)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,self.p.v_yshim_current_magtrap,0.,n=500)
        
        self.ttl.d2_mot_shutter.off()
        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        # delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                            i_start=0.,
                            i_end=self.p.i_lf_lightsheet_evap1_current)

        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lf_lightsheet_rampdown,
                            v_start=self.p.v_pd_lightsheet_rampup_end,
                            v_end=self.p.v_pd_lf_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                            i_start=self.p.i_lf_lightsheet_evap1_current,
                            i_end=self.p.i_lf_tweezer_load_current)
        
        self.tweezer.on(paint=True)
        self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_ramp,
                        v_start=0.,
                        v_end=self.p.v_pd_lf_tweezer_1064_ramp_end,
                        paint=True,keep_trap_frequency_constant=False,
                        v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)
        
        # delay(self.p.t_tweezer_soak)
        
        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lf_lightsheet_rampdown2,
                            v_start=self.p.v_pd_lf_lightsheet_rampdown_end,
                            v_end=self.p.v_pd_lightsheet_rampdown3_end)
        
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
        
        # tweezer evap 2 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_rampdown2,
                        v_start=self.p.v_pd_lf_tweezer_1064_rampdown_end,
                        v_end=self.p.v_pd_lf_tweezer_1064_rampdown2_end,
                        paint=True,keep_trap_frequency_constant=True,
                        v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                            i_start=self.p.i_lf_tweezer_evap2_current,
                            i_end=self.p.i_spin_mixture)
        
        self.dac.tweezer_paint_amp.linear_ramp(t=self.p.t_ramp_down_painting_amp,
                                               v_start=self.dac.tweezer_paint_amp.v,
                                               v_end=self.p.v_paint_amp_end,
                                               n=1000)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()
        
        self.outer_coil.off()
        self.outer_coil.discharge()

    @kernel
    def run(self):
        self.init_kernel(setup_awg=True,setup_slm=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)