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
        
        # self.xvar('t_tof',np.linspace(100.,1000.,10)*1.e-6)
        self.p.t_tof = 600.e-6
        self.line_trigger_phase_delay = 0.0
        # self.xvar('line_trigger_phase_delay', np.linspace(0., 15.e-3, 10))
        f_range = 20.e3
        df = 5.e3
        self.p.frequency_raman_transition = 41.1095e6
        self.xvar('frequency_raman_transition',
                  self.p.frequency_raman_transition + np.arange(-f_range, f_range, df))

        # self.xvar('amp_raman',np.linspace(0.12,.35,5))

        # self.xvar('t_raman_pulse',np.linspace(0.,300.,100)*1.e-6)

        # T = 1/self.p.frequency_raman_transition
        # N = 10
        # dt = T / N
        # self.xvar('t_ramsey_delay',10.e-6 + np.arange(0.,50.e-9,8.e-9))
        # self.xvar('t_ramsey_delay',5.e-6 + np.arange(0.,T+dt,dt))
        self.xvar('t_ramsey_delay', np.linspace(0.,90.,10)*1.e-6)
        self.p.t_ramsey_delay = 55.e-6
        # self.xvar('line_trigger_phase_delay', np.linspace(0.00, 0.017, 10))
        self.p.line_trigger_phase_delay = 0.0057
        # self.xvar('t_tweezer_hold',np.linspace(0.,1.5,10)*1.e-3)
        self.p.t_tweezer_hold = .1e-3
        # self.xvar('do_pi_pulse',[0,1])
        self.p.do_pi_pulse = 0

        self.p.t_mot_load = 1.
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(self.p.frequency_detuned_imaging_m1)

        self.prepare_lf_tweezers()
        self.ttl.d2_mot_shutter.off()

        self.init_raman_beams(self.p.frequency_raman_transition,self.p.amp_raman)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(1.e-3)
        delay(self.p.line_trigger_phase_delay)

        if self.p.do_pi_pulse:
            self.raman.pulse(self.p.t_raman_pi_pulse)
        else:
            delay(self.p.t_raman_pi_pulse)
        
        self.raman.pulse(self.p.t_raman_pi_pulse/2)
        delay(self.p.t_ramsey_delay)
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