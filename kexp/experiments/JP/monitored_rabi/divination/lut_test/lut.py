from artiq.experiment import *
from artiq.language import now_mu, at_mu
import numpy as np

from kexp.experiments.JP.monitored_rabi.divination.lut_test.generate_lut import ( mean_func_list, std_func_list,
                                                                                Omega, omega_0, nu, n_photons,
                                                                                lut_f1, lut_f2, lut_f3, lut_f4,
                                                                                lut_g1, lut_g2, lut_g3, lut_g4,
                                                                                f_lut_interpol_4d)

v_apd_all_down = -1.7
v_apd_all_up = -1.0
v_range = v_apd_all_up - v_apd_all_down

class lut(EnvExperiment):
    kernel_invariants = {"Omega"}

    def prepare(self):
        self.core = self.get_device('core')
        self.ttl = self.get_device('ttl4')

        self.Omega = Omega # rabi frequency guess
        self.omega_raman = omega_0 # omega_ctrl

        self.v = np.zeros(nu)

        self.k = np.array([0.1 * n_photons]*5)

    ### when setting raman beams make sure to divide by 2pi

    @kernel
    def convert_measurement(self, v_apd):
        v_apd = (v_apd - v_apd_all_down) / v_range
        if v_apd < 0.0:
            return 0.0
        if v_apd > 1.0:
            return 1.0
        return v_apd

    @kernel
    def run(self):
        mn = 0.
        std = 0.

        self.core.reset()

        # 

        for i in range(nu):
            k = self.k[i] 
            self.v[i] = k/n_photons # replace this with apd imaging

            if i<nu-1: #was <nu-1
                mean_func=mean_func_list[i]
                std_func=std_func_list[i]
            
                t = now_mu()
                self.core.wait_until_mu(now_mu())
                mn=mean_func(self.v)
                std=std_func(self.v)
                slack = t - self.core.get_rtio_counter_mu()
                print(slack)

            omega_ctrl_set=mn
            Omega_set=std