from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np

class imaging_stabilize_power_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=False,
                      imaging_type=img_types.ABSORPTION,
                      suppress_live_od=True)

        # exercises BeatLockImagingPID.stabilize_power, which replaces the
        # check_current_v_apd / jump_to_target / feedback_check_pid_for_lightshift
        # boilerplate in the other JP imaging_apd_pid_* experiments.

        self.p.v_target = 1.

        # these live in waxx ExptParams -- override here to test other settings
        self.p.t_apd_imaging_check = 150.e-6
        self.p.frac_err_threshold_imaging_pid = 0.003
        self.p.N_max_iter_imaging_pid = np.int32(50)
        self.p.gain_p_imaging_pid = -0.019
        self.p.gain_i_imaging_pid = -0.0175

        # run many repeats to build up convergence statistics
        self.p.N_repeats = 100

        self.data.n_iter = self.data.add_data_container(1, np.int32)
        self.data.frac_err_converged = self.data.add_data_container(1)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        n_iter, frac_err = self.imaging.stabilize_power(self.p.v_target)
        self.data.n_iter.put_data(n_iter)
        self.data.frac_err_converged.put_data(frac_err)

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
        # stats straight from the in-memory run data instead of via atomdata
        n_iter = self.data.n_iter._run_data
        frac_err_converged = self.data.frac_err_converged._run_data

        N_max = self.p.N_max_iter_imaging_pid
        conv_rate = np.mean(n_iter < N_max)
        print(f"mean iterations = {n_iter.mean():.2f}, converged fraction = {conv_rate:.2f}")

        fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(9, 4))

        ax0.hist(n_iter, bins=np.arange(N_max + 2) - 0.5)
        ax0.set_xlabel('iterations until convergence')
        ax0.set_ylabel('counts')
        ax0.set_title(f'fractional error threshold = {self.p.frac_err_threshold_imaging_pid:g}')

        ax1.hist(frac_err_converged * 1.e3, bins=30)
        ax1.set_xlabel('fractional error (x$10^3$) upon convergence')
        ax1.set_ylabel('counts')

        fig.tight_layout()
        plt.show()
