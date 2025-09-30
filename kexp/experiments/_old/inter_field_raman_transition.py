from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('frequency_detuned_imaging',np.arange(280.,295.,2)*1.e6)

        # self.xvar('do_pi_pulse_bool',[0,1])

        # self.xvar('t_tweezer_hold',np.linspace(0.,1000.e-3,10))

        # self.p.v_pd_tweezer_1064_rampdown3_end = .8

        # self.xvar('f_raman_transition',43.4222e6 + np.linspace(-7.e3,7.e3,15))
        # self.p.frequency_raman_transition = 41.236e6
        self.p.frequency_raman_transition = 41.294e6

        self.p.t_raman_pi_pulse = 2.507e-06
        # self.xvar('t_raman_pulse',np.linspace(0.,20.,50)*1.e-6)
        self.p.t_raman_pulse = 1.e-3

        # self.xvar('f_raman_sweep_width',np.linspace(3.e3,30.e3,20))
        # self.p.f_raman_sweep_width = 15.e3
        self.p.f_raman_sweep_width = 15.e3

        # self.xvar('f_raman_sweep_center',np.arange(41.21e6, 41.5e6, self.p.f_raman_sweep_width/2))
        # self.p.f_raman_sweep_center = 43.408e6
        # self.p.f_raman_sweep_center = self.p.frequency_raman_transition

        # self.xvar('t_raman_sweep',np.linspace(200.e-6,3.e-3,10))
        # self.p.t_raman_sweep = 1.e-3

        self.xvar('amp_raman',np.linspace(0.,self.p.amp_raman,8))
        # self.p.amp_raman = .15
        self.p.amp_raman = 0.25

        # self.p.t_max = 20.e-3
        # self.xvar('t_pulse',np.linspace(0.,self.p.t_max,10))

        self.p.frequency_tweezer_list = [74.e6]
        self.p.amp_tweezer_list = [.99]

        self.p.t_mot_load = 1.
        self.p.t_tof = 300.e-6
        # self.xvar('t_tof',np.linspace(20.,500.,4)*1.e-6)
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def set_up_imaging(self):
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging_midpoint)
        # self.set_high_field_imaging(i_outer=self.p.i_spin_mixture,pid_bool=True)

        self.set_imaging_detuning(self.p.frequency_detuned_imaging_m1)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging_0)
        # self.dds.imaging.set_dds(amplitude=.1)
        
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging_midpoint)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

    @kernel
    def scan_kernel(self):
        
        self.set_up_imaging()

        self.prepare_lf_tweezers()

        self.init_raman_beams()

        delay(1.e-3)

        # self.raman.pulse(t=self.p.t_raman_pi_pulse,frequency_transition=self.p.frequency_raman_transition)
        # delay(5.e-3)
        # self.dds.imaging.on()
        # self.raman.pulse(t=self.p.t_raman_pulse,frequency_transition=self.p.frequency_raman_transition)
        # delay(self.p.t_raman_pulse)
        # self.dds.imaging.off()

        self.raman.pulse(t=self.p.t_raman_pulse, frequency_transition=self.p.frequency_raman_transition)

        # self.raman.sweep(t=self.p.t_raman_sweep,
        #                  frequency_center=self.p.f_raman_sweep_center,
        #                  frequency_sweep_fullwidth=self.p.f_raman_sweep_width)
        
        # delay(1.e-3)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging_0)
        # self.dds.imaging.set_dds(amplitude=.095)

        delay(9.e-3)
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()        

        ### moved coil reset to cleanup_scan_kernel

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