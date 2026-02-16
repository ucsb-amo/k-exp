from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,camera_select=cameras.xy_basler,
                      imaging_type=img_types.ABSORPTION)

        self.p.t_tof = 1000.e-6
        # self.xvar('t_tof',np.linspace(100,1200.,10)*1.e-6)
        # self.xvar('t_tof',np.linspace(5.,20.,10)*1.e-3)
        # self.xvar('dumy',[0,1]*2)

        # self.xvar('hf_imaging_detuning', [-594.e6,-494.e6])

        # self.xvar('t_pump_to_F1',np.linspace(0.05,10.,10)*1.e-6)

        # self.xvar('t_magtrap',np.linspace(0.,5000.,10)*1.e-3)
        # self.p.t_magtrap = .5

        # self.xvar('i_magtrap_init',np.linspace(75.,97.,10))
        # self.p.i_magtrap_init = 95.

        # self.p.v_yshim_current = 2.2

        # self.p.v_zshim_current_gm = 0.68
        # self.p.v_xshim_current_gm = 0.5 

        # self.p.pfrac_c_gmramp_end = 0.3
        # self.p.pfrac_r_gmramp_end = 0.2

        # self.xvar('v_zshim_current_magtrap',np.linspace(0.,3.,15))
        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,5.,10))
        # self.xvar('v_yshim_current_magtrap',np.linspace(4.,9.9,10))
        # self.p.v_zshim_current_magtrap_init = 0.
        # self.p.v_yshim_current_magtrap = 6.
        # self.p.v_xshim_current_magtrap = 0.5
        # self.xvar('t_shim_delay',np.linspace(0.05,15.,20)*1.e-3)
        # self.p.t_shim_delay = 3.4e-3

        # self.xvar('t_magtrap_rampdown',np.linspace(5.,150.,15)*1.e-3)
        # self.p.t_magtrap_rampdown = 87.e-3

        # self.xvar('t_yshim_rampdown',np.linspace(5.,100.,15)*1.e-3)
        # self.p.t_yshim_rampdown = 10.e-3

        # self.xvar('t_feshbach_field_rampup',np.linspace(15.,250.,15)*1.e-3)
        # self.p.t_feshbach_field_rampup = 150.e-3

        # self.xvar('t_lightsheet_rampup',np.linspace(20.,400.,15)*1.e-3)
        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(5.,8.,10))
        # self.p.t_lightsheet_rampup = 4.
        # self.p.v_pd_lightsheet_rampup_end = 7.2

        # self.xvar('i_hf_lightsheet_evap1_current',np.linspace(191.,195.,15))
        # self.p.i_hf_lightsheet_evap1_current = 193.57
        # self.p.i_hf_lightsheet_evap1_current = 18.
 
        # self.xvar('v_pd_hf_lightsheet_rampdown_end',np.linspace(.3,3.,20))
        # self.p.v_pd_hf_lightsheet_rampdown_end = .65

        # self.xvar('t_hf_lightsheet_rampdown',np.linspace(100.,1000.,8)*1.e-3)
        # self.p.t_hf_lightsheet_rampdown = .45
        # self.p.t_hf_lightsheet_rampdown = 0.4401463

        # self.xvar('v_pd_hf_lightsheet_rampdown2_end',np.linspace(.1,.4,15))
        # self.p.v_pd_hf_lightsheet_rampdown2_end = 0.25

        # self.xvar('t_hf_lightsheet_rampdown2',np.linspace(100.,1000.,8)*1.e-3)
        # self.p.t_hf_lightsheet_rampdown2 = 0.74

        # self.xvar('i_hf_lightsheet_evap2_current',np.linspace(192.,194.5,8))
        # self.p.i_hf_lightsheet_evap2_current = 193.3
        
        self.p.t_lightsheet_hold = .1

        # self.p.t_magtrap = 1.5
        # self.xvar('t_imaging_pulse',np.linspace(1.,20.,20)*1.e-6)
        # self.p.t_imaging_pulse = 2.e-5    

        # self.xvar('amp_imaging',np.linspace(.05,.3,10))

        # self.xvar('hf_imaging_detuning', np.arange(-150.,180.,10.)*1.e6)
        
        # self.xvar('hf_imaging_detuning', np.arange(-670.,-600.,6.)*1.e6)
        # self.p.hf_imaging_detuning = -490.e6
        # self.p.hf_imaging_detuning = -594.e6
       
        # self.camera_params.exposure_time = 25.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        # self.camera_params.em_gain = 1.
        self.p.amp_imaging = .13

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        # self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        self.set_high_field_imaging(i_outer=self.p.i_hf_lightsheet_evap1_current)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        # self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False,do_magtrap_rampdown=True)
        # self.inner_coil.snap_off()

        # feshbach field on, ramp up to field 1
        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_hf_lightsheet_evap1_current)
        
        self.set_shims(0.,0.,0.)

        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_hf_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_hf_lightsheet_rampdown_end)
        
        # self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
        #                      i_start=self.p.i_hf_lightsheet_evap1_current,
        #                      i_end=self.p.i_hf_lightsheet_evap2_current)
        
        # # lightsheet evap 2
        # self.lightsheet.ramp(t=self.p.t_hf_lightsheet_rampdown2,
        #                      v_start=self.p.v_pd_hf_lightsheet_rampdown_end,
        #                      v_end=self.p.v_pd_hf_lightsheet_rampdown2_end)

        delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        delay(self.p.t_tof)
        self.abs_image()

        # self.lightsheet.off()

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
