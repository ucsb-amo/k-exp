from artiq.experiment import *
from artiq.language import now_mu, at_mu
import numpy as np

class timing_test(EnvExperiment):
    kernel_invariants = {
                        "m",
                        "Omega",
                        "dt",
                        "N_photons_per_shot",
                        "omega_guess_list",
                        "omega_sq_list",
                        "cos_z_list",
                        "sin_z_list",
                        "cos_H_list",
                        "sin_H_list",
                        "Omega_over_H_list",
                        "u_z_list",
                        "omega_step"}

    def prepare(self):
        self.core = self.get_device('core')
        self.ttl = self.get_device('ttl4')

        self.m = 21
        self.P0 = np.ones(self.m)
        self.P0 = self.P0 / np.sum(self.P0)
        self.state_list = np.zeros((self.m,3))
        self.state_list[:,2] = 1.

        self.Omega = 2*np.pi*80.e3 # rabi frequency guess

        omega_guess = 2*np.pi*147.e6 # state splitting guess
        offset = 5 # how many rabi frequencies away from the guess to "search"
        self.omega_guess_list = omega_guess + 2*offset*self.Omega*np.linspace(-1,1,self.m)
        self.omega_step = self.omega_guess_list[1] - self.omega_guess_list[0]
        self.omega_sq_list = self.omega_guess_list * self.omega_guess_list

        self.omega_raman = omega_guess # omega_ctrl
        
        self.dt = 2.e-6 # drive pulse length per step

        delta_omega_list = self.omega_raman - self.omega_guess_list
        alpha_z_list = 2.0 * self.dt * delta_omega_list
        self.cos_z_list = np.cos(alpha_z_list)
        self.sin_z_list = np.sin(alpha_z_list)

        norm_H_list = np.sqrt(self.Omega*self.Omega + delta_omega_list*delta_omega_list)
        self.Omega_over_H_list = self.Omega / norm_H_list
        self.u_z_list = delta_omega_list / norm_H_list

        alpha_H_list = 2.0 * norm_H_list * self.dt
        self.cos_H_list = np.cos(alpha_H_list)
        self.sin_H_list = np.sin(alpha_H_list)

        self.N_photons_per_shot = 10
        
    @kernel
    def run(self):
        v = 0.1
        v = v * self.N_photons_per_shot
        t = 100.e-6

        slack0 = 0
        slack1 = 1

        self.core.reset()
        
        self.ttl.on()
        t0 = now_mu()
        self.core.wait_until_mu(t0)
        # slack0 = t0 - self.core.get_rtio_counter_mu()
        (mn, std) = self.generate_posterior(v, 100.e-6)
        slack1 = t0 - self.core.get_rtio_counter_mu()
        # self.ttl.off()
        
        delay(10.e-3)
        print(abs(slack1))

    @kernel(flags={"fast-math"})
    def generate_posterior(self, k, t):
        P0_total = 0.
        moment_2 = 0.
        mn = 0.
        omega_guess_list = self.omega_guess_list
        omega_sq_list = self.omega_sq_list
        state_list = self.state_list
        P0 = self.P0
        cos_z_list = self.cos_z_list
        sin_z_list = self.sin_z_list
        cos_H_list = self.cos_H_list
        sin_H_list = self.sin_H_list
        Omega_over_H_list = self.Omega_over_H_list
        u_z_list = self.u_z_list
        m = self.m
        n_photons = self.N_photons_per_shot

        k_int = int(k)
        # int_k_mode = (k == k_int)
        nk_int = n_photons - k_int
        # int_nk_mode = (nk_int >= 0)

        wt = omega_guess_list[0] * t
        cos_wt = np.cos(wt)
        sin_wt = np.sin(wt)

        dwt = self.omega_step * t
        cos_dwt = np.cos(dwt)
        sin_dwt = np.sin(dwt)

        for j in range(m):
            omega = omega_guess_list[j]
            cos_z = cos_z_list[j]
            sin_z = sin_z_list[j]

            sx = state_list[j][0]
            sy = state_list[j][1]
            sz = state_list[j][2]

            cos_H = cos_H_list[j]
            sin_H = sin_H_list[j]
            Omega_over_H = Omega_over_H_list[j]
            u_z = u_z_list[j]

            u_x = Omega_over_H * cos_wt
            u_y = Omega_over_H * sin_wt

            one_minus_cos = 1.0 - cos_H

            uxux = u_x * u_x
            uyuy = u_y * u_y
            uzuz = u_z * u_z
            uxuy = u_x * u_y
            uxuz = u_x * u_z
            uyuz = u_y * u_z

            hx = (cos_H + one_minus_cos * uxux) * sx
            hx += (one_minus_cos * uxuy - sin_H * u_z) * sy
            hx += (one_minus_cos * uxuz + sin_H * u_y) * sz

            hy = (one_minus_cos * uxuy + sin_H * u_z) * sx
            hy += (cos_H + one_minus_cos * uyuy) * sy
            hy += (one_minus_cos * uyuz - sin_H * u_x) * sz

            hz = (one_minus_cos * uxuz - sin_H * u_y) * sx
            hz += (one_minus_cos * uyuz + sin_H * u_x) * sy
            hz += (cos_H + one_minus_cos * uzuz) * sz

            nx = cos_z * hx + sin_z * hy
            ny = -sin_z * hx + cos_z * hy

            state_list[j][0] = nx
            state_list[j][1] = ny
            state_list[j][2] = hz

            p1 = hz
            # if int_k_mode and int_nk_mode:
            p1_pow = 1.0
            i = 0
            while i < k_int:
                p1_pow *= p1
                i += 1

            q = 1.0 - p1
            q_pow = 1.0
            i = 0
            while i < nk_int:
                q_pow *= q
                i += 1

            pj = P0[j] * p1_pow * q_pow
            
            P0_total += pj
            mn += pj * omega
            moment_2 += pj * omega_sq_list[j]

            P0[j] = pj

            next_cos_wt = cos_wt * cos_dwt - sin_wt * sin_dwt
            sin_wt = sin_wt * cos_dwt + cos_wt * sin_dwt
            cos_wt = next_cos_wt

        mn = mn / P0_total
        moment_2 = moment_2 / P0_total

        std = np.sqrt(moment_2 - mn * mn)

        return mn, std