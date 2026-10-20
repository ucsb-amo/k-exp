from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, TInt32, at_mu, parallel
from kexp import Base, img_types, cameras, aprint
from kexp.base import Feedback, RandomRamanPulseTimes
from kexp.calibrations.imaging import integrator_calibration
import numpy as np
from numpy import int64

from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams as ExptParamsFeedback
from kexp.experiments.HF_experiments.feedback.data_vault_feedback import DataVault

class FeedbackExpt(Base, Feedback, RandomRamanPulseTimes):
    def __init__(self,
                 save_data=True,
                 suppress_live_od=False,
                 save_on_underflow=True):
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

        # the pre-shot (read, resonant pi, read) leaves the spin all down, and the
        # model must start where the atoms are; Feedback.__init__ reads this
        self.p.feedback_initial_sz = -1.0 if self.p.preshot_contrast else 1.0

        Feedback.__init__(self)

        self.zidx = self.p.feedback_resonance_grid_index
        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)

        self.p.omega_pulse_list = self.get_new_pulse_list(seed=self.p.pulse_list_seed)

        ### randomized raman pulse-time list
        # draw once so the list attribute has its compile-time shape/dtype
        self.p.t_raman_pulse_list = self.get_new_t_raman_pulse_list(
            seed=self.resolve_t_raman_pulse_seed())


        self.data.feedback_data_containers(self.p)
        # [APD read of the prepared state (all up), APD read after a resonant pi pulse
        # (all down)] per shot when p.preshot_contrast; stays 0 otherwise
        self.data.preshot_apd = self.data.add_data_container(2)
        # [v_apd_all_up, v_apd_all_down, N_photons_per_shot] the posterior used this
        # shot, and 1/0 = per-shot estimate updated / guarded (p.preshot_endpoint_gain
        # > 0; stays 0 with the gain off); written on pre-shot shots only
        self.data.preshot_endpoints = self.data.add_data_container(4)
        # populate first row of probabilities with pre-pulse lists
        self.data.probabilities.shot_data[0, :] = self.P0
        self.data.omega_raman_mesh.shot_data[0, :] = self.omega_guess_list

        # the interleaved readout calibration (p.cal_enabled): a sub-scan of
        # up / down readout points between the data shots, recorded raw and
        # evaluated on the host (ReadoutCalibrationRecord); phase 1 never
        # changes the kernel's constants
        # The sub-scan object always exists (calibration_kernel names
        # self.cal, and the compiler type-checks it whether or not a point is
        # ever taken); with cal_enabled = 0 it is turned off before the run
        # is prepared: no points, no containers in the file, no record.
        self.readout_cal = None
        self._declare_readout_calibration()
        if not int(self.p.cal_enabled):
            self.cal.disable("cal_enabled = 0", quiet=True)
            self.readout_cal = None

        super().finish_prepare(shuffle=shuffle)

    # the parameters calibration_kernel reads; the sub-scan is refused if the
    # main scan scans one of them (the points would mix settings)
    CAL_READS_PARAMS = ("amp_imaging", "t_img_pulse", "frequency_detuned_hf_midpoint",
                        "phase_slm_mask", "dimension_slm_mask", "slm_mask_every_shot",
                        "t_raman_pi_pulse", "t_raman_pulse_offset", "frequency_raman_transition",
                        "fraction_power_raman", "t_preshot_gap", "t_tweezer_hold",
                        "t_between_pulses_mu", "cal_t_between_reads_mu", "cal_n_reads")

    def _declare_readout_calibration(self):
        from kexp.base.readout_calibration import ReadoutCalibrationRecord
        p = self.p
        if int(p.cal_apply) != 0:
            raise NotImplementedError("cal_apply != 0: the in-run apply path is not built "
                                      "(phase 1 records and evaluates only)")
        # only with the sub-scan on: with cal_enabled = 0 a run that uses the
        # preshot gain or the APD map is prepared exactly as before
        if int(getattr(p, "cal_enabled", 1)):
            if float(np.ravel(p.preshot_endpoint_gain)[0]) > 0.:
                raise ValueError("cal_enabled with preshot_endpoint_gain > 0: the two readout "
                                 "paths are mutually exclusive")
            if bool(p.feedback_apd_map_enabled):
                raise ValueError("cal_enabled with feedback_apd_map_enabled: the calibration "
                                 "reads raw volts, the map would not describe them")
        modes = [float(m) for m in np.atleast_1d(p.cal_readout_modes)]
        if not modes or any(m not in (0., 1.) for m in modes):
            raise ValueError(f"cal_readout_modes must be a list of 0 / 1, got {modes}")
        t_down = float(p.t_raman_pi_pulse + p.t_raman_pulse_offset)
        self.cal = self.add_sub_scan("cal", every_n_shots=int(p.cal_every_n_shots), at_start=True,
                                     alternate=bool(int(p.cal_alternate)),
                                     reads_params=self.CAL_READS_PARAMS,
                                     require_push=bool(getattr(self, "_cal_require_push", True)))
        # one event = one pair (up, down); the readout mode cycles event by
        # event (a 2-D sub-scan xvar), and the pair order reverses every other
        # cycle, so each mode sees both orders
        self.cal.xvar("t_raman_pulse", np.array([0., t_down]))
        self.cal.xvar("cal_readout_mode", np.array([[m, m] for m in modes]))
        self.cal.data.apd = self.cal.add_data_container(int(p.cal_n_reads))
        self.readout_cal = ReadoutCalibrationRecord(self, self.cal)

    def on_sub_scan_point(self, sub, i, ok):
        if self.readout_cal is not None:
            self.readout_cal.on_point(i, ok)

    def on_sub_scan_finish(self, sub):
        if self.readout_cal is not None:
            self.readout_cal.finish_run()

    @kernel
    def scan_kernel(self):

        self.core.wait_until_mu(now_mu())
        self.p.omega_pulse_list = self.get_new_pulse_list(seed=self.p.pulse_list_seed)
        # pulse-time list is a function of the seed (p.t_raman_pulse_seed, or a
        # fresh per-shot draw when that is 0); record both for this shot
        t_raman_pulse_seed = self.resolve_t_raman_pulse_seed()
        self.p.t_raman_pulse_list = self.get_new_t_raman_pulse_list(seed=t_raman_pulse_seed)
        self.data.t_raman_pulse_seed.put_data(float(t_raman_pulse_seed))
        self.data.t_raman_pulse.put_data_1d(self.p.t_raman_pulse_list)
        self.omega_raman = self.p.omega_pulse_list[0]
        self.core.break_realtime()

        self.integrator.init()

        self.initialize_feedback()
        delay(10.e-3)
        
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask, verbose=False)
        # p.slm_mask_every_shot = 1: rewrite the phase-dot mask every shot, as the
        # phase_spot scans do. 2026-09-28 (runs 83472 / 83473): with the mask
        # written only at init_kernel the APD up-down contrast fell from ~32 to
        # ~14 mV within ~2 min of a run; rewritten every shot it held ~28 mV.
        if self.p.slm_mask_every_shot:
            self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask, dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        # squeeze=False (user, 2026-09-27): the APD-state and joint calibrations
        # (apd_voltage_vs_state_2, apd_joint_calibration) prepare unsqueezed
        # tweezers, and with squeeze=True the on-resonance simulation check
        # (83204) did not match the calibrated readout.
        # self.prepare_hf_tweezers(squeeze=True)
        self.prepare_hf_tweezers(squeeze=False)
        if self.p.preshot_contrast:
            # pre-shot contrast (user, 2026-09-28): read the prepared state (all up),
            # resonant pi pulse (commanded length = rate pi time + turn-on offset),
            # read again (all down). measure_integrated_v re-arms t_apd_slack after
            # each blocking read. Then the drive moves to the initial feedback
            # frequency; the model starts all down (p.feedback_initial_sz = -1).
            self.prep_raman(frequency_transition=self.p.frequency_raman_transition,
                            phase_mode=0)
            v_preshot_up = self.imaging.measure_integrated_v(self.p.t_img_pulse)
            self.data.preshot_apd.put_data(v_preshot_up, 0)
            delay(self.p.t_preshot_gap)
            self.raman.pulse(self.p.t_raman_pi_pulse + self.p.t_raman_pulse_offset)
            delay(self.p.t_preshot_gap)
            v_preshot_down = self.imaging.measure_integrated_v(self.p.t_img_pulse)
            self.data.preshot_apd.put_data(v_preshot_down, 1)
            # p.preshot_endpoint_gain > 0: this shot's endpoints from the pre-shot
            # reads, smoothed over shots (Feedback.update_shot_endpoints); the
            # endpoints the posterior uses are recorded every pre-shot shot
            if self.preshot_endpoint_gain > 0.:
                self.data.preshot_endpoints.put_data(
                    float(self.update_shot_endpoints(v_preshot_up, v_preshot_down)), 3)
            self.data.preshot_endpoints.put_data(self.v_apd_all_up, 0)
            self.data.preshot_endpoints.put_data(self.v_apd_all_down, 1)
            self.data.preshot_endpoints.put_data(self.N_photons_per_shot, 2)
            # the blocking reads leave ~t_apd_slack of slack: re-arm before the DDS
            # retune (83515 underflowed here without it); the spin sits at the pole
            self.core.break_realtime()
            self.raman.set(frequency_transition=self.omega_raman/(2*np.pi))
            delay(self.p.t_preshot_gap)
        else:
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

        # mask the difference, not the constant, so the timestamp stays 8-aligned
        # even if the 10000 is later changed to a non-multiple of 8
        at_mu((t_start_mu - 10000) & ~7)

        self.raman.set_frequency_fast(f)
        self.raman.stage_ffua()
        phase_tracker = 0.
        
        dT = self.p.t_between_pulses_mu

        # Fixed turn-on delay between the programmed and ideal pulse times;
        # applied to each drawn pulse time below.
        # Use the explicit turn-on latency: the derived difference
        # (t_raman_pulse - t_raman_pulse_ideal) is only correct while both times
        # are scalars, and this experiment may scan t_raman_pulse.
        # ExptParamsFeedback always defines t_raman_pulse_offset, so no fallback
        # is needed here -- and none is possible: getattr() and truthiness casts
        # on floats are outside the compiled kernel subset.
        t_turn_on_delay = self.p.t_raman_pulse_offset

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
        return v

    # ---- the interleaved readout calibration (p.cal_enabled) --------------

    @kernel
    def calibration_read(self, i) -> TFloat:
        """One readout pulse the way this class's data shots read it:
        measurement()'s integrator timeline, in fast-frequency-update mode,
        without writing the main scan's apd container. A class with its own
        read path (the fast-path session copies) overrides this."""
        T_CONV_MU = 80
        self.integrator.begin_integrate(reset=False)
        self.imaging.pulse(self.p.t_img_pulse)
        self.integrator.stop_and_settle()
        t0 = now_mu()
        self.raman.stage_ffua()
        at_mu(t0 + T_CONV_MU)
        self.integrator.clear(t=0)
        at_mu(t0)
        return self.integrator.sample()

    @kernel
    def calibration_kernel(self):
        """One point of the readout sub-scan: the data shot's preparation,
        then a raman pulse of p.t_raman_pulse (0 for the prepared state, the
        pi time for all down) and p.cal_n_reads APD reads -- the data shot's
        readout (calibration_read, p.cal_readout_mode 0) or the calibration
        run's (warmup_imaging + integrated_imaging_pulse at
        cal_t_between_reads_mu, mode 1). Ends with the sub-scan's data sync.

        Triggers no camera and no scope: liveOD and the camera streams count
        frames per shot, so one extra trigger would shift every later slot
        (no abs_image, no diag frames -- Base.init_calibration_kernel turned
        them off -- no pd_scope_trig3). The main scan's containers are never
        written here."""
        self.integrator.init()
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        if self.p.slm_mask_every_shot:
            self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask, dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)
        self.prepare_hf_tweezers(squeeze=False)
        cal_style = self.p.cal_readout_mode > 0.5
        if cal_style:
            self.warmup_imaging()
        self.prep_raman(frequency_transition=self.p.frequency_raman_transition, phase_mode=0)
        # the data shot's pulse 0 starts 500 us after prep_raman (scan_kernel)
        t_start_mu = now_mu() + 500000
        at_mu(t_start_mu)
        self.raman.pulse(self.p.t_raman_pulse)
        delay(self.p.t_preshot_gap)
        if cal_style:
            t = now_mu()
            for i in range(self.p.cal_n_reads):
                at_mu(t)
                self.imaging.integrated_imaging_pulse(self.cal.data.apd, self.p.t_img_pulse, i)
                t = t + self.p.cal_t_between_reads_mu
        else:
            self.raman.set_up_fast_frequency_update(aggressive_mode=1)
            t = now_mu() + 20000
            for i in range(self.p.cal_n_reads):
                at_mu(t)
                self.cal.data.apd.put_data(self.calibration_read(i), i)
                t = t + self.p.t_between_pulses_mu
            self.core.break_realtime()
            self.raman.clean_up_fast_frequency_update()
        self.core.break_realtime()
        self.ttl.raman_shutter.off()
        delay(self.p.t_tweezer_hold)
        self.tweezer.off()
        self.core.wait_until_mu(now_mu())
        self.cal.put_shot_data()

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