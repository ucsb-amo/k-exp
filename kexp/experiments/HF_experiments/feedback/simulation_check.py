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
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE,
                      expt_params=self.p)
        
        self.p.update_raman_frequency_bool = 0
        self.p.include_photon_noise = 1

        self.p.N_repeats = 11
        self.p.N_pulses = 12 # number of steps of evolution
        
        ### parameters

        # self.xvar('pulse_list_span_Omega', np.linspace(0, 3, 3))
        self.p.pulse_list_span_Omega = 4.
        self.xvar('pulse_list_seed', np.linspace(1056, 15432, 5, dtype=np.int32))
        self.p.pulse_list_seed = 1056

        self.get_new_pulse_list()
        
        ###

        # self.p.t_calculation_slack_compensation_mu += 5000
        # timing docs: https://docs.google.com/document/d/11tzbmMhPQ-lycEPc1OWHo9MnWyrR9bsQly9bz8DF_WQ/edit?tab=t.cvj0bnjp2og4#heading=h.pimm1a640bup
        self.p.t_between_pulses_mu = self.compute_t_between_pulses_mu(
            t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
            t_raman_pulse=self.p.t_raman_pulse,
            t_img_pulse=self.p.t_img_pulse,
            t_raman_pretrigger=self.p.t_raman_set_pretrigger_mu,
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
        # self.zidx = self.p.feedback_grid_size//2

        ###

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)
        
        self._phase = 0

        self.data.phi = self.data.add_data_container(self.p.N_pulses)
        self.data.ts = self.data.add_data_container(self.p.N_pulses)

        self.finish_prepare()

        self.p.probabilities = np.zeros((*self.xvardims, self.p.N_pulses, self.p.feedback_grid_size))

    @rpc
    def get_new_pulse_list(self, seed=0) -> TArray(TFloat):
        Omega = np.pi / self.p.t_raman_pi_pulse
        if seed != 0:
            np.random.seed(seed)
        else:
            np.random.seed()
        detuning_list = ((np.random.rand(self.p.N_pulses) - 0.5) * 2) # from -1 to 1
        detuning_list = detuning_list * Omega * self.p.pulse_list_span_Omega
        detuning_list[0] = 0.
        self.p.omega_pulse_list = 2*np.pi*self.p.frequency_raman_transition + detuning_list
        return self.p.omega_pulse_list

    @kernel
    def feedback_loop(self, t_start_mu,
                       update_raman_frequency=0,
                       update_rabi_frequency=0,
                       include_photon_noise=1):

        self.omega_z_lightshift = 2*np.pi * self.p.frequency_lightshift

        k = 0
        f = self.omega_raman / (2*np.pi)
        omega_prev = 0.

        t_start_mu = t_start_mu & ~7
        t_step = t_start_mu

        at_mu(t_start_mu - (10000 & ~7))

        self.raman.set_frequency_fast(self.p.omega_pulse_list[0] / (2*np.pi))
        self.raman.stage_ffua()
        # aprint(self.raman.get_phase())
        # self._phase = 0
        phase_tracker = 0.

        dT = self.p.t_between_pulses_mu

        at_mu(t_start_mu)
        
        for i in range(self.p.N_pulses):
            # self.omega_raman = self.p.intermediate_detuning

            self.omega_raman = self.p.omega_pulse_list[i] 
            
            f = self.omega_raman / (2*np.pi)
            self.data.omega_raman.shot_data[i] = self.omega_raman
            # self.data.Omega.shot_data[i+1] = var

            at_mu(t_step - self.p.t_raman_set_pretrigger_mu)
            self.raman.set_frequency_fast(f, do_io_update=False)

            t = (t_step - t_start_mu)*1.e-9

            phase_tracker = self.raman.io_update_and_phase_update(t_pulse_mu = t_step,
                                                                t_last_update_mu = t_step - dT,
                                                                t_io_update_delay_mu=self.p.delta_t_mu)

            # phase_tracker += ((tP - tR + dt) * omega_prev + (tR - dt) * self.omega_raman) * 1.e-9
            # phi = phase_tracker

            self.raman.pulse(self.p.t_raman_pulse)

            k = self.measurement(i)
            omega_prev = self.omega_raman
            self.omega_raman, self.Omega = self.generate_posterior(k, t,
                                                    phase_raman_pulse_start=phase_tracker,
                                                    update_raman_frequency=update_raman_frequency,
                                                    update_rabi_frequency=update_rabi_frequency,
                                                    include_photon_noise=include_photon_noise)

            t_step += dT

            self.data.t.shot_data[i] = t + self.p.t_raman_pulse + self.p.t_img_pulse
            self.data.s_z.shot_data[i] = self.state_z[self.zidx]
            # self.data.phi.put_data(phase_tracker, i)
            # self.store_probabilities_to_host(self.P0, self.scan_xvars[0].counter, i)
        
    @rpc(flags={"async"})
    def store_probabilities_to_host(self, pulse_probabilities, shot_idx, pulse_idx):
        self.p.probabilities[shot_idx, pulse_idx] = pulse_probabilities

    @kernel
    def scan_kernel(self):

        self.core.wait_until_mu(now_mu())

        self.p.omega_pulse_list = self.get_new_pulse_list(seed=self.p.pulse_list_seed)

        self.core.break_realtime()

        self.integrator.init()

        self.initialize_feedback()
        self.reset_initial_omega_from_params()
        delay(10.e-3)
        
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask, verbose=False)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)
        self.prep_raman(frequency_transition=self.omega_raman/(2*np.pi),
                        phase_mode=0)

        t_pulse_start_mu = now_mu() + 5000000

        self.raman.set_up_fast_frequency_update(aggressive_mode=1)

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

        self.core.wait_until_mu(now_mu())
        self.reset_initial_omega_from_params()
        # print((self.data.omega_raman.shot_data/(2*np.pi) - self.p.frequency_raman_transition)/1.e3)
        # self.scope.read_sweep(0)
        # self.core.break_realtime()
        delay(30.e-3)

    @kernel
    def measurement(self, i):
        T_CONV_MU = 80
        self.integrator.begin_integrate(reset=False)
        self.imaging.pulse(self.p.t_img_pulse)
        self.integrator.stop_and_settle()

        t0 = now_mu()
        self.raman.stage_ffua()

        # start the clear after the integrator voltage is already in the sampler
        at_mu(t0 + T_CONV_MU)
        self.integrator.clear(t=0)
        at_mu(t0)
        self.data.apd.shot_data[i] = self.integrator.sample()
        v = self.convert_measurement(self.data.apd.shot_data[i])
        i = i + 1
        return v

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)