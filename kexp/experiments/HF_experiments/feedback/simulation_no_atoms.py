from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras
from kexp.base import Feedback
from kexp.calibrations.imaging import integrator_calibration
import numpy as np
from numpy import int64

from kexp.util.artiq.async_print import aprint

T_CONV_MU = 30

from waxx.control.artiq.DDS import T_AD9910_REGISTER_UPDATE_FROM_PHASE_ORIGIN_MU

from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams as ExptParamsFeedback

class feedback(EnvExperiment, Base, Feedback):

    def prepare(self):

        self.p = ExptParamsFeedback()
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE,
                      expt_params=self.p)
        self.p.update_raman_frequency_bool = 1
        self.p.include_photon_noise = 1
        
        ### parameters

        self.p.feedback_fractional_initial_offset = 2.
        # self.xvar('feedback_fractional_initial_offset', np.linspace(-5.,5.,21))
        
        self.p.N_repeats = 1

        self.p.feedback_guess_span_Omega = 5.0

        ###

        self.p.t_between_pulses_mu += 10000
        # timing docs: https://docs.google.com/document/d/11tzbmMhPQ-lycEPc1OWHo9MnWyrR9bsQly9bz8DF_WQ/edit?tab=t.cvj0bnjp2og4#heading=h.pimm1a640bup
        self.p.t_between_pulses_mu = self.compute_t_between_pulses_mu(
            t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
            t_raman_pulse=self.p.t_raman_pulse,
            t_img_pulse=self.p.t_img_pulse,
            t_fifo_mu=self.p.t_fifo_mu
        )

        print(f'time between pulses: {self.p.t_between_pulses_mu / 1.e3:1.2f} (us)')
        print(f'calculation slack compensation: {self.p.t_calculation_slack_compensation_mu / 1.e3:1.2f} (us)')

        ### setup data containers

        self.idx = 0
        self.data.omega_raman = self.data.add_data_container(self.p.N_pulses)
        self.data.Omega = self.data.add_data_container(self.p.N_pulses)
        self.data.apd = self.data.add_data_container(self.p.N_pulses)

        self.data.s_z = self.data.add_data_container(self.p.N_pulses)
        self.data.t = self.data.add_data_container(self.p.N_pulses)

        Feedback.__init__(self)
        
        self.zidx = self.p.feedback_resonance_grid_index

        ###

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)
        
        self._phase = 0

        self.finish_prepare()

        self.p.probabilities = np.zeros((*self.xvardims, self.p.N_pulses, self.p.feedback_grid_size))

    @kernel
    def feedback_loop(self, t_start_mu,
                       update_raman_frequency=1,
                       update_rabi_frequency=0,
                       include_photon_noise=1):
        
        self.omega_z_lightshift = 2*np.pi * self.p.frequency_lightshift

        k = 0
        f = self.omega_raman / (2*np.pi)
        omega_prev = 0.

        t_start_mu = t_start_mu & ~7
        t_step = t_start_mu

        at_mu(t_start_mu - (10000 & ~7))

        self.raman.set_frequency_fast(f)
        phase_tracker = 0.

        at_mu(t_start_mu)

        tP = self.p.t_between_pulses_mu
        dt = self.p.delta_t_mu
        tR = self.p.t_raman_set_pretrigger_mu
        
        for i in range(self.p.N_pulses):

            f = self.omega_raman / (2*np.pi)
            self.data.omega_raman.shot_data[i] = self.omega_raman

            at_mu(t_step - self.p.t_raman_set_pretrigger_mu)
            self.raman.set_frequency_fast(f)

            t = (t_step - t_start_mu)*1.e-9
            at_mu(t_step)

            phase_tracker += ((tP - tR + dt) * omega_prev + (tR - dt) * self.omega_raman) * 1.e-9

            self.raman.pulse(self.p.t_raman_pulse)
            k = self.measurement(i)
            omega_prev = self.omega_raman
            self.omega_raman, self.Omega = self.generate_posterior(k, t,
                                                    phase_raman_pulse_start=phase_tracker,
                                                    update_raman_frequency=update_raman_frequency,
                                                    update_rabi_frequency=update_rabi_frequency,
                                                    include_photon_noise=include_photon_noise)

            t_step += self.p.t_between_pulses_mu

            self.data.t.shot_data[i] = t + self.p.t_raman_pulse + self.p.t_img_pulse
            self.data.s_z.shot_data[i] = self.state_z[self.zidx]

    @kernel
    def scan_kernel(self):
        self.core.break_realtime()

        self.integrator.init()

        self.initialize_feedback()
        self.reset_initial_omega_from_params()
        delay(10.e-3)
        
        self.prep_raman(frequency_transition=self.omega_raman/(2*np.pi),
                        phase_mode=0)

        t_pulse_start_mu = now_mu() + 500000

        self.raman.set_up_fast_frequency_update()

        at_mu(t_pulse_start_mu - 20000) # beginning of time
        self.ttl.pd_scope_trig3.pulse(1.e-6)

        self.feedback_loop(t_start_mu=t_pulse_start_mu,
                           update_raman_frequency=self.p.update_raman_frequency_bool,
                           include_photon_noise=self.p.include_photon_noise)

        delay(self.p.t_tweezer_hold)
        self.raman.clean_up_fast_frequency_update()

        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def measurement(self, i):
        T_CONV_MU = 80
        self.integrator.begin_integrate(reset=False)
        self.imaging.pulse(self.p.t_img_pulse)
        self.integrator.stop_and_settle()
        t = now_mu()
        # start the clear after the integrator voltage is already in the sampler
        at_mu(t + T_CONV_MU)
        self.integrator.clear(t=0)
        at_mu(t)
        self.data.apd.shot_data[i] = self.integrator.sample()
        v = self.convert_measurement(self.data.apd.shot_data[i])
        i = i + 1
        return v

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)