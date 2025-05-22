from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from kexp.calibrations.magnets import compute_pid_overhead

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,save_data=False)
        self.xvar('beans',[0]*5)
        # self.p.imaging_state = 2.

        # self.xvar('frequency_detuned_imaging',np.arange(240.,550.,6)*1.e6)
        
        self.p.frequency_detuned_imaging = 294.e6 # i-18.3

        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(6.5,9.9,6))
        # self.p.v_pd_lightsheet_rampup_end = 9.9
        
        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,8))
        # self.p.t_lightsheet_rampdown = .16

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(.7,2.5,20))
        self.p.v_pd_lightsheet_rampdown_end = 1.5
        # self.p.v_pd_lightsheet_rampdown_end = .78


        # self.xvar('t_lightsheet_hold',np.linspace(1.,5000.,5)*1.e-3)
        # self.p.t_lightsheet_hold = .1

        # self.xvar('t_tweezer_hold',np.linspace(1.,800.,10)*1.e-3)
        self.p.t_tweezer_hold = 300.e-3

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-7.,0.,10))
        self.p.v_tweezer_paint_amp_max = -7.

        # self.xvar('v_pd_tweezer_1064_ramp_end', np.linspace(3.,9.,15))
        self.p.v_pd_tweezer_1064_ramp_end = 5.1

        self.p.i_lf_lightsheet_evap1_current = 16.

        self.p.i_lf_tweezer_load_current = 14.5
        # self.p.i_lf_evap3_current = 18.23

        # self.p.i_spin_mixture = 24.3
        self.p.i_spin_mixture = 20.57

        # self.xvar('t_raman_pulse',np.linspace(10.e-6,20.e-3,5))
        # self.p.t_raman_pulse = 500.e-6
        # self.p.f_raman_transition = 41.23e6
        # self.xvar('f_raman_transition',43.405e6 + np.linspace(-10.e3,10.e3,20))
        self.p.f_raman_transition = 43.4024e6

        # self.xvar('f_raman_sweep_center',np.linspace(39.e6,45.e6,40))
        # self.xvar('f_raman_sweep_center',np.linspace(43.35e6,43.48e6,10))
        # self.xvar('f_raman_sweep_center',np.linspace(44.0,45.5,15)*1.e6)
        # self.xvar('f_raman_sweep_center',76.4e6 + 2.e6*np.linspace(-1.,1.,60))
        self.p.f_raman_sweep_center = 43.405e6
        # self.p.f_raman_sweep_center = 41.39e6

        # self.xvar('t_raman_sweep',np.linspace(200.e-6,3.e-3,10))
        # self.p.t_raman_sweep = 1.8e-3
        self.p.t_raman_sweep = 1.e-3
        self.p.t_raman_pulse = 500.e-6
        # self.xvar('t_raman_pulse',np.linspace(1.,50.,20)*1.e-6)
        
        # self.xvar('f_raman_sweep_width',np.linspace(3.e3,30.e3,20))
        # self.p.f_raman_sweep_width = 350.e3
        self.p.f_raman_sweep_width = 15.e3

        # self.xvar('amp_raman',np.linspace(.02,.15,20))
        self.p.amp_raman = .09

        # self.p.frequency_tweezer_list = [73.7e6,76.e6]
        self.p.frequency_tweezer_list = [76.e6]
        # self.p.frequency_tweezer_list = np.linspace(76.e6,78.e6,6)

        # a_list = [.45,.55]
        # a_list = [.14,.145]
        a_list = [.145]
        self.p.amp_tweezer_list = a_list

        # self.xvar('beans',[0,1])

        self.p.t_mot_load = 1.

        # self.xvar('t_tof',np.linspace(100.,3000.,10)*1.e-6)

        self.p.t_tof = 20.e-6
        self.p.N_repeats = 1


        # self.camera_params.amp_imaging = .12
        # self.camera_params.exposure_time = 10.e-6
        # self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # i = 50.
        i = 20.

        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        # delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_lf_lightsheet_evap1_current)
        
        # 

        
        # feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_lightsheet_evap1_current,
                             i_end=self.p.i_lf_tweezer_load_current)
        
        #


        self.outer_coil.ramp_supply(t=20.e-3,
                             i_start=self.p.i_lf_tweezer_load_current,
                             i_end=self.p.i_spin_mixture)
        
        
        self.outer_coil.start_pid()
        self.ttl.pd_scope_trig.pulse(1.e-6)
        delay(100.e-3)

        # self.dds.raman_minus.set_dds(amplitude=self.p.amp_raman)
        # self.dds.raman_plus.set_dds(amplitude=self.p.amp_raman)

        # delay(100.e-3)

        # self.dds.raman_minus.on()
        # delay(self.p.t_raman_pulse)
        # self.dds.raman_minus.off()

        # self.dds.raman_plus.on()
        # delay(self.p.t_raman_pulse)
        # self.dds.raman_plus.off()

        # self.raman.pulse(t=self.p.t_raman_pulse,frequency_transition=self.p.f_raman_transition)
        # delay(self.p.t_raman_pulse)
        # self.raman.sweep(t=self.p.t_raman_sweep,frequency_center=self.p.f_raman_sweep_center,frequency_sweep_fullwidth=self.p.f_raman_sweep_width)
        # delay(self.p.t_raman_sweep)

        # delay(50.e-3)

        # if self.p.turn_off_pid_before_imaging_bool:
        #     self.outer_coil.stop_pid()
        #     delay(50.e-3)
        # else:
        #     delay(80.e-3)

        # delay(self.p.t_tweezer_hold)
        #self.tweezer.off()

        #delay(self.p.t_tof)
        #self.abs_image()

        self.outer_coil.stop_pid()
        delay(100.e-3)

        self.outer_coil.off()
        self.outer_coil.discharge()

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,
                         dds_off=False,
                         dds_set=False,
                         init_shuttler=False,
                         init_lightsheet=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)