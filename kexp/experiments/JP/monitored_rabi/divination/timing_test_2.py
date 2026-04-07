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
                        "sin_lut",
                        "lut_size",
                        "lut_scale",
                        "lut_mask",
                        "lut_quarter",
                        "two_pi",
                        "pi_half",
                        "inv_two_pi"}

    def prepare(self):
        self.core = self.get_device('core')
        self.ttl = self.get_device('ttl4')

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

        self.N_photons_per_shot = 10000

        self.lut_size = 4096
        self.lut_scale = self.lut_size / self.two_pi
        self.lut_mask = self.lut_size - 1
        self.lut_quarter = self.lut_size // 4
        self.inv_two_pi = 1.0 / self.two_pi
        self.sin_lut = np.sin(self.two_pi * np.arange(self.lut_size) / self.lut_size)

    @kernel(flags={"fast-math"})
    def sincos_lut_interp(self, x):
        inv_two_pi = self.inv_two_pi
        two_pi = self.two_pi
        turns = int(x * inv_two_pi)
        x -= two_pi * turns
        if x < 0.0:
            x += two_pi

        y = x * self.lut_scale
        i0 = int(y)
        frac = y - i0

        lut_mask = self.lut_mask
        i1 = (i0 + 1) & lut_mask
        ic0 = (i0 + self.lut_quarter) & lut_mask
        ic1 = (i1 + self.lut_quarter) & lut_mask

        sin_lut = self.sin_lut
        s0 = sin_lut[i0]
        s1 = sin_lut[i1]
        c0 = sin_lut[ic0]
        c1 = sin_lut[ic1]

        sin_val = s0 + frac * (s1 - s0)
        cos_val = c0 + frac * (c1 - c0)
        return sin_val, cos_val

    @kernel(flags={"fast-math"})
    def sin_lut_interp(self, x):
        (s, c) = self.sincos_lut_interp(x)
        return s

    @kernel(flags={"fast-math"})
    def cos_lut_interp(self, x):
        (s, c) = self.sincos_lut_interp(x)
        return c

    @kernel(flags={"fast-math"})
    def powi(self, base, exp):
        # Exponentiation by squaring for non-negative integer exponents.
        result = 1.0
        b = base
        e = exp
        while e > 0:
            if (e & 1) != 0:
                result *= b
            b *= b
            e = e // 2
        return result

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

        k = int(v)
        (mn, std) = self.generate_posterior(k, t)
        slack1 = t0 - self.core.get_rtio_counter_mu()
        
        delay(10.e-3)
        print(abs(slack1))

    @kernel(flags={"fast-math"})
    def generate_posterior(self, k, t):
        P0_total = 0.
        moment_2 = 0.
        mn = 0.
        omega_guess_list = self.omega_guess_list
        omega_sq_list = self.omega_sq_list
        state_x = self.state_x
        state_y = self.state_y
        state_z = self.state_z
        P0 = self.P0

        m = self.m
        n_photons = self.N_photons_per_shot

        omega_raman = self.omega_raman
        Omega = self.Omega
        Omega_sq = Omega * Omega
        two_dt = 2.0 * self.dt

        if m > 1:
            domega = omega_guess_list[1] - omega_guess_list[0]
        else:
            domega = 0.0

        omega0 = omega_guess_list[0]

        # omega * t phase recursion across uniformly spaced omega grid.
        (sin_wt, cos_wt) = self.sincos_lut_interp(omega0 * t)
        (sin_wt_step, cos_wt_step) = self.sincos_lut_interp(domega * t)

        # alpha_z = 2*dt*(omega_raman - omega) is also uniformly spaced.
        (sin_z, cos_z) = self.sincos_lut_interp(two_dt * (omega_raman - omega0))
        (sin_z_step, cos_z_step) = self.sincos_lut_interp(-two_dt * domega)

        k_int = int(k)
        if k_int < 0:
            k_int = 0
        if k_int > n_photons:
            k_int = n_photons
        nk_int = n_photons - k_int

        j = 0
        while j < m:
            omega = omega_guess_list[j]
            delta_omega = omega_raman - omega

            norm_H = np.sqrt(Omega_sq + delta_omega * delta_omega)
            if norm_H > 0.0:
                inv_norm_H = 1.0 / norm_H
                Omega_over_H = Omega * inv_norm_H
                u_z = delta_omega * inv_norm_H
                (sin_H, cos_H) = self.sincos_lut_interp(two_dt * norm_H)
            else:
                Omega_over_H = 0.0
                u_z = 0.0
                sin_H = 0.0
                cos_H = 1.0

            sx = state_x[j]
            sy = state_y[j]
            sz = state_z[j]

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
            q = 1.0 - p1
            p1_pow = self.powi(p1, k_int)
            q_pow = self.powi(q, nk_int)

            pj = P0[j] * p1_pow * q_pow

            P0_total += pj
            mn += pj * omega
            moment_2 += pj * omega_sq_list[j]

            P0[j] = pj

            # Advance sin/cos states to next grid point with angle-addition.
            next_sin_wt = sin_wt * cos_wt_step + cos_wt * sin_wt_step
            next_cos_wt = cos_wt * cos_wt_step - sin_wt * sin_wt_step
            sin_wt = next_sin_wt
            cos_wt = next_cos_wt

            next_sin_z = sin_z * cos_z_step + cos_z * sin_z_step
            next_cos_z = cos_z * cos_z_step - sin_z * sin_z_step
            sin_z = next_sin_z
            cos_z = next_cos_z

            j += 1

        if P0_total <= 0.0:
            return self.omega_raman, 0.0

        mn = mn / P0_total
        moment_2 = moment_2 / P0_total

        var = moment_2 - mn * mn
        if var < 0.0:
            var = 0.0
        std = np.sqrt(var)

        return mn, std