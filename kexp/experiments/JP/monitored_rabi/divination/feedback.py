from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu
from kexp import Base, img_types, cameras
import numpy as np

class feedback(EnvExperiment, Base):
    kernel_invariants = {
                        "m",
                        "dt",
                        "dt_z",
                        "omega_z_lightshift",
                        "N_pulses",
                        "N_photons_per_shot",
                        "v_apd_all_up",
                        "v_apd_all_down",
                        "v_range",
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
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)
        
        ### parameters

        self.xvar('dummy',[0])

        self.p.amp_imaging = 0.3
        self.p.t_img_pulse = 5.e-6

        self.p.t_raman_pulse = 3.5e-6

        self.N_pulses = 5 # number of steps of evolution
        self.m = 21 # feedback grid size
        
        ### calibrations

        self.v_apd_all_up = -0.191
        self.v_apd_all_down = -0.226

        n_photons_per_us_per_imgamp = 431.77 # 63017

        # for vpd = 0.3, lightshift 18.74kHz (#63034)
        self.omega_z_lightshift = 2*np.pi*18.74e3

        ### setup data containers

        self.idx = 0
        self.data.omega_raman = self.data.add_data_container(self.N_pulses)
        self.data.apd = self.data.add_data_container(self.N_pulses)
        self.data.counts = self.data.add_data_container(self.N_pulses)
        self.data.ts = self.data.add_data_container(self.N_pulses)

        ### feedback setup

        self.dt_z = self.p.t_img_pulse # z rotation due to measurement pulse
        self.dt = self.p.t_raman_pulse # drive pulse length per step

        self.Omega = 2*np.pi*60.e3 # rabi frequency guess

        omega_guess = 2*np.pi*self.p.frequency_raman_transition # state splitting guess
        omega_guess_offset = self.Omega
        omega_guess = omega_guess + omega_guess_offset

        offset = 5 # how many rabi frequencies away from the guess to "search"
        self.omega_guess_list = omega_guess + 2*offset*self.Omega*np.linspace(-1,1,self.m)
        self.omega_sq_list = self.omega_guess_list * self.omega_guess_list

        self.omega_raman = omega_guess # omega_ctrl
        
        self.v_range = self.v_apd_all_up - self.v_apd_all_down
        n_photons_per_us = n_photons_per_us_per_imgamp * self.p.amp_imaging
        self.N_photons_per_shot = n_photons_per_us * self.p.t_img_pulse * 1.e6
        
        ### constants and array setup

        self.P0 = np.ones(self.m)
        self.P0 = self.P0 / np.sum(self.P0)
        self.P0_total = 1.

        self.state_x = np.zeros(self.m)
        self.state_y = np.zeros(self.m)
        self.state_z = np.ones(self.m)

        self.t_posterior_mu = np.int64(0) # updated in initialize_feedback

        self.two_pi = 2*np.pi
        self.pi_half = 0.5*np.pi

        ### lookup table setup

        self.lut_size = 4096
        self.lut_scale = self.lut_size / self.two_pi
        self.lut_mask = self.lut_size - 1
        self.lut_quarter = self.lut_size // 4
        self.inv_two_pi = 1.0 / self.two_pi
        self.sin_lut = np.sin(self.two_pi * np.arange(self.lut_size) / self.lut_size)

        ###
        
        # self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)
        
        self.finish_prepare()

    @kernel
    def scan_kernel(self):

        self.integrator.init()

        self.initialize_feedback()
        delay(10.e-3)
        
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)
        self.prep_raman(frequency_raman=self.omega_raman)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        delay(10.e-6)

        t0 = now_mu() # beginning of time
        for i in range(self.N_pulses):
            k = self.measurement()
            t_mu = now_mu()
            t = (t_mu - t0)*1.e-9
            self.omega_raman, _ = self.generate_posterior(k, t)

            self.data.ts.shot_data[i] = t
            self.data.counts.shot_data[i] = float(k)
            self.data.omega_raman.shot_data[i] = self.omega_raman

            delay_mu(self.t_posterior_mu)
            delay_mu(20000)
            self.raman.set(self.omega_raman/(2*np.pi))
            self.raman.pulse(self.p.t_raman_pulse)
            delay_mu(20000)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()

        self.core.wait_until_mu(now_mu())
        print(self.data.omega_raman.shot_data)
        # self.scope.read_sweep(0)
        # self.core.break_realtime()
        delay(30.e-3)

    @portable
    def convert_measurement(self, v_apd):
        return round(self.N_photons_per_shot * (v_apd - self.v_apd_all_down) / self.v_range)
    
    @kernel
    def measurement(self):
        idx = self.idx
        self.integrated_imaging_pulse(self.data.apd, t=self.p.t_img_pulse, idx=self.idx)
        v = self.convert_measurement(self.data.apd.shot_data[idx])
        self.idx = self.idx + 1
        return v

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

        @kernel(flags={"fast-math"})
    def generate_posterior(self, k, t, do_it=True):
        # Running sums for posterior normalization and moments:
        #   P0_total = sum_j p_j
        #   mn       = sum_j p_j * omega_j
        #   moment_2 = sum_j p_j * omega_j^2
        P0_total = 0.
        moment_2 = 0.
        mn = 0.

        # Bring arrays into local references for kernel performance.
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
        alpha_z_lightshift = 2.0 * self.omega_z_lightshift * self.dt_z

        # In this experiment omega_guess_list is uniformly spaced (linspace in prepare).
        # That lets us update trigonometric phases recursively across j.
        if m > 1:
            domega = omega_guess_list[1] - omega_guess_list[0]
        else:
            domega = 0.0

        omega0 = omega_guess_list[0]

        # omega * t phase recursion across uniformly spaced omega grid.
        # This is the optimized equivalent of repeatedly evaluating:
        #   u_x ~ cos(omega * t), u_y ~ sin(omega * t)
        # from timing_test_0.py.
        (sin_wt, cos_wt) = self.sincos_lut_interp(omega0 * t)
        (sin_wt_step, cos_wt_step) = self.sincos_lut_interp(domega * t)

        # alpha_z = 2*dt*(omega_raman - omega) is uniformly spaced.
        # Add the extra z-rotation from light shift once as a constant offset:
        #   alpha_z_total = 2*dt*(omega_raman - omega) + omega_z_lightshift*dt_z
        # Folding this into initialization keeps loop cost unchanged.
        #   alpha_Z = 2 * dt * delta_omega
        #   R_z = [[cos(alpha_Z), sin(alpha_Z), 0],
        #          [-sin(alpha_Z), cos(alpha_Z), 0],
        #          [0,            0,            1]]
        (sin_z, cos_z) = self.sincos_lut_interp(two_dt * (omega_raman - omega0) - alpha_z_lightshift)
        (sin_z_step, cos_z_step) = self.sincos_lut_interp(-two_dt * domega)

        # Clamp observed photon count to valid [0, N] range.
        k_int = int(k)
        if k_int < 0:
            k_int = 0
        if k_int > n_photons:
            k_int = n_photons
        nk_int = n_photons - k_int

        j = 0
        while j < m:
            # Hypothesis frequency and detuning for this grid point.
            omega = omega_guess_list[j]
            delta_omega = omega_raman - omega

            # Hamiltonian rotation magnitude:
            # norm_H = sqrt(Omega^2 + delta_omega^2)
            # This matches timing_test_0.py's norm_H.
            norm_H = np.sqrt(Omega_sq + delta_omega * delta_omega)
            if norm_H > 0.0:
                inv_norm_H = 1.0 / norm_H
                Omega_over_H = Omega * inv_norm_H
                u_z = delta_omega * inv_norm_H

                # alpha_H = 2 * dt * norm_H in timing_test_0.py.
                # sin_H/cos_H drive Rodrigues rotation around axis u.
                (sin_H, cos_H) = self.sincos_lut_interp(two_dt * norm_H)
            else:
                Omega_over_H = 0.0
                u_z = 0.0
                sin_H = 0.0
                cos_H = 1.0

            # Current Bloch vector for this hypothesis.
            sx = state_x[j]
            sy = state_y[j]
            sz = state_z[j]

            # Rotation axis components u = (u_x, u_y, u_z).
            # u_x/u_y correspond to timing_test_0.py terms:
            #   u_x = (Omega/norm_H) * cos(omega*t)
            #   u_y = (Omega/norm_H) * sin(omega*t)
            u_x = Omega_over_H * cos_wt
            u_y = Omega_over_H * sin_wt

            one_minus_cos = 1.0 - cos_H

            # Precompute pairwise axis products used by expanded Rodrigues form.
            uxux = u_x * u_x
            uyuy = u_y * u_y
            uzuz = u_z * u_z
            uxuy = u_x * u_y
            uxuz = u_x * u_z
            uyuz = u_y * u_z

            # Apply R_H to state vector s=(sx,sy,sz) in expanded scalar form.
            # This is algebraically equivalent to timing_test_0.py:
            #   R_H = I + sin_H*K + (1-cos_H)*(K@K)
            #   h = R_H @ s
            hx = (cos_H + one_minus_cos * uxux) * sx
            hx += (one_minus_cos * uxuy - sin_H * u_z) * sy
            hx += (one_minus_cos * uxuz + sin_H * u_y) * sz

            hy = (one_minus_cos * uxuy + sin_H * u_z) * sx
            hy += (cos_H + one_minus_cos * uyuy) * sy
            hy += (one_minus_cos * uyuz - sin_H * u_x) * sz

            hz = (one_minus_cos * uxuz - sin_H * u_y) * sx
            hz += (one_minus_cos * uyuz + sin_H * u_x) * sy
            hz += (cos_H + one_minus_cos * uzuz) * sz

            # Apply R_z to h=(hx,hy,hz):
            #   [nx, ny]^T = [[cos_z, sin_z],[-sin_z, cos_z]] * [hx, hy]^T
            #   hz unchanged by z-rotation.
            # This matches timing_test_0.py's R = R_z @ R_H and state update.
            nx = cos_z * hx + sin_z * hy
            ny = -sin_z * hx + cos_z * hy
            if do_it:
                state_x[j] = nx
                state_y[j] = ny
                state_z[j] = hz

            # Measurement model:
            # p1 is the excited-state probability after evolution.
            # Posterior weight uses binomial-like factor:
            #   p_j <- p_j * p1^k * (1-p1)^(N-k)
            # same explicit formula used in timing_test_0.py.
            p1 = (hz + 1)/2
            q = 1.0 - p1
            p1_pow = self.powi(p1, k_int)
            q_pow = self.powi(q, nk_int)

            pj = P0[j] * p1_pow * q_pow

            #print('step', j, p1,q,p1_pow,q_pow, P0[j], 'probability', pj)

            P0_total += pj
            mn += pj * omega
            moment_2 += pj * omega_sq_list[j]

            # Store unnormalized posterior for next update cycle.
            if do_it:
                P0[j] = pj

            # Advance sin/cos states to next grid point with angle-addition.
            #   sin(a+b)=sin(a)cos(b)+cos(a)sin(b)
            #   cos(a+b)=cos(a)cos(b)-sin(a)sin(b)
            next_sin_wt = sin_wt * cos_wt_step + cos_wt * sin_wt_step
            next_cos_wt = cos_wt * cos_wt_step - sin_wt * sin_wt_step
            sin_wt = next_sin_wt
            cos_wt = next_cos_wt

            next_sin_z = sin_z * cos_z_step + cos_z * sin_z_step
            next_cos_z = cos_z * cos_z_step - sin_z * sin_z_step
            sin_z = next_sin_z
            cos_z = next_cos_z

            j += 1

        # Degenerate case: all weights underflowed/vanished.
        if P0_total <= 0.0:
            return self.omega_raman, 0.0

        # Normalize moments to obtain posterior mean and variance.
        mn = mn / P0_total
        moment_2 = moment_2 / P0_total
        
        if do_it:
            for i in range(len(P0)):
                P0[i] = P0[i] / P0_total
    
        self.P0_total = P0_total

        var = moment_2 - mn * mn
        if var < 0.0:
            var = 0.0
        std = np.sqrt(var)

        return mn, std
    
    @kernel
    def initialize_feedback(self):
        """Makes feedback go faster to run it once. Does not modify state or P0
        arrays.
        """    

        self.core.wait_until_mu(now_mu())
        (mn, std) = self.generate_posterior(10, 1.e-6, do_it=False)
        self.core.break_realtime()

        t0 = now_mu()
        self.core.wait_until_mu(t0)
        (mn, std) = self.generate_posterior(10, 1.e-6, do_it=False)
        self.t_posterior_mu = abs(t0 - self.core.get_rtio_counter_mu())
        self.core.break_realtime()

    @kernel(flags={"fast-math"})
    def sincos_lut_interp(self, x):
        # Map angle to [0, 2pi) so LUT indexing is stable.
        inv_two_pi = self.inv_two_pi
        two_pi = self.two_pi
        turns = int(x * inv_two_pi)
        x -= two_pi * turns
        if x < 0.0:
            x += two_pi

        # Linear interpolation between adjacent LUT samples.
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
        # This computes base**exp in O(log exp) multiplications.
        # It replaces O(exp) repeated multiplication loops from the naive form.
        result = 1.0
        b = base
        e = exp
        while e > 0:
            if (e & 1) != 0:
                result *= b
            b *= b
            e = e // 2
        return result