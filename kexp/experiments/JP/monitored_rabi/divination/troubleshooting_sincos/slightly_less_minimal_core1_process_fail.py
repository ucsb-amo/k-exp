from artiq.experiment import *
from artiq.experiment import delay
import numpy as np

class core1_fail(EnvExperiment):

    def prepare(self):
        self.core = self.get_device('core')

        self.m = 21
        self.P0 = np.ones(self.m)
        self.P0 = self.P0 / np.sum(self.P0)

        Omega_guess = 2*np.pi*80.e3
        self.Omega = 2*np.pi*80.e3
        offset = 5
        self.Omega_guess_list = Omega_guess + 2*offset*self.Omega*np.linspace(-1,1,self.m)

        self.dt = 2.e-6
        self.N_pulses = 8 # nu


        self.N_photons_per_shot = 10
        self.v_apd_all_up = -1.5
        self.v_apd_all_down = -1.0
        self.v_range = self.v_apd_all_up - self.v_apd_all_down

        self.omega_raman = 2*np.pi*147.e6 # omega_ctrl

        self.state_list = np.zeros((self.m,3))
        self.state_list[:,2] = 1.

    @kernel
    def run(self):
        (mn, std) = self.generate_posterior(0.1*100, 1.e-6)

    @kernel
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
            omega = self.Omega_guess_list[j]
            delta_omega = self.omega_raman - omega

            phase = self.dt * delta_omega
            alpha_Z = 2.0 * phase
            cos_z = np.sin(np.pi/2 - alpha_Z)
            sin_z = np.sin(alpha_Z)

            R_z = np.array([[cos_z,sin_z, 0.],
                            [-sin_z, cos_z, 0.],
                            [0., 0., 1.]])

            norm_H = np.sqrt(self.Omega**2 + delta_omega**2)
            if norm_H != 0.:
                alpha_H = 2.0 * norm_H * self.dt
                cos_H = np.sin(np.pi/2 - alpha_H)
                sin_H = np.sin(alpha_H)

                u_x = (self.Omega * np.sin(np.pi/2 - omega * t)) / norm_H
                u_y = (self.Omega * np.sin(omega * t)) / norm_H
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

        std = np.sqrt(moment_2 - mn**2)

        return mn, std
