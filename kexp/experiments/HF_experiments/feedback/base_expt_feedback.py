from artiq.experiment import *
from artiq.language import now_mu, delay, TFloat, TArray, at_mu
from kexp import Base, img_types, cameras
from kexp.base import Feedback, RandomRamanPulseTimes
from kexp.base.feedback import check_feedback_grid_params
import numpy as np

from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams as ExptParamsFeedback
from kexp.experiments.HF_experiments.feedback.data_vault_feedback import DataVault

class FeedbackExpt(Base, Feedback, RandomRamanPulseTimes):
    def __init__(self,
                 save_data=True,
                 suppress_live_od=False,
                 save_on_underflow=True,
                 recalibrate=True,
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
        self.p.cal_enabled = recalibrate
        
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

        # interleaved readout calibration: raw up/down points between data shots, evaluated on
        # the host. self.cal must exist for the compiler; cal_enabled = 0 turns it off here.
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
                        "fraction_power_raman", "cal_t_raman_to_read", "t_tweezer_hold",
                        "t_between_pulses_mu", "cal_t_between_reads_mu", "cal_n_reads")

    def _declare_readout_calibration(self):
        from kexp.base.readout_calibration import ReadoutCalibrationRecord
        p = self.p
        if int(p.cal_apply) != 0:
            raise NotImplementedError("cal_apply != 0: the in-run apply path is not built "
                                      "(phase 1 records and evaluates only)")
        modes = [float(m) for m in np.atleast_1d(p.cal_readout_modes)]
        if not modes or any(m not in (0., 1.) for m in modes):
            raise ValueError(f"cal_readout_modes must be a list of 0 / 1, got {modes}")
        t_down = float(p.t_raman_pi_pulse + p.t_raman_pulse_offset)
        self.cal = self.add_sub_scan("cal", every_n_shots=int(p.cal_every_n_shots), at_start=True,
                                     alternate=bool(int(p.cal_alternate)),
                                     reads_params=self.CAL_READS_PARAMS,
                                     require_push=True)
        # one event = one pair (up, down); the mode cycles event by event, the pair order every
        # other cycle, so each mode sees both orders
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
        t_raman_pulse_seed = self.resolve_t_raman_pulse_seed()
        self.p.t_raman_pulse_list = self.get_new_t_raman_pulse_list(seed=t_raman_pulse_seed)
        self.data.t_raman_pulse_seed.put_data(float(t_raman_pulse_seed))
        self.data.t_raman_pulse.put_data_1d(self.p.t_raman_pulse_list)
        self.core.break_realtime()

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

    # ---- the interleaved readout calibration (p.cal_enabled) --------------

    @kernel
    def calibration_read(self, i) -> TFloat:
        """measurement() without writing the main scan's apd container. A class with its own read
        path overrides this."""
        self.readout_events()
        return self.integrator.sample()

    @kernel
    def calibration_kernel(self):
        """One sub-scan point: the data shot's preparation, a raman pulse of p.t_raman_pulse (0 = all
        up, pi time = all down), then p.cal_n_reads APD reads: mode 0 calibration_read, mode 1 the
        calibration run's integrated_imaging_pulse at cal_t_between_reads_mu.

        No camera or scope trigger, no write to the main scan's containers: liveOD and the camera
        streams count frames per shot, so one extra trigger shifts every later slot."""
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
        delay(self.p.cal_t_raman_to_read)
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