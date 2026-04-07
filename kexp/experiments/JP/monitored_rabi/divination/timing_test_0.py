from artiq.experiment import *
from artiq.language import now_mu, at_mu
import numpy as np

class timing_test(EnvExperiment):
    kernel_invariants = {
                        "m",
                        "Omega",
                        "dt",
                        "N_photons_per_shot"}

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

        self.omega_raman = omega_guess # omega_ctrl
        
        self.dt = 2.e-6 # drive pulse length per step

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
        
        delay(500.e-3)
        # print(slack0, slack1)
        print(slack1)

    @kernel(flags={"fast-math"})
    def generate_posterior(self, k, t):
        P0_total = 0.
        p1 = 0.
        moment_2 = 0.
        mn = 0.
        std = 0.
        sin_H = 0.
        cos_H = 0.

        I = np.array([[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
        R_z = np.array([[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
        K = np.array([[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
        R_H = np.array([[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
        R = np.array([[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])

        for j in range(self.m):
            omega = self.omega_guess_list[j]
            delta_omega = self.omega_raman - omega

            phase = self.dt * delta_omega
            alpha_Z = 2.0 * phase
            cos_z = np.sin(np.pi/2 - alpha_Z)
            sin_z = np.sin(alpha_Z)

            R_z = np.array([[cos_z,sin_z, 0.],
                            [-sin_z, cos_z, 0.],
                            [0., 0., 1.]])

            norm_H = np.sqrt(self.Omega*self.Omega + delta_omega*delta_omega)
            if norm_H != 0.:
                alpha_H = 2.0 * norm_H * self.dt
                cos_H = np.sin(np.pi/2 - alpha_H)
                sin_H = np.sin(alpha_H)

                Omega_over_H = self.Omega / norm_H

                u_x = Omega_over_H * np.sin(np.pi/2 - omega * t) 
                u_y = Omega_over_H * np.sin(omega * t)
                u_z = delta_omega / norm_H

                K = np.array([[0.0,-u_z, u_y],
                            [u_z, 0.0, -u_x],
                            [-u_y, u_x, 0.0]])

                R_H = I + sin_H * K + (1.0 - cos_H) * (K @ K)

            R = R_z @ R_H 

            for i in range(3):
                self.state_list[j][i] = R[i] @ self.state_list[j]
            
            p1 = self.state_list[j][2]
            pj = self.P0[j] * (p1**k) * ((1.0 - p1)**(self.N_photons_per_shot-k))

            P0_total += pj
            mn += pj * omega
            moment_2 += pj * omega**2

            self.P0[j] = pj

        mn = mn / P0_total
        moment_2 = moment_2 / P0_total

        std = np.sqrt(moment_2 - mn*mn)

        return mn, std