from artiq.experiment import *
from artiq.experiment import delay
from artiq.language import TFloat, TInt32, TTuple
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class imaging_apd_pid_optimize_threshold(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=False,
                      imaging_type=img_types.ABSORPTION,
                      suppress_live_od=True)

        # goal: with the P/I gains already tuned (imaging_apd_pid_optimize_gains.py),
        # sweep the convergence threshold to find the tightest fractional error
        # the PID can still reliably hit within N_max_iter, then confirm the
        # winner with a longer statistics run.

        self.p.t_apd_imaging_check = 150.e-6

        self.p.N_max_iter = 50

        self.p.v_target = 1.

        # DAC output is limited to +/-10 V; stay just inside that rail
        self.p.v_dac_max = 9.99

        # gains found by imaging_apd_pid_optimize_gains.py
        self.p.pid_gain_p = -0.019
        self.p.pid_gain_i = -0.0175

        # threshold grid to sweep, smallest (tightest) to largest -- CALIBRATED:
        # values here are an example
        self.p.frac_err_threshold_grid = np.geomspace(0.0005, 0.01, 31)

        # a threshold only "counts" as achievable if at least this fraction of
        # repeats converge within N_max_iter
        self.p.min_conv_rate_acceptable = 0.95

        self.p.N_repeats_sweep = 20
        self.p.N_repeats_final = 100

        N_thresh = len(self.p.frac_err_threshold_grid)

        self.data.apd_check = self.data.add_data_container(2) # 2 points, one each for light + dark

        # one row per threshold value tested
        self.data.sweep_threshold = self.data.add_data_container(N_thresh)
        self.data.sweep_n_iter = self.data.add_data_container((N_thresh, self.p.N_repeats_sweep), np.int32)
        self.data.sweep_frac_err = self.data.add_data_container((N_thresh, self.p.N_repeats_sweep))

        self.data.best_frac_err_threshold = self.data.add_data_container(1)

        # confirmation run with the winning threshold
        self.data.final_n_iter = self.data.add_data_container(self.p.N_repeats_final, np.int32)
        self.data.final_frac_err_converged = self.data.add_data_container(self.p.N_repeats_final)

        self.finish_prepare(shuffle=True)

    @kernel
    def check_current_v_apd(self):
        # check current light level
        self.integrated_imaging_pulse(self.data.apd_check,
                                      t=self.p.t_apd_imaging_check,
                                      idx=0)
        delay(10.e-6)

        # dark image
        self.integrated_imaging_pulse(self.data.apd_check,
                                      t=self.p.t_apd_imaging_check,
                                      dark=True,
                                      idx=1)

        delay(10.e-6)

        v_light = self.data.apd_check.shot_data[0]
        v_dark = self.data.apd_check.shot_data[1]
        v_signal = v_light - v_dark
        return v_signal

    @kernel
    def jump_to_target(self, v_target):

        v_signal = self.check_current_v_apd()

        # no measurable signal (e.g. imaging light off/blocked) -- skip the
        # jump rather than dividing by zero
        if v_signal != 0.:
            v_pid_current = self.imaging.dac_pid.v
            v_pid_target = v_pid_current * (v_target / v_signal)
            if v_pid_target > self.p.v_dac_max:
                v_pid_target = self.p.v_dac_max
            elif v_pid_target < -self.p.v_dac_max:
                v_pid_target = -self.p.v_dac_max
            self.imaging.set_power(v_pid_target)

    @kernel
    def feedback_check_pid_for_lightshift(self, v_target, frac_err_threshold) -> TTuple([TInt32, TFloat]):
        p_gain = self.p.pid_gain_p
        i_gain = self.p.pid_gain_i

        i = 0
        N_MAX_ITER = self.p.N_max_iter
        frac_err = 1.
        err_integral = 0.

        while i < N_MAX_ITER:

            v_signal = self.check_current_v_apd()
            err = v_signal - v_target

            frac_err = abs(err / v_target)
            if frac_err < frac_err_threshold:
                break
            else:
                err_integral += err
                v_pid_current = self.imaging.dac_pid.v
                new_v_pid = p_gain * err + i_gain * err_integral + v_pid_current
                if new_v_pid > self.p.v_dac_max:
                    new_v_pid = self.p.v_dac_max
                elif new_v_pid < -self.p.v_dac_max:
                    new_v_pid = -self.p.v_dac_max
                self.imaging.set_power(new_v_pid)
                delay(1.e-3)
                i += 1

        return i, frac_err

    @rpc
    def select_min_threshold(self, n_iter_grid, threshold_grid) -> TFloat:

        n_iter_grid = np.asarray(n_iter_grid, dtype=float)
        threshold_grid = np.asarray(threshold_grid, dtype=float)
        conv_rate = np.mean(n_iter_grid < self.p.N_max_iter, axis=1)
        mean_n_iter = np.mean(n_iter_grid, axis=1)

        print("threshold    mean iters   conv. rate")
        for idx in range(len(threshold_grid)):
            print(f"{threshold_grid[idx]:10.5f}  {mean_n_iter[idx]:10.2f}  {conv_rate[idx]:10.2f}")

        acceptable = conv_rate >= self.p.min_conv_rate_acceptable
        if np.any(acceptable):
            # smallest (tightest) threshold that still reliably converges
            idx_acceptable = np.where(acceptable)[0]
            best_idx = idx_acceptable[np.argmin(threshold_grid[idx_acceptable])]
        else:
            # nothing hit the reliability bar -- fall back to whichever
            # threshold converged most often
            best_idx = int(np.argmax(conv_rate))
            print(f"\nwarning: no threshold reached {100*self.p.min_conv_rate_acceptable:.0f}% "
                  f"convergence within N_max_iter={self.p.N_max_iter}; falling back to the "
                  "most reliable threshold tested")

        best_threshold = float(threshold_grid[best_idx])
        print(f"\nminimum achievable fractional error threshold: {best_threshold:.5f} "
              f"({mean_n_iter[best_idx]:.2f} mean iterations, {100*conv_rate[best_idx]:.0f}% converged)")

        return best_threshold

    @kernel
    def scan_kernel(self):

        v_target = self.p.v_target

        N_thresh = len(self.p.frac_err_threshold_grid)

        for tidx in range(N_thresh):
            threshold = self.p.frac_err_threshold_grid[tidx]
            self.data.sweep_threshold.put_data(threshold, i=tidx)

            for r in range(self.p.N_repeats_sweep):
                # this loop replaces the usual scan()/N_repeats machinery,
                # which normally re-syncs the timeline every shot -- do
                # that by hand so many back-to-back repeats don't drift
                # into an underflow
                self.core.break_realtime()
                self.jump_to_target(v_target)
                n_iter, frac_err = self.feedback_check_pid_for_lightshift(v_target, threshold)
                self.data.sweep_n_iter.put_data(n_iter, i=tidx, j=r)
                self.data.sweep_frac_err.put_data(frac_err, i=tidx, j=r)

        best_threshold = self.select_min_threshold(self.data.sweep_n_iter.shot_data,
                                                     self.data.sweep_threshold.shot_data)
        # select_min_threshold does host-side numpy work and prints a whole
        # table -- give the timeline slack to catch back up before resuming
        # real-time pulses
        self.core.break_realtime()
        self.data.best_frac_err_threshold.put_data(best_threshold)

        for r in range(self.p.N_repeats_final):
            self.core.break_realtime()
            self.jump_to_target(v_target)
            n_iter, frac_err = self.feedback_check_pid_for_lightshift(v_target, best_threshold)
            self.data.final_n_iter.put_data(n_iter, i=r)
            self.data.final_frac_err_converged.put_data(frac_err, i=r)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False, setup_slm=False)
        self.scan()

    def analyze(self):
        import os
        import matplotlib.pyplot as plt

        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

        # the whole sweep + confirmation procedure runs as a single "shot",
        # so the scan dimension (xvardims=[1]) is a leading axis of size 1
        best_threshold = float(self.data.best_frac_err_threshold._run_data[0])
        n_iter = self.data.final_n_iter._run_data[0]
        frac_err_converged = self.data.final_frac_err_converged._run_data[0]

        conv_rate = np.mean(n_iter < self.p.N_max_iter)
        print(f"minimum allowed fractional error threshold: {best_threshold:.5f}")
        print(f"confirmation run ({self.p.N_repeats_final} repeats): "
              f"mean iterations = {n_iter.mean():.2f}, converged fraction = {conv_rate:.2f}")

        fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(9, 4))

        ax0.hist(n_iter, bins=np.arange(self.p.N_max_iter + 2) - 0.5)
        ax0.set_xlabel('iterations until convergence')
        ax0.set_ylabel('counts')
        ax0.set_title(f'fractional error threshold = {best_threshold:g}')

        ax1.hist(frac_err_converged * 1.e3, bins=30)
        ax1.set_xlabel('fractional error (x$10^3$) upon convergence')
        ax1.set_ylabel('counts')

        fig.suptitle(f'minimum fractional error threshold: {best_threshold:g}')
        fig.tight_layout()
        plt.show()
