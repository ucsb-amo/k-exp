"""Integrator timing check (no atoms, imaging light onto the APD).

Plan "Tier B" (2026-09-29). One file, four tests; pick one per run with the
environment variable INTEGRATOR_TEST_MODE (recorded as p.test_mode):

  1  settle      scan t_int_settle: gate close -> Sampler CNV
  2  clear       scan t_int_clear_offset: CNV -> integrator clear starts
  3  memory      scan t_int_clear_gap: clear held for this long after a charge
                 read A (pulse length from p.t_int_a_pulse_list, per read)
                 before a dark read B
  4  aperture    scan t_int_pulse_start: a short pulse slid across the gate
  5  settle_fine scan t_int_settle finely; every iteration also reads bright
                 and dark at the fixed reference settle t_int_settle_ref
                 (v_plat / v_plat_dark), so each point is compared with
                 reads interleaved in the same shot (drift cancels)

INTEGRATOR_AMP overrides amp_imaging (default 0.5).

Each read reproduces BeatLockImagingPID._integrated_pulse_v with every offset
exposed (reset release gate-600 mu and gate-open command gate-300 mu come from
Integrator.begin_integrate unchanged). Every read is paired with a dark read of
identical timing, and each shot also takes N_ref reads through the production
imaging.measure_integrated_v (bright and dark) as a drift reference.

Reset polarity used here is the one the production code uses: ttl_reset.off()
starts the clear, begin_integrate's ttl_reset.on() releases it.
"""
import os

from artiq.experiment import *
from artiq.language import now_mu, at_mu, delay, TFloat
from kexp import Base, img_types, cameras
import numpy as np

MODES = {1: 'settle', 2: 'clear', 3: 'memory', 4: 'aperture', 5: 'settle_fine',
         6: 'aperture_prod'}

