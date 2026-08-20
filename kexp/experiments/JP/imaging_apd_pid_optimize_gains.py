from artiq.experiment import *
from artiq.experiment import delay
from artiq.language import TFloat, TInt32, TTuple
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class imaging_apd_pid_optimize_gains(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=False,
                      imaging_type=img_types.ABSORPTION,
                      suppress_live_od=True)

        # goal: sweep the P/I feedback gains, score each combo by how fast
        # (and how reliably) the APD PID converges, then confirm the winner
        # with a longer statistics run.

        self.p.t_apd_imaging_check = 150.e-6

        self.p.N_max_iter = 50
        self.p.frac_err_threshold = 0.003

        self.p.v_target = 1.

        # DAC output is limited to +/-10 V; stay just inside that rail
        self.p.v_dac_max = 9.99

        # gain grid to sweep -- CALIBRATED: values here are an example
        self.p.pid_gain_p_grid = -0.019 + np.linspace(-0.005,0.005,11)
        self.p.pid_gain_i_grid = -0.0175 + np.linspace(-0.005,0.005,11)

        self.p.N_repeats_sweep = 20
        self.p.N_repeats_final = 100

        N_combos = len(self.p.pid_gain_p_grid) * len(self.p.pid_gain_i_grid)

        self.data.apd_check = self.data.add_data_container(2) # 2 points, one each for light + dark

        # one row per (p_gain, i_gain) combo
        self.data.sweep_p_gain = self.data.add_data_container(N_combos)
        self.data.sweep_i_gain = self.data.add_data_container(N_combos)
        self.data.sweep_n_iter = self.data.add_data_container((N_combos, self.p.N_repeats_sweep), np.int32)
        self.data.sweep_frac_err = self.data.add_data_container((N_combos, self.p.N_repeats_sweep))

        self.data.best_pid_gain_p = self.data.add_data_container(1)
        self.data.best_pid_gain_i = self.data.add_data_container(1)

        # confirmation run with the winning gains
        self.data.final_n_iter = self.data.add_data_container(self.p.N_repeats_final, np.int32)
        self.data.final_frac_err_converged = self.data.add_data_container(self.p.N_repeats_final)

        self.finish_prepare(shuffle=True)

    @kernel
    def lightshift_to_v_target(self, f_lightshift):
        # CALIBRATED -- values here are an example
        # 0.05 integrated voltage above background per 10 kHz light shift
        slope_v_apd_per_f_lightshift = 0.05 / 10.e3
        offset_v_apd_per_f_lightshift = 0. # should be exactly 0

        m = slope_v_apd_per_f_lightshift
        y0 = offset_v_apd_per_f_lightshift

        return m * f_lightshift + y0

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
    def feedback_check_pid_for_lightshift(self, v_target, p_gain, i_gain) -> TTuple([TInt32, TFloat]):

        i = 0
        N_MAX_ITER = self.p.N_max_iter
        frac_err = 1.
        err_integral = 0.

        while i < N_MAX_ITER:

            v_signal = self.check_current_v_apd()
            err = v_signal - v_target

            frac_err = abs(err / v_target)
            if frac_err < self.p.frac_err_threshold:
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

    @rpc(flags={"async"})
    def print_progress(self, combo, N_combos):
        print(f"combo {combo}/{N_combos} complete")

    @rpc
    def select_best_gains(self, n_iter_grid, frac_err_grid, p_grid, i_grid) -> TTuple([TFloat, TFloat]):

        n_iter_grid = np.asarray(n_iter_grid, dtype=float)
        conv_rate = np.mean(n_iter_grid < self.p.N_max_iter, axis=1)
        mean_n_iter = np.mean(n_iter_grid, axis=1)

        # lower is better -- reward fast convergence, heavily penalize combos
        # that don't reliably converge within N_max_iter
        score = mean_n_iter + self.p.N_max_iter * (1. - conv_rate)
        best_idx = int(np.argmin(score))

        print("p_gain      i_gain      mean iters   conv. rate")
        for idx in range(len(score)):
            print(f"{p_grid[idx]:10.5f}  {i_grid[idx]:10.5f}  {mean_n_iter[idx]:10.2f}  {conv_rate[idx]:10.2f}")

        best_p = float(p_grid[best_idx])
        best_i = float(i_grid[best_idx])

        print(f"\nbest gains: pid_gain_p = {best_p:.5f}, pid_gain_i = {best_i:.5f} "
              f"({mean_n_iter[best_idx]:.2f} mean iterations, {100*conv_rate[best_idx]:.0f}% converged)")

        return best_p, best_i

    @kernel
    def scan_kernel(self):

        v_target = self.p.v_target

        N_p = len(self.p.pid_gain_p_grid)
        N_i = len(self.p.pid_gain_i_grid)

        combo = 0
        for pidx in range(N_p):
            p_gain = self.p.pid_gain_p_grid[pidx]
            for iidx in range(N_i):
                i_gain = self.p.pid_gain_i_grid[iidx]

                self.data.sweep_p_gain.put_data(p_gain, i=combo)
                self.data.sweep_i_gain.put_data(i_gain, i=combo)

                for r in range(self.p.N_repeats_sweep):
                    # this loop replaces the usual scan()/N_repeats machinery,
                    # which normally re-syncs the timeline every shot -- do
                    # that by hand so thousands of back-to-back repeats don't
                    # drift into an underflow
                    self.jump_to_target(v_target)
                    n_iter, frac_err = self.feedback_check_pid_for_lightshift(v_target, p_gain, i_gain)
                    self.data.sweep_n_iter.put_data(n_iter, i=combo, j=r)
                    self.data.sweep_frac_err.put_data(frac_err, i=combo, j=r)

                combo += 1
                if combo % 10 == 0:
                    self.print_progress(combo, N_p * N_i)
                    self.core.break_realtime()

        best_p, best_i = self.select_best_gains(self.data.sweep_n_iter.shot_data,
                                                 self.data.sweep_frac_err.shot_data,
                                                 self.data.sweep_p_gain.shot_data,
                                                 self.data.sweep_i_gain.shot_data)
        # select_best_gains does host-side numpy work and prints a whole
        # table -- give the timeline slack to catch back up before resuming
        # real-time pulses
        self.data.best_pid_gain_p.put_data(best_p)
        self.data.best_pid_gain_i.put_data(best_i)

        
        self.core.break_realtime()              
        for r in range(self.p.N_repeats_final):
            self.jump_to_target(v_target)
            n_iter, frac_err = self.feedback_check_pid_for_lightshift(v_target, best_p, best_i)
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
        best_p = float(self.data.best_pid_gain_p._run_data[0])
        best_i = float(self.data.best_pid_gain_i._run_data[0])
        n_iter = self.data.final_n_iter._run_data[0]
        frac_err_converged = self.data.final_frac_err_converged._run_data[0]

        conv_rate = np.mean(n_iter < self.p.N_max_iter)
        print(f"ideal gains: pid_gain_p = {best_p:.5f}, pid_gain_i = {best_i:.5f}")
        print(f"confirmation run ({self.p.N_repeats_final} repeats): "
              f"mean iterations = {n_iter.mean():.2f}, converged fraction = {conv_rate:.2f}")

        fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(9, 4))

        ax0.hist(n_iter, bins=np.arange(self.p.N_max_iter + 2) - 0.5)
        ax0.set_xlabel('iterations until convergence')
        ax0.set_ylabel('counts')
        ax0.set_title(f'fractional error threshold = {self.p.frac_err_threshold:g}')

        ax1.hist(frac_err_converged * 1.e3, bins=30)
        ax1.set_xlabel('fractional error (x$10^3$) upon convergence')
        ax1.set_ylabel('counts')

        fig.suptitle(f'best gains: p = {best_p:.5f}, i = {best_i:.5f}')
        fig.tight_layout()
        plt.show()
