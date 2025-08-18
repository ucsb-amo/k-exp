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

        # self.xvar('frequency_detuned_imaging',np.arange(250.,320.,3)*1.e6)
        self.p.frequency_detuned_imaging = 289.e6
        # self.xvar('beans',[0]*500)

        # self.xvar('hf_imaging_detuning', [340.e6,420.e6]*1)
        
        # self.xvar('t_tof',np.linspace(100.,1000.,10)*1.e-6)
        self.p.t_tof = 300.e-6

        self.p.frequency_tweezer_list = [75.3e6]
        a_list = [.15]
        self.p.amp_tweezer_list = a_list

        # self.xvar('f_raman_sweep_width',np.linspace(10.e3,60.e3,6))
        self.p.f_raman_sweep_width = 15.e3

        # self.xvar('t_raman_sweep',np.linspace(200.e-6,3.e-3,10))
        self.p.t_raman_sweep = 500.e-6

        # self.xvar('frequency_raman_transition',42.27*1e6 + np.linspace(-1.e5,1.e5,15))
        # self.xvar('frequency_raman_transition',np.linspace(41.,43.5,25)*1e6)
        # self.p.frequency_raman_transition = 41.236e6
        # self.p.frequency_raman_transition = 43.e6
        self.p.frequency_raman_transition = 41.10e6 # this one
        # self.p.frequency_raman_transition = 42.e6

        # self.xvar('amp_raman',np.linspace(0.12,.35,5))
        self.p.amp_raman = .35

        # self.p.t_raman_pi_pulse = 2.507e-06
        # self.xvar('t_raman_pulse',np.linspace(0.,300.,100)*1.e-6)
        # self.xvar('t_raman_pulse',np.linspace(0.,30.,30)*1.e-6)
        t_pi_time = 5.6566e-06 # 42525 # 5.0937e-06 
        # self.xvar('t_raman_pulse',np.arange(0.,15. + 1.,1) * t_pi_time *0.5)
        self.p.t_raman_pi_pulse = t_pi_time
        # self.p.t_raman_pulse = 0.
        self.xvar('t_ramsey_wait',np.linspace(0.,50.,6)*1.e-6)
        # self.p.t_ramsey_wait = 34.5e-6
        # self.xvar('t_tweezer_hold',np.linspace(0.,1.5,10)*1.e-3)
        self.p.t_tweezer_hold = .1e-3

        self.p.t_mot_load = 1.
        self.p.N_repeats = 2

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.slm.write_phase_mask_kernel()
        # self.set_high_field_imaging(i_outer=self.p.i_spin_mixture,
        #                             pid_bool=False)
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.prepare_lf_tweezers()

        self.init_raman_beams(frequency_transition=self.p.frequency_raman_transition,
                              amp_raman=self.p.amp_raman)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(1.e-3)

        self.raman.pulse(self.p.t_raman_pi_pulse/2)
        delay(self.p.t_ramsey_wait)
        self.raman.pulse(self.p.t_raman_pi_pulse/2)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

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