class integrator_timing_check(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=True,
                      camera_select=cameras.apd,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE,
                      # 83670/83671: an underflow made liveOD delete the partial
                      # run; keep the shots taken instead (user, 2026-09-29)
                      save_on_underflow=True)

        self.p.test_mode = np.int32(int(os.environ.get('INTEGRATOR_TEST_MODE', '1')))
        if self.p.test_mode not in MODES:
            raise ValueError(f'INTEGRATOR_TEST_MODE must be one of {list(MODES)}')
        print(f'integrator_timing_check: mode {self.p.test_mode} ({MODES[self.p.test_mode]})')

        # feedback reads at amp_imaging 0.2 (expt_params_feedback); 0.5 here for
        # ~3x the signal (0.2 gives only ~80 mV per 5 us read, 2026-09-29). The
        # timing under test does not depend on the power.
        self.p.amp_imaging = float(os.environ.get('INTEGRATOR_AMP', '0.5'))  # imaging PID v_pd setpoint
        self.p.t_img_pulse = 5.e-6
        # slack re-armed after each blocking sampler read; production 12 us.
        # 83670 (mode 5) underflowed at a CNV with 12 us (user: add slack, 2026-09-29);
        # 83671/83672 still did at 25 us although every read started with >= 23 us
        # of slack (83672 slack_mu): a rare ~40 us stall, likely a DRTIO satellite
        # write (imaging sw, integrator TTLs 36/38 are on satellite 1)
        # self.p.t_apd_slack = 25.e-6
        self.p.t_apd_slack = 60.e-6

        # defaults = production timing (integrator.py / beat_lock.py)
        self.p.t_int_gate = 5.e-6             # gate open -> gate close command
        self.p.t_int_pulse_start = 0.         # light on, relative to gate open
        self.p.t_int_pulse = 5.e-6            # light pulse length
        self.p.t_int_settle = 1.e-6           # T_SETTLE_MU
        self.p.t_int_clear_offset = 80.e-9    # T_APD_SAMPLER_CONV_MU
        self.p.t_int_clear_gap = 20.e-6       # mode 3 only
        self.p.t_int_a_gate = 10.e-6          # mode 3 charge read A window
        self.p.t_int_settle_ref = 5.e-6       # mode 5 interleaved reference settle

        self.p.N_reads = np.int32(800 if int(self.p.test_mode) == 5 else 400)
        self.p.N_ref = np.int32(20)

        # mode 3: per-read charge pulse length for read A, 0 / 5 / 10 us,
        # fixed pseudo-random pattern (seeded, saved in params)
        rng = np.random.default_rng(20260929)
        self.p.t_int_a_pulse_list = rng.choice([0., 5.e-6, 10.e-6], size=int(self.p.N_reads))

        m = self.p.test_mode
        if m != 6:
            # modes 1-5 were measured with the original window (83665-83674);
            # kexp expt_params now sets the new one, so pin the old values here
            self.p.t_integrator_gate_delay = 0.
            self.p.t_integrator_gate_extra = 0.
            self.p.t_integrator_settle = 1.e-6
        if m == 1:
            self.xvar('t_int_settle', np.array([0., 25., 50., 100., 150., 200., 300., 400.,
                                                500., 750., 1000., 1500., 2000., 3000., 5000.]) * 1.e-9)
        elif m == 2:
            self.xvar('t_int_clear_offset', np.arange(-800., 401., 50.) * 1.e-9)
        elif m == 3:
            self.xvar('t_int_clear_gap', np.array([0.1, 0.2, 0.3, 0.5, 0.75, 1., 1.5, 2., 3.,
                                                   5., 10., 20., 50.]) * 1.e-6)
        elif m == 4:
            self.p.t_int_pulse = 500.e-9
            self.xvar('t_int_pulse_start', np.arange(-1500., 6001., 100.) * 1.e-9)
        elif m == 6:
            # the production Integrator path with the proposed window: gate
            # opens 0.7 us after the light command, closes 1.7 us after the
            # nominal 5 us pulse end, sample 4 us later (83668, 83674)
            self.p.t_integrator_gate_delay = 0.7e-6
            self.p.t_integrator_gate_extra = 1.0e-6
            self.p.t_integrator_settle = 4.0e-6
            self.p.t_int_pulse = 500.e-9
            self.xvar('t_int_pulse_start', np.arange(-2000., 7001., 100.) * 1.e-9)
        elif m == 5:
            self.xvar('t_int_settle', np.concatenate([np.arange(800., 3001., 50.),
                                                      [3250., 3500., 4000., 5000., 6000., 8000., 10000.]]) * 1.e-9)

        self.p.N_repeats = 1

        self.data.v_test = self.data.add_data_container(int(self.p.N_reads))
        self.data.v_dark = self.data.add_data_container(int(self.p.N_reads))
        self.data.v_ref = self.data.add_data_container(int(self.p.N_ref))
        self.data.v_ref_dark = self.data.add_data_container(int(self.p.N_ref))
        # mode 5 only (zeros otherwise)
        self.data.v_plat = self.data.add_data_container(int(self.p.N_reads))
        self.data.v_plat_dark = self.data.add_data_container(int(self.p.N_reads))
        # mode 5: slack (mu) at the start of every read, in read order
        # (4 per iteration: test, test dark, ref, ref dark)
        self.data.slack_mu = self.data.add_data_container(4 * int(self.p.N_reads))

        self.finish_prepare(shuffle=True)

    @kernel
    def read(self, t_gate_mu, t_pulse_start_mu, t_pulse_mu,
             t_settle_mu, t_clear_offset_mu) -> TFloat:
        """One integrated read, gate opening at the current cursor.
        Precondition: integrator held in clear, >= 2 us of slack.
        Leaves the integrator held in clear; slack ~0 on return."""
        t_open = now_mu()
        self.integrator.begin_integrate(reset=False)
        if t_pulse_mu > 0:
            at_mu(t_open + t_pulse_start_mu)
            self.imaging.on()
            at_mu(t_open + t_pulse_start_mu + t_pulse_mu)
            self.imaging.off()
        at_mu(t_open + t_gate_mu)
        self.integrator.ttl_integrate.on()
        t0 = t_open + t_gate_mu + t_settle_mu
        at_mu(t0 + t_clear_offset_mu)
        self.integrator.ttl_reset.off()
        at_mu(t0)
        return self.integrator.sample()

    @kernel
    def read_prod(self, t_pulse_start_mu, t_pulse_mu, t_nominal_mu) -> TFloat:
        """Mode 6: one read through Integrator.begin_integrate / stop_and_settle
        (window from p.t_integrator_*), light command at the cursor + start,
        stop_and_settle called at the nominal pulse end."""
        t = now_mu()
        self.integrator.begin_integrate(reset=False)
        if t_pulse_mu > 0:
            at_mu(t + t_pulse_start_mu)
            self.imaging.on()
            at_mu(t + t_pulse_start_mu + t_pulse_mu)
            self.imaging.off()
        at_mu(t + t_nominal_mu)
        self.integrator.stop_and_settle()
        t0 = now_mu()
        at_mu(t0 + 80)
        self.integrator.ttl_reset.off()
        at_mu(t0)
        return self.integrator.sample()

    @kernel
    def charge_then_clear(self, t_a_pulse_mu, t_a_gate_mu, t_settle_mu,
                          t_clear_offset_mu) -> TInt64:
        """Mode 3 read A: integrate (light for t_a_pulse_mu), hold, start the
        clear as production does, but never sample. Returns the clear start."""
        t_open = now_mu()
        self.integrator.begin_integrate(reset=False)
        if t_a_pulse_mu > 0:
            self.imaging.on()
            at_mu(t_open + t_a_pulse_mu)
            self.imaging.off()
        at_mu(t_open + t_a_gate_mu)
        self.integrator.ttl_integrate.on()
        t_clear = t_open + t_a_gate_mu + t_settle_mu + t_clear_offset_mu
        at_mu(t_clear)
        self.integrator.ttl_reset.off()
        return t_clear

    @kernel
    def scan_kernel(self):
        # init_scan_kernel's reset_devices turns the 2D MOT + push back on;
        # keep that light off the APD
        self.power_down_cooling()
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)
        self.integrator.init()
        delay(20.e-3)

        t_gate_mu = self.core.seconds_to_mu(self.p.t_int_gate)
        t_pulse_start_mu = self.core.seconds_to_mu(self.p.t_int_pulse_start)
        t_pulse_mu = self.core.seconds_to_mu(self.p.t_int_pulse)
        t_settle_mu = self.core.seconds_to_mu(self.p.t_int_settle)
        t_clear_offset_mu = self.core.seconds_to_mu(self.p.t_int_clear_offset)
        t_clear_gap_mu = self.core.seconds_to_mu(self.p.t_int_clear_gap)
        t_a_gate_mu = self.core.seconds_to_mu(self.p.t_int_a_gate)
        t_settle_ref_mu = self.core.seconds_to_mu(self.p.t_int_settle_ref)
        t_slack = self.p.t_apd_slack

        # production reference reads
        for j in range(self.p.N_ref):
            self.data.v_ref.shot_data[j] = self.imaging.measure_integrated_v(self.p.t_img_pulse)
            self.data.v_ref_dark.shot_data[j] = self.imaging.measure_integrated_v(self.p.t_img_pulse, dark=True)

        if self.p.test_mode == 5:
            # one read per iteration (83670/83671 underflowed with all four
            # unrolled in one body); k = i % 4 picks the read type
            for i in range(4 * self.p.N_reads):
                k = i % 4
                j = i // 4
                t_s = t_settle_mu if k < 2 else t_settle_ref_mu
                t_p = t_pulse_mu if k % 2 == 0 else np.int64(0)
                self.data.slack_mu.shot_data[i] = float(now_mu() - self.core.get_rtio_counter_mu())
                v = self.read(t_gate_mu, t_pulse_start_mu, t_p, t_s, t_clear_offset_mu)
                if k == 0:
                    self.data.v_test.shot_data[j] = v
                elif k == 1:
                    self.data.v_dark.shot_data[j] = v
                elif k == 2:
                    self.data.v_plat.shot_data[j] = v
                else:
                    self.data.v_plat_dark.shot_data[j] = v
                delay(t_slack)

        for i in range(self.p.N_reads if self.p.test_mode != 5 else 0):
            if self.p.test_mode == 3:
                t_a_pulse_mu = self.core.seconds_to_mu(self.p.t_int_a_pulse_list[i])
                t_clear = self.charge_then_clear(t_a_pulse_mu, t_a_gate_mu,
                                                 t_settle_mu, t_clear_offset_mu)
                # begin_integrate releases the clear 600 mu before the gate opens
                at_mu(t_clear + t_clear_gap_mu + 600)
                self.data.v_test.shot_data[i] = self.read(t_gate_mu, 0, 0,
                                                          t_settle_mu, t_clear_offset_mu)
                delay(t_slack)
                self.data.v_dark.shot_data[i] = self.read(t_gate_mu, 0, 0,
                                                          t_settle_mu, t_clear_offset_mu)
                delay(t_slack)
            elif self.p.test_mode == 6:
                t_nominal_mu = self.core.seconds_to_mu(self.p.t_img_pulse)
                self.data.v_test.shot_data[i] = self.read_prod(t_pulse_start_mu, t_pulse_mu, t_nominal_mu)
                delay(t_slack)
                self.data.v_dark.shot_data[i] = self.read_prod(t_pulse_start_mu, np.int64(0), t_nominal_mu)
                delay(t_slack)
            else:
                self.data.v_test.shot_data[i] = self.read(t_gate_mu, t_pulse_start_mu, t_pulse_mu,
                                                          t_settle_mu, t_clear_offset_mu)
                delay(t_slack)
                self.data.v_dark.shot_data[i] = self.read(t_gate_mu, t_pulse_start_mu, 0,
                                                          t_settle_mu, t_clear_offset_mu)
                delay(t_slack)

        self.imaging.off()
        self.integrator.init()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        # chained runs: INTEGRATOR_RESTART_MONITOR=0 on all but the last
        restart = os.environ.get('INTEGRATOR_RESTART_MONITOR', '1') == '1'
        self.end(os.path.abspath(__file__), restart_monitor=restart)
