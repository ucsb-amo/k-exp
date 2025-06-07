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

        # self.xvar('frequency_detuned_imaging',np.arange(300.,336.,2)*1.e6)
        
        # IMAGING FREQUENCIES IN FREE SPACE
        # self.xvar('frequency_detuned_imaging',[298.2e6, 284.e6])
        self.p.frequency_detuned_imaging_m1 = 286.e6
        self.p.frequency_detuned_imaging_0 = 318.e6
        # self.p.frequency_detuned_imaging_midpoint = 298.e6
        self.p.frequency_detuned_imaging_midpoint = 615.e6
        # self.xvar('frequency_detuned_imaging_midpoint',np.arange(280.,400.,6)*1.e6)

        # self.xvar('amp_imaging',np.linspace(0.0,.13,8))
        self.p.amp_imaging = .09

        self.p.v_pd_tweezer_1064_rampdown3_end = 1.2

        self.p.i_spin_mixture = 19.48

        # self.xvar('f_raman_transition',43.4222e6 + np.linspace(-7.e3,7.e3,15))
        self.p.frequency_raman_transition = 41.247e6

        # self.p.frequency_detuned_raman_transition = 41.989e6
        self.p.frequency_detuned_raman_transition = 41.5e6
        
        # self.xvar('t_raman_pulse',np.linspace(0.,30.,30)*1.e-6)
        self.p.t_raman_pulse = 30.e-6

        self.p.t_raman_pi_pulse = 3.5e-06
        # self.xvar('t_raman_pulse',np.linspace(0.,self.p.t_raman_pi_pulse,15))
        # self.xvar('t_raman_pulse',np.linspace(0.,20.,40)*1.e-6)
        # self.p.t_raman_pulse = 30.e-6

        self.xvar('pulse_delay',np.linspace(0.,50.,10)*1.e-6)

        # self.xvar('amp_raman',np.linspace(.02,.15,20))
        self.p.amp_raman_plus = .25
        self.p.amp_raman_minus = .25
        self.p.amp_raman = .25

        # self.p.t_max = 20.e-3
        # self.xvar('t_pulse',np.linspace(0.,self.p.t_max,10))

        self.p.frequency_tweezer_list = [74.e6]
        self.p.amp_tweezer_list = [.75]

        self.p.t_mot_load = 1.
        self.p.t_tof = 500.e-6
        # self.xvar('t_tof',np.linspace(20.,500.,4)*1.e-6)
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        ### prepares the atoms and turns on the PID at self.p.i_spin_mixture ###
        self.prepare_lf_tweezers()
        ### start experiment ###

        self.dds.raman_minus.set_dds(amplitude=self.p.amp_raman)
        self.dds.raman_plus.set_dds(amplitude=self.p.amp_raman)

        # self.raman.pulse(t=self.p.t_raman_pi_pulse,frequency_transition=self.p.frequency_raman_transition)
        # delay(5.e-3)
        # self.dds.imaging.on()
        # self.raman.pulse(t=self.p.t_raman_pulse,frequency_transition=self.p.frequency_raman_transition)
        # delay(self.p.t_raman_pulse)
        # self.dds.imaging.off()

        self.raman.pulse(t=self.p.t_raman_pi_pulse,frequency_transition=self.p.frequency_raman_transition)
        delay(self.p.pulse_delay)
        self.raman.pulse(t=self.p.t_raman_pi_pulse,frequency_transition=self.p.frequency_raman_transition)
        delay(self.p.pulse_delay)
        self.raman.pulse(t=self.p.t_raman_pi_pulse,frequency_transition=self.p.frequency_raman_transition)
        delay(self.p.pulse_delay)
        
        self.set_imaging_detuning(self.p.frequency_detuned_imaging_0)
        self.dds.imaging.set_dds(amplitude=.1)

        # delay(self.p.t_tweezer_hold)
        delay(10.e-3)
        self.tweezer.off()

        delay(self.p.t_tof)
        # delay(.5e-6)
        self.abs_image()        

        self.outer_coil.stop_pid()

        self.outer_coil.off()
        self.outer_coil.discharge()

        self.dac.supply_current_2dmot.set(v=self.p.v_2d_mot_current)

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