from artiq.experiment import *
from artiq.language import now_mu, delay
import numpy as np

class timing_test(EnvExperiment):
    kernel_invariants = {
                        "m",
                        "dt",
                        "N_photons_per_shot",
                        "omega_guess_list",
                        "omega_sq_list",
                        "state_x",
                        "state_y",
                        "state_z",
                        "cos_z_list",
                        "sin_z_list",
                        "cos_H_list",
                        "sin_H_list",
                        "Omega_over_H_list",
                        "u_z_list",
                        "sin_lut",
                        "lut_size",
                        "lut_scale",
                        "two_pi",
                        "pi_half"}

    def prepare(self):
        self.core = self.get_device('core')

        self.m = 21
        self.P0 = np.ones(self.m)
        self.P0 = self.P0 / np.sum(self.P0)
        self.state_x = np.zeros(self.m)
        self.state_y = np.zeros(self.m)
        self.state_z = np.ones(self.m)

        self.Omega = 2*np.pi*80.e3 # rabi frequency guess
        self.two_pi = 2*np.pi
        self.pi_half = 0.5*np.pi

        omega_guess = 2*np.pi*147.e6 # state splitting guess
        offset = 5 # how many rabi frequencies away from the guess to "search"
        self.omega_guess_list = omega_guess + 2*offset*self.Omega*np.linspace(-1,1,self.m)
        self.omega_sq_list = self.omega_guess_list * self.omega_guess_list

        self.omega_raman = omega_guess # omega_ctrl
        
        self.dt = 2.e-6 # drive pulse length per step

        # These tables depend on (omega_raman, Omega) and are refreshed in kernel each call.
        self.cos_z_list = np.zeros(self.m)
        self.sin_z_list = np.zeros(self.m)
        self.cos_H_list = np.ones(self.m)
        self.sin_H_list = np.zeros(self.m)
        self.Omega_over_H_list = np.zeros(self.m)
        self.u_z_list = np.zeros(self.m)

        self.N_photons_per_shot = 10

        # Sine lookup table used by kernel-side trig interpolation.
        self.lut_size = 4096
        self.lut_scale = self.lut_size / self.two_pi
        self.sin_lut = np.sin(self.two_pi * np.arange(self.lut_size) / self.lut_size)

    @kernel(flags={"fast-math"})
    def sin_lut_interp(self, x):
        two_pi = self.two_pi
        # Fast phase wrap to [0, 2pi) without expensive transcendental operations.
        turns = int(x / two_pi)
        x -= two_pi * turns
        if x < 0.0:
            x += two_pi

        y = x * self.lut_scale
        i0 = int(y)
        frac = y - i0
        i1 = i0 + 1
        if i1 == self.lut_size:
            i1 = 0

        s0 = self.sin_lut[i0]
        s1 = self.sin_lut[i1]
        return s0 + frac * (s1 - s0)

    @kernel(flags={"fast-math"})
    def cos_lut_interp(self, x):
        return self.sin_lut_interp(x + self.pi_half)

    @kernel(flags={"fast-math"})
    def update_dynamic_tables(self):
        omega_guess_list = self.omega_guess_list
        cos_z_list = self.cos_z_list
        sin_z_list = self.sin_z_list
        cos_H_list = self.cos_H_list
        sin_H_list = self.sin_H_list
        Omega_over_H_list = self.Omega_over_H_list
        u_z_list = self.u_z_list
        m = self.m

        omega_raman = self.omega_raman
        Omega = self.Omega
        dt = self.dt

        j = 0
        while j < m:
            print('hi')
            delta_omega = omega_raman - omega_guess_list[j]

            alpha_z = 2.0 * dt * delta_omega
            cos_z_list[j] = self.cos_lut_interp(alpha_z)
            sin_z_list[j] = self.sin_lut_interp(alpha_z)

            norm_H = np.sqrt(Omega * Omega + delta_omega * delta_omega)
            if norm_H > 0.0:
                inv_norm_H = 1.0 / norm_H
                Omega_over_H_list[j] = Omega * inv_norm_H
                u_z_list[j] = delta_omega * inv_norm_H

                alpha_H = 2.0 * norm_H * dt
                cos_H_list[j] = self.cos_lut_interp(alpha_H)
                sin_H_list[j] = self.sin_lut_interp(alpha_H)
            else:
                # Degenerate axis/angle case maps to identity evolution for this term.
                Omega_over_H_list[j] = 0.0
                u_z_list[j] = 0.0
                cos_H_list[j] = 1.0
                sin_H_list[j] = 0.0
            j += 1
        
    @kernel
    def run(self):
        v = 0.1
        v = v * self.N_photons_per_shot
        t = 100.e-6

        slack0 = 0
        slack1 = 1

        self.core.reset()
        
        t0 = now_mu()
        self.core.wait_until_mu(t0)
        # slack0 = t0 - self.core.get_rtio_counter_mu()
        (self.omega_raman, self.Omega) = self.generate_posterior(v, 100.e-6)
        slack1 = t0 - self.core.get_rtio_counter_mu()
        
        delay(10.e-3)
        print(abs(slack1))

    @kernel(flags={"fast-math"})
    def generate_posterior(self, k, t):
        self.update_dynamic_tables()

        P0_total = 0.
        moment_2 = 0.
        mn = 0.
        omega_guess_list = self.omega_guess_list
        omega_sq_list = self.omega_sq_list
        state_x = self.state_x
        state_y = self.state_y
        state_z = self.state_z
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
        nk_int = n_photons - k_int

        for j in range(m):
            omega = omega_guess_list[j]
            cos_z = cos_z_list[j]
            sin_z = sin_z_list[j]

            wt = omega * t
            cos_wt = self.cos_lut_interp(wt)
            sin_wt = self.sin_lut_interp(wt)

            sx = state_x[j]
            sy = state_y[j]
            sz = state_z[j]

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

            state_x[j] = nx
            state_y[j] = ny
            state_z[j] = hz

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

        mn = mn / P0_total
        moment_2 = moment_2 / P0_total

        std = np.sqrt(moment_2 - mn * mn)

        return mn, std