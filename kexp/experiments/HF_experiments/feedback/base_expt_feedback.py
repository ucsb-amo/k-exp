from artiq.experiment import *
from artiq.language import now_mu, delay, TFloat, TArray, at_mu
from kexp import Base, img_types, cameras, aprint
from kexp.base import Feedback, RandomRamanPulseTimes
from kexp.base.feedback import check_feedback_grid_params
import numpy as np

from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams as ExptParamsFeedback
from kexp.experiments.HF_experiments.feedback.data_vault_feedback import DataVault
from kexp.experiments.HF_experiments.feedback.fastest.fastest_loop import FastestLoop, OverlapPosterior

class FeedbackExpt(Base, Feedback, RandomRamanPulseTimes, OverlapPosterior, FastestLoop):
    """Feedback runs. feedback_loop is the fastest loop by default (p.fast_path = 2,
    fastest/fastest_loop.py); self.p.fast_path = 0 in prepare() runs the standard loop
    (feedback_loop_standard). A class that overrides the read or the posterior gets the standard
    loop, with a printed reason; p.fast_path records the loop that ran."""

    def __init__(self,
                 save_data=True,
                 suppress_live_od=False,
                 save_on_underflow=True,
                 warmup_shots=3,
                mot_preload=False):
        
        self.data = DataVault(self)
        self.p = ExptParamsFeedback()
        Base.__init__(self,
                    save_data=save_data,
                    imaging_type=img_types.DISPERSIVE,
                    # acquire with the APD: pickoff stage in, no liveOD frames
                    camera_select=cameras.apd,
                    expt_params=self.p,
                    data_vault=self.data,
                    suppress_live_od=suppress_live_od,
                    save_on_underflow=save_on_underflow,
                    warmup_shots=warmup_shots,
                    mot_preload=mot_preload)
        # the standard loop until finish_prepare chooses (fastest_choose)
        self.fastest_defaults(FeedbackExpt)
        # the params' default slack: a different value at finish_prepare means the experiment set
        # its own, which the fastest loop keeps instead of the measured required slack
        self._slack_default_mu = int(self.p.t_calculation_slack_compensation_mu)

    def finish_prepare(self, shuffle=True):

        # which loop runs (recorded in p.fast_path before the run is registered); the fastest loop
        # also picks its slack here (fastest_pick_slack), so the spacing is computed after it
        self.fastest_choose(FeedbackExpt)

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

        # refuse a bad grid before a run id is used, then derive its Omega-unit values
        check_feedback_grid_params(self.p, self.scan_xvars)
        self.p.compute_feedback_grid()

        Feedback.__init__(self)

        self.zidx = self.p.feedback_resonance_grid_index
        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)

        self.p.omega_pulse_list = self.get_new_pulse_list(seed=self.p.pulse_list_seed)

        # draw once so the list has its compile-time shape
        self.p.t_raman_pulse_list = self.get_new_t_raman_pulse_list(
            seed=self.resolve_t_raman_pulse_seed())

        self.data.feedback_data_containers(self.p)
        # populate first row of probabilities with pre-pulse lists
        self.data.probabilities.shot_data[0, :] = self.P0
        self.data.omega_raman_mesh.shot_data[0, :] = self.omega_guess_list

        super().finish_prepare(shuffle=shuffle)

        self.fastest_finish()

    @kernel
    def scan_kernel(self):

        self.core.wait_until_mu(now_mu())
        self.p.omega_pulse_list = self.get_new_pulse_list(seed=self.p.pulse_list_seed)
        t_raman_pulse_seed = self.resolve_t_raman_pulse_seed()
        self.p.t_raman_pulse_list = self.get_new_t_raman_pulse_list(seed=t_raman_pulse_seed)
        self.data.t_raman_pulse_seed.put_data(float(t_raman_pulse_seed))
        self.data.t_raman_pulse.put_data_1d(self.p.t_raman_pulse_list)
        self.core.break_realtime()

        # fastest loop: its read traces, recorded in the first shot (nothing for the standard loop)
        self._fastest_shot_kernels[0](self)

        self.integrator.init()

        self.initialize_feedback()
        delay(10.e-3)
        
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask, verbose=False)
        # init-only mask: APD contrast fell 32 -> 14 mV in ~2 min; per shot it held ~28 mV (83472/83473)
        if self.p.slm_mask_every_shot:
            self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask, dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        # unsqueezed, as the APD calibrations prepare; squeezed failed the on-resonance sim check (83204)
        # self.prepare_hf_tweezers(squeeze=True)
        self.prepare_hf_tweezers(squeeze=False)
        self.prep_raman(frequency_transition=self.omega_raman/(2*np.pi),
                        phase_mode=0)

        t_pulse_start_mu = now_mu() + 500000

        self.raman.set_up_fast_frequency_update(aggressive_mode=1)

        at_mu(t_pulse_start_mu - 20000) # beginning of time
        self.ttl.pd_scope_trig3.pulse(1.e-6)

        self.feedback_loop(t_start_mu=t_pulse_start_mu,
                           update_raman_frequency=self.p.update_raman_frequency_bool,
                           update_rabi_frequency=0,
                           include_photon_noise=self.p.include_photon_noise)

        delay(self.p.t_tweezer_hold)
        self.raman.clean_up_fast_frequency_update()
        self.ttl.raman_shutter.off()

        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()

        self.core.wait_until_mu(now_mu())
        delay(30.e-3)

    @kernel
    def feedback_loop(self, t_start_mu,
                       update_raman_frequency=0,
                       update_rabi_frequency=0,
                       include_photon_noise=1):
        """The loop finish_prepare chose: feedback_loop_fastest (default) or
        feedback_loop_standard. Only that one is compiled."""
        self._feedback_loop_kernels[0](self, t_start_mu, update_raman_frequency,
                                       update_rabi_frequency, include_photon_noise)

    @kernel
    def cleanup_scan_kernel(self):
        Base.cleanup_scan_kernel(self)
        self._fastest_cleanup_kernels[0](self)

    @kernel
    def cleanup_abort_kernel(self):
        """Base's safe state, then the Raman and imaging RF off: the fastest loop's read trace
        turns the next Raman pulse on, so an exception between the two could leave it on (the
        shutter is closed by Base). Then the ADC back to the 32-bit transfer."""
        Base.cleanup_abort_kernel(self)
        try:
            self.core.break_realtime()
            self.raman.off()
            self.imaging.off()
        except:
            aprint("[feedback] cleanup_abort_kernel: switching the Raman / imaging RF off failed")
        try:
            self._fastest_cleanup_kernels[0](self)
        except:
            aprint("[feedback] cleanup_abort_kernel: restoring the 32-bit ADC transfer failed")

    @kernel
    def feedback_loop_standard(self, t_start_mu,
                       update_raman_frequency=0,
                       update_rabi_frequency=0,
                       include_photon_noise=1):

        self.omega_z_lightshift = 2 * np.pi * self.p.frequency_lightshift

        k = 0
        f = self.omega_raman / (2*np.pi)

        t_start_mu = t_start_mu & ~7
        t_step = t_start_mu

        at_mu((t_start_mu - 10000) & ~7)

        self.raman.set_frequency_fast(f)
        self.raman.stage_ffua()
        phase_tracker = 0.
        
        dT = self.p.t_between_pulses_mu

        # the explicit offset: t_raman_pulse - t_raman_pulse_ideal is wrong when t_raman_pulse is scanned
        t_turn_on_delay = self.p.t_raman_pulse_offset

        at_mu(t_start_mu)

        for i in range(self.p.N_pulses):

            self.per_feedback_loop_top(idx=i)
            f = self.omega_raman / (2*np.pi)

            # pulse i time
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

            # the period floats with the drawn pulse time; replay rebuilds it from data.t_raman_pulse
            dT = self.compute_t_between_pulses_mu(
                t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
                t_raman_pulse=t_pulse,
                t_img_pulse=self.p.t_img_pulse,
                t_raman_pretrigger=self.p.t_raman_set_pretrigger_mu,
                t_fifo_mu=self.p.t_fifo_mu
            )

            # time of result of pulse i
            self.data.t.put_data(t + t_pulse + self.p.t_img_pulse, i)
            # model S_z of grid point zidx: exact resonance only with feedback_grid_shift = 0
            self.data.s_z.put_data(self.state_z[self.zidx], i)

            t_step += dT

            self.per_feedback_loop_end(idx=i)

        self.per_scan_kernel_end()

    # ---- the readout: every read path is built from these two ------------

    @kernel
    def readout_pulse(self):
        """Integrator gate and imaging pulse; leaves the cursor at the sample time."""
        self.integrator.begin_integrate(reset=False)
        self.imaging.pulse(self.p.t_img_pulse)
        self.integrator.stop_and_settle()

    @kernel
    def readout_prepare_sample(self):
        """At the sample time: stage the next fast frequency update and schedule the integrator
        clear; leaves the cursor at the sample time."""
        T_CONV_MU = 80
        t0 = now_mu()
        self.raman.stage_ffua()
        # start the clear after the integrator voltage is already in the sampler
        at_mu(t0 + T_CONV_MU)
        self.integrator.clear(t=0)
        at_mu(t0)

    @kernel
    def readout_events(self):
        self.readout_pulse()
        self.readout_prepare_sample()

    @kernel
    def measurement(self, i):
        self.readout_events()
        self.data.apd.shot_data[i] = self.integrator.sample()
        v = self.convert_measurement(self.data.apd.shot_data[i])
        return v

    @kernel
    def per_scan_kernel_end(self):
        '''runs per scan kernel after everything else'''
        pass
    
    @kernel
    def per_feedback_loop_top(self, idx):
        '''runs per step of the feedback loop before anything else'''
        pass

    @kernel
    def per_feedback_loop_end(self, idx):
        '''runs per step of the feedback loop after everything else'''
        pass

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