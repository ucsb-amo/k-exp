from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras, aprint
from kexp.base import Feedback
from kexp.calibrations.imaging import integrator_calibration
import numpy as np
from numpy import int64

T_CONV_MU = 30


from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams as ExptParamsFeedback
from kexp.experiments.HF_experiments.feedback.data_vault_feedback import DataVault

class FeedbackExpt(Base, Feedback):
    def __init__(self,
                 save_data=True,
                 suppress_live_od=False,
                 save_on_underflow=True):
        self.data = DataVault(self)
        self.p = ExptParamsFeedback()
        Base.__init__(self,
                    setup_camera=False,
                    save_data=save_data,
                    imaging_type=img_types.DISPERSIVE,
                    camera_select=cameras.andor,
                    expt_params=self.p,
                    data_vault=self.data,
                    suppress_live_od=suppress_live_od,
                    save_on_underflow=save_on_underflow)
        
    def finish_prepare(self, shuffle=True):

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

        Feedback.__init__(self)

        self.zidx = self.p.feedback_resonance_grid_index
        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)

        self.p.omega_pulse_list = self.get_new_pulse_list(seed=self.p.pulse_list_seed)

        ### randomized raman pulse-time list
        self._init_t_raman_pulse_rng()
        # Draw once so the list attribute has its compile-time shape/dtype,
        # then rewind the RNG so shot 0 consumes the first batch of the stream.
        self.p.t_raman_pulse_list = self.get_new_t_raman_pulse_list()
        self._t_raman_pulse_rng = np.random.default_rng(self.p.t_raman_pulse_seed_used)


        self.data.feedback_data_containers(self.p)
        # populate first row of probabilities with pre-pulse lists
        self.data.probabilities.shot_data[0, :] = self.P0
        self.data.omega_raman_mesh.shot_data[0, :] = self.omega_guess_list
        
        super().finish_prepare(shuffle=shuffle)

    @kernel
    def scan_kernel(self):

        self.core.wait_until_mu(now_mu())
        self.p.omega_pulse_list = self.get_new_pulse_list(seed=self.p.pulse_list_seed)
        self.p.t_raman_pulse_list = self.get_new_t_raman_pulse_list()
        self.omega_raman = self.p.omega_pulse_list[0]
        # record this shot's drawn pulse times (synced to host at end of shot)
        self.data.t_raman_pulse.put_data_1d(self.p.t_raman_pulse_list)
        self.core.break_realtime()

        self.integrator.init()

        self.initialize_feedback()
        delay(10.e-3)
        
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask, verbose=False)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)
        self.prep_raman(frequency_transition=self.omega_raman/(2*np.pi),
                        phase_mode=0)

        t_pulse_start_mu = now_mu() + 500000

        self.raman.set_up_fast_frequency_update(aggressive_mode=1)

        at_mu(t_pulse_start_mu - 20000) # beginning of time
        self.ttl.pd_scope_trig3.pulse(1.e-6)

        self.feedback_loop(t_start_mu=t_pulse_start_mu,
                           update_raman_frequency=self.p.update_raman_frequency_bool,
                           include_photon_noise=self.p.include_photon_noise)

        delay(self.p.t_tweezer_hold)
        self.raman.clean_up_fast_frequency_update()
        self.ttl.raman_shutter.off()

        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.reset_initial_omega_from_params()
        delay(30.e-3)

    @kernel
    def feedback_loop(self, t_start_mu,
                       update_raman_frequency=0,
                       update_rabi_frequency=0,
                       include_photon_noise=1):
        
        self.omega_z_lightshift = 2 * np.pi * self.p.frequency_lightshift

        k = 0
        f = self.omega_raman / (2*np.pi)

        t_start_mu = t_start_mu & ~7
        t_step = t_start_mu

        at_mu(t_start_mu - (10000 & ~7))

        self.raman.set_frequency_fast(f)
        self.raman.stage_ffua()
        phase_tracker = 0.
        
        dT = self.p.t_between_pulses_mu

        # Fixed turn-on delay between the programmed and ideal pulse times;
        # applied to each drawn pulse time below.
        t_turn_on_delay = self.p.t_raman_pulse - self.p.t_raman_pulse_ideal

        at_mu(t_start_mu)

        for i in range(self.p.N_pulses):

            self.per_feedback_loop_top(idx=i)
            f = self.omega_raman / (2*np.pi)

            # pulse i time (drawn per shot; see get_new_t_raman_pulse_list)
            t_pulse = self.p.t_raman_pulse_list[i]
            self.t_raman_pulse_current = t_pulse
            self.t_raman_pulse_ideal_current = t_pulse - t_turn_on_delay

            # pulse i frequency
            self.data.omega_raman.put_data(self.omega_raman, i)

            at_mu(t_step - self.p.t_raman_set_pretrigger_mu)
            self.raman.set_frequency_fast(f, do_io_update=False)

            t = (t_step - t_start_mu)*1.e-9

            phase_tracker = self.raman.io_update_and_phase_update(t_pulse_mu = t_step,
                                                                t_last_pulse_mu = t_step - dT)

            at_mu(t_step)

            self.raman.pulse(t_pulse)
            k = self.measurement(i)
            self.omega_raman, omega_posterior_mean, self.Omega = self.generate_posterior(k, t,
                                                    phase_raman_pulse_start=phase_tracker,
                                                    update_raman_frequency=update_raman_frequency,
                                                    update_rabi_frequency=update_rabi_frequency,
                                                    include_photon_noise=include_photon_noise)
            if i > (self.p.n_initial_shots_before_remesh-1):
                self.maybe_remesh(self._posterior_std, omega_center=omega_posterior_mean)

            # Gap between the start of pulse i and pulse i+1: budgets pulse i's
            # drawn duration plus imaging, calculation slack, and the next
            # pulse's frequency-set pretrigger, so the period floats with the
            # drawn pulse times. The analysis reconstructs this per step from
            # the saved data.t_raman_pulse (FeedbackReplayCore._compute_dT_rr_mu).
            dT = self.compute_t_between_pulses_mu(
                t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
                t_raman_pulse=t_pulse,
                t_img_pulse=self.p.t_img_pulse,
                t_raman_pretrigger=self.p.t_raman_set_pretrigger_mu,
                t_fifo_mu=self.p.t_fifo_mu
            )

            # time of result of pulse i
            self.data.t.put_data(t + t_pulse + self.p.t_img_pulse, i)
            # result of pulse i
            self.data.s_z.put_data(self.state_z[self.zidx], i)

            t_step += dT

            self.per_feedback_loop_end(idx=i)

        self.per_scan_kernel_end()

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
    def per_scan_kernel_end(self):
        '''runs per scan kernel after everything else'''
        pass
    
    @kernel
    def per_scan_kernel_top(self):
        '''runs per scan kernel before anything else'''
    
    @kernel
    def per_feedback_loop_top(self, idx):
        '''runs per step of the feedback loop before anything else'''
        pass

    @kernel
    def per_feedback_loop_end(self, idx):
        '''runs per step of the feedback loop after everything else'''
        pass

    ### randomized raman pulse-time list

    def _init_t_raman_pulse_rng(self):
        """Create the persistent RNG that draws per-shot raman pulse-time lists.

        p.t_raman_pulse_seed = 0 means unseeded: a fresh seed is drawn from
        entropy. Either way, the seed actually used is recorded in
        p.t_raman_pulse_seed_used (saved with the run params), so the full
        sequence of drawn lists is reproducible for any run.
        """
        seed = int(self.p.t_raman_pulse_seed)
        if seed == 0:
            # keep to 31 bits (and nonzero) so the param stays int32-typed on
            # the kernel -- a fresh uint32 draw above 2**31 would retype the
            # attribute as int64 and fail ARTIQ type unification
            seed = int(np.random.SeedSequence().generate_state(1)[0] >> 1)
            if seed == 0:
                seed = 1
        self.p.t_raman_pulse_seed_used = seed
        self._t_raman_pulse_rng = np.random.default_rng(seed)

    @rpc
    def get_new_t_raman_pulse_list(self) -> TArray(TFloat):
        """Draw the next shot's raman pulse times from the persistent RNG stream.

        Uniform in [t_raman_pulse_min_frac_pi, t_raman_pulse_max_frac_pi] *
        t_raman_pi_pulse, rounded to whole ns so that kernel delays and the mu
        conversion in compute_t_between_pulses_mu agree exactly with the values
        saved to data.t_raman_pulse. Each call consumes the next N_pulses draws
        from the run's seeded stream, so every shot gets a fresh list while the
        whole run remains reproducible from p.t_raman_pulse_seed_used.

        With t_raman_pulse_random_bool = 0, returns a constant list at the
        scalar p.t_raman_pulse (the pre-randomization behavior).
        """
        if not self.p.t_raman_pulse_random_bool:
            self.p.t_raman_pulse_list = np.full(self.p.N_pulses,
                                                self.p.t_raman_pulse)
            return self.p.t_raman_pulse_list
        t_pi = self.p.t_raman_pi_pulse
        t_list = self._t_raman_pulse_rng.uniform(
            self.p.t_raman_pulse_min_frac_pi * t_pi,
            self.p.t_raman_pulse_max_frac_pi * t_pi,
            self.p.N_pulses)
        self.p.t_raman_pulse_list = np.round(t_list * 1.e9) * 1.e-9
        return self.p.t_raman_pulse_list

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