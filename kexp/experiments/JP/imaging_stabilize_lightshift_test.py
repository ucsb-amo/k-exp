from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np

class imaging_stabilize_lightshift_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=False,
                      imaging_type=img_types.ABSORPTION,
                      suppress_live_od=True)

        # exercises BeatLockImagingPID.stabilize_lightshift, the light-shift
        # wrapper over stabilize_power. Where imaging_stabilize_power_test asks
        # "does the servo hit a commanded VOLTAGE", this asks the question that
        # actually matters: "does it hit a commanded light shift in Hz, across
        # the range of shifts you would command", by converting the converged
        # voltage back to Hz and comparing.

        # Range of commanded shifts. The interesting failures are at the ends:
        # too low and the servo is fighting the dark-subtraction noise floor,
        # too high and v_target is simply unreachable before the DAC rails.
        self.xvar('frequency_lightshift_target', np.linspace(15.e3, 120.e3, 7))
        # self.p.frequency_lightshift_target = 15.e3

        # these live in waxx ExptParams -- override here to test other settings.
        # t_apd_imaging_check is deliberately NOT set: stabilize_lightshift sizes
        # its own window per target, so that param only affects a bare
        # stabilize_power call.
        self.p.v_target_imaging_lightshift = 1.
        self.p.t_apd_imaging_check_max = 150.e-6
        self.p.t_apd_imaging_check_min = 10.e-6
        self.p.frac_err_threshold_imaging_pid = 0.005

        # fit-based path: probe the setpoint -> power map once, invert it, land
        # in one jump, accept on an average. Set False to compare against the
        # old P/I servo, whose gains below are then what matters.
        self.p.imaging_power_use_fit = True
        self.p.N_points_imaging_power_map = np.int32(9)
        # probe band, as a fraction of the setpoint the map is centered on. Widen
        # this if n_iter is routinely nonzero at the ends of the scan: it means
        # the targets sit outside the probed band and the jump is extrapolating.
        self.p.frac_span_imaging_power_map = 0.6
        self.p.imaging_power_map_quadratic = True
        self.p.N_max_correction_imaging_power = np.int32(4)
        self.p.N_shots_per_imaging_power_map_refit = np.int32(0)
        self.p.frac_secant_slope_max = 4.

        # averaging, split by purpose: the dark is subtracted from everything so
        # it is averaged hardest, the probe points lean on the fit instead, and
        # the verification averages adaptively until its accept/reject call is
        # unambiguous. Raise N_avg_imaging_verify_max if the run reports a noise
        # floor above frac_err_threshold_imaging_pid.
        self.p.N_avg_imaging_dark = np.int32(8)
        self.p.N_avg_imaging_power_check = np.int32(2)
        self.p.N_avg_imaging_verify_min = np.int32(3)
        self.p.N_avg_imaging_verify_max = np.int32(32)
        self.p.k_sigma_imaging_verify = 2.5

        # servo path only
        self.p.N_max_iter_imaging_pid = np.int32(100)
        self.p.gain_p_imaging_pid = -0.019
        self.p.gain_i_imaging_pid = -0.0175

        self.p.N_repeats = 15

        self.data.n_iter = self.data.add_data_container(1, np.int32)
        self.data.frac_err_converged = self.data.add_data_container(1)
        self.data.v_signal_achieved = self.data.add_data_container(1)
        self.data.f_lightshift_achieved = self.data.add_data_container(1)
        # what was COMMANDED, recorded per shot rather than read back out of
        # scan_xvars in analyze(). With the xvar line commented out and only the
        # scalar set, xvarnames is empty and init_xvars silently inserts its own
        # placeholder xvar("dummy",[0]) -- so scan_xvars[0].values is then a
        # column of zeros, which is where the divide-by-zero came from. Logging
        # the target alongside the result works either way.
        self.data.f_lightshift_target = self.data.add_data_container(1)
        self.data.v_target = self.data.add_data_container(1)
        # the window stabilize_lightshift chose for this target
        self.data.t_integration = self.data.add_data_container(1)

        # shuffle matters MORE here than in the power test. On the servo path
        # each shot inherits the previous shot's converged PID setpoint, so an
        # ordered ramp would let it warm-start from a nearly-correct power and
        # report an n_iter that says nothing about acquiring a target cold. On
        # the fit path the jump is open-loop and does not warm-start, but the
        # probe band is centered on wherever the setpoint happens to be, so
        # ordering still leaks in through a re-probe.
        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.imaging.set_power(0.5)
        delay(5.e-3)

        # reset_devices (via init_scan_kernel) restores the camera_params
        # detuning every shot, so it has to be set here -- and it must be the
        # detuning the calibration was taken at, since the amp -> power map
        # depends on AOM drive frequency and the light shift itself goes as
        # I/delta. check_lightshift produces its shift at the midpoint.
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)

        # the same conversions stabilize_lightshift does internally: the window
        # is chosen from the target shift so the measurement lands near
        # p.v_target_imaging_lightshift, and the target voltage follows from
        # that window. Recomputing them here rather than only reading back the
        # returned window keeps this a check on the conversion, not a
        # restatement of it.
        f_target = self.p.frequency_lightshift_target
        t_predicted = self.imaging.lightshift_to_t_integration(f_target)
        v_target = self.imaging.lightshift_to_v_target(f_target, t_predicted)

        self.data.f_lightshift_target.put_data(f_target)
        self.data.v_target.put_data(v_target)

        n_iter, frac_err, t_check = self.imaging.stabilize_lightshift(f_target)

        self.data.n_iter.put_data(n_iter)
        self.data.frac_err_converged.put_data(frac_err)
        self.data.t_integration.put_data(t_check)

        ### read back what the servo actually landed on
        # stabilize_power returns with ~zero slack (its last act is a blocking
        # sampler read or a settle delay), and begin_integrate pretriggers 2100
        # mu into the past on a reset=True call, so the timeline needs room
        # before measuring again.
        self.core.break_realtime()

        # same dark-then-light order stabilize_power uses internally, and the
        # SAME window it returned -- v_signal scales with the integration time,
        # so reading back with any other window would misreport the shift.
        v_dark = self.imaging.measure_integrated_v(t_check, True)
        v_signal = self.imaging.measure_integrated_v(t_check, False) - v_dark

        self.data.v_signal_achieved.put_data(v_signal)
        self.data.f_lightshift_achieved.put_data(
            self.imaging.v_to_lightshift(v_signal, t_check))

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False, setup_slm=False)
        self.scan()

    def analyze(self):
        import os
        import matplotlib.pyplot as plt

        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

        # suppress_live_od=True means nothing is saved to disk, so pull the
        # stats straight from the in-memory run data instead of via atomdata.
        # Target and result are both logged per shot, so they are aligned by
        # construction -- no un-shuffling, and no dependence on whether the
        # target is being scanned or held at a scalar.
        f_target = np.asarray(self.data.f_lightshift_target._run_data, dtype=float)
        v_target = np.asarray(self.data.v_target._run_data, dtype=float)
        n_iter = np.asarray(self.data.n_iter._run_data, dtype=float)
        frac_err = np.asarray(self.data.frac_err_converged._run_data, dtype=float)
        f_achieved = np.asarray(self.data.f_lightshift_achieved._run_data, dtype=float)
        v_achieved = np.asarray(self.data.v_signal_achieved._run_data, dtype=float)
        t_integration = np.asarray(self.data.t_integration._run_data, dtype=float)

        # Convergence is defined on the returned error, not on the iteration
        # count: the fit path can use its last allowed correction and still land
        # inside threshold, so n_iter == N_max does not mean failure there.
        thresh = self.p.frac_err_threshold_imaging_pid
        converged = frac_err < thresh
        if self.p.imaging_power_use_fit:
            # n_iter accumulates across BOTH of acquire_rate's attempts, so the
            # ceiling is twice the per-attempt cap -- binning to N_max alone
            # silently drops the shots that used the re-probe, which are exactly
            # the ones worth looking at.
            N_max = 2 * self.p.N_max_correction_imaging_power
            label = 'corrections after the open-loop jump'
        else:
            N_max = self.p.N_max_iter_imaging_pid
            label = 'iterations until convergence'
        print(f"mean iterations = {n_iter.mean():.2f}, "
              f"converged fraction = {np.mean(converged):.2f}")
        if self.p.imaging_power_use_fit:
            # the number that says whether the cached map is any good: a jump
            # that lands inside threshold needs no corrections at all
            print(f"jump landed with no correction on "
                  f"{np.mean(n_iter == 0):.2f} of shots")

        f_unique = np.unique(f_target)
        mean_achieved = np.zeros(f_unique.size)
        sem_achieved = np.zeros(f_unique.size)
        mean_v_target = np.zeros(f_unique.size)
        mean_v_achieved = np.zeros(f_unique.size)
        sem_v_achieved = np.zeros(f_unique.size)
        mean_t = np.zeros(f_unique.size)
        conv_rate = np.zeros(f_unique.size)
        for i, f in enumerate(f_unique):
            sel = (f_target == f)
            samples = f_achieved[sel]
            v_samples = v_achieved[sel]
            mean_achieved[i] = np.nanmean(samples)
            mean_v_target[i] = np.nanmean(v_target[sel])
            mean_v_achieved[i] = np.nanmean(v_samples)
            mean_t[i] = np.nanmean(t_integration[sel])
            if samples.size > 1:
                sem_achieved[i] = np.nanstd(samples, ddof=1) / np.sqrt(samples.size)
                sem_v_achieved[i] = np.nanstd(v_samples, ddof=1) / np.sqrt(v_samples.size)
            conv_rate[i] = np.mean(converged[sel])

        # v and Hz are related by one positive constant with no offset
        # (f = slope * v / t), so the two error columns below are the same
        # number. They differ only if the calibration slope was changed between
        # the run and this analysis. The volts are what the servo actually sees.
        #
        # t_int is the window stabilize_lightshift picked. It should hold
        # target V flat at p.v_target_imaging_lightshift and vary inversely with
        # the commanded shift, except where it saturates t_apd_imaging_check_max
        # -- past that point target V falls and the errors should get noisier.
        t_max = self.p.t_apd_imaging_check_max
        t_min = self.p.t_apd_imaging_check_min
        print("\n  target f    achieved f     err     target V   achieved V    err    t_int   converged")
        for i, f in enumerate(f_unique):
            err_pct = 100 * (mean_achieved[i] - f) / f
            v_err_pct = 100 * (mean_v_achieved[i] - mean_v_target[i]) / mean_v_target[i]
            flag = ''
            if mean_t[i] >= t_max:
                flag = ' (capped)'
            elif mean_t[i] < t_min:
                flag = ' (SHORT)'
            print(f"  {f/1e3:6.2f} kHz  {mean_achieved[i]/1e3:7.2f} kHz  "
                  f"{err_pct:+6.2f}%   {mean_v_target[i]:7.4f} V  "
                  f"{mean_v_achieved[i]:7.4f} V  {v_err_pct:+6.2f}%  "
                  f"{mean_t[i]*1e6:6.1f} us  {conv_rate[i]:.2f}{flag}")

        fig, (ax0, ax1, ax2) = plt.subplots(1, 3, figsize=(13, 4))

        # the money plot: commanded vs delivered. Any departure from y = x is
        # calibration error, not servo error -- the servo only ever sees volts.
        lim = [0., f_unique.max() * 1.05 / 1e3]
        ax0.plot(lim, lim, '--', color='0.6', lw=1, label='ideal')
        ax0.errorbar(f_unique / 1e3, mean_achieved / 1e3, yerr=sem_achieved / 1e3,
                     fmt='o', ms=4, capsize=3, label='measured')
        ax0.set_xlabel('commanded light shift (kHz)')
        ax0.set_ylabel('achieved light shift (kHz)')
        ax0.set_xlim(lim)
        ax0.legend()

        # same comparison in the servo's own units
        vlim = [0., mean_v_target.max() * 1.05]
        ax1.plot(vlim, vlim, '--', color='0.6', lw=1, label='ideal')
        ax1.errorbar(mean_v_target, mean_v_achieved, yerr=sem_v_achieved,
                     fmt='o', ms=4, capsize=3, label='measured')
        ax1.set_xlabel('target integrated APD voltage (V)')
        ax1.set_ylabel('achieved integrated APD voltage (V)')
        ax1.set_xlim(vlim)
        ax1.legend()

        ax2.hist(n_iter, bins=np.arange(N_max + 2) - 0.5)
        ax2.set_xlabel(label)
        ax2.set_ylabel('counts')
        ax2.set_title(f'frac err threshold = {thresh:g}')

        fig.tight_layout()
        plt.show()
