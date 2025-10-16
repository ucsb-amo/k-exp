from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types
import numpy as np
from wax.control.slm.slm import SLM
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        # self.xvar('t_ramsey_delay',np.linspace(300.,330.,1)*1.e-6)

        self.p.do_dynamical_decoupling = 1
        # self.xvar('do_dynamical_decoupling',[0,1])
        # self.p.N_dd_pulses = 6
        # self.p.dt_dd_gap = (self.p.t_ramsey_delay - self.p.N_dd_pulses * self.p.t_raman_pi_pulse) / (self.p.N_dd_pulses + 1)

        self.p.frequency_ramsey_comb_filter = 150.e3
        # self.p.frequency_response_width = 1.e3 # limited by Ramsey coherence time?

        # placeholders
        self.p.t_ramsey_delay = 280.e-6
        self.p.dt_spacing_ramsey_comb_pulses = 0.
        self.p.N_ramsey_half_comb_pulses = 0
        self.p.t_ramsey_comb_padding = 0.

        self.p.t_tof = 10.e-6

        self.p.t_tweezer_hold = .1e-3
        self.p.t_mot_load = 1.
        self.p.N_repeats = 10

        self.p.frequency_raman_transition = 42.e6
        
        self.finish_prepare(shuffle=True)

    @kernel
    def compute_ramsey_comb_params(self):
        """Compute the comb params. Treating half the comb guarantees an even number of pi pulses in the comb.
        """        
        # self.p.t_ramsey_delay = 1 / self.p.frequency_response_width
        self.p.dt_spacing_ramsey_comb_pulses = 1 / (2*self.p.frequency_ramsey_comb_filter)
        self.p.N_ramsey_half_comb_pulses = int(np.floor((self.p.t_ramsey_delay + self.p.dt_spacing_ramsey_comb_pulses)/2 / (self.p.t_raman_pi_pulse + self.p.dt_spacing_ramsey_comb_pulses)))
        self.p.t_ramsey_comb_padding = (self.p.t_ramsey_delay + self.p.dt_spacing_ramsey_comb_pulses)/2 - self.p.N_ramsey_half_comb_pulses * ( self.p.t_raman_pi_pulse + self.p.dt_spacing_ramsey_comb_pulses )

    @kernel
    def scan_kernel(self):

        self.compute_ramsey_comb_params()

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging_m1)

        self.prepare_lf_tweezers()

        self.init_raman_beams(self.p.frequency_raman_transition,self.p.amp_raman)

        self.ttl.line_trigger.wait_for_line_trigger()
        delay(1.e-3)
        
        self.raman.pulse(self.p.t_raman_pi_pulse/2)
        
        if self.p.do_dynamical_decoupling:
            delay(self.p.t_ramsey_comb_padding) # intial padding
            # loop over and do the pulses
            for _ in range(2*self.p.N_ramsey_half_comb_pulses):
                self.raman.pulse(self.p.t_raman_pi_pulse)
                delay(self.p.dt_spacing_ramsey_comb_pulses)
            delay(-self.p.dt_spacing_ramsey_comb_pulses) # subtract off the last after-pulse delay (too many)
            delay(self.p.t_ramsey_comb_padding) # add on the second padding to make the sequence symmetric
        else:
            delay(self.p.t_ramsey_delay)

        self.raman.pulse(self.p.t_raman_pi_pulse/2)

        self.raman.pulse(self.p.t_raman_pi_pulse)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        # self.warmup(N=5)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)