from artiq.experiment import *
from artiq.language import now_mu, at_mu, delay
from kexp import Base, img_types, cameras
import numpy as np

class sigma_z(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)
        
        self.p.amp_imaging = 0.4
        self.xvar('amp_imaging', np.linspace(0.2, 1., 5))

        self.p.t_pci_pulse = 6.e-6
        # self.xvar('t_pci_pulse', np.linspace(3., 10., 5)*1.e-6)
        
        self.p.t_raman_pulse = 0.
        self.xvar('t_raman_pulse', self.p.t_raman_pi_pulse * np.linspace(0.,1.,2))

        self.p.t_tweezer_hold = 20.e-3
        self.p.t_tof = 20.e-6
        self.p.N_repeats = 10

        self.p.N_pulses = 10

        self.data.apd = self.data.add_data_container(self.p.N_pulses)

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)
        
        self.finish_prepare()

    @kernel
    def scan_kernel(self):
        self.integrator.init()

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        self.ttl.pd_scope_trig3.pulse(1.e-6)

        self.raman.pulse(self.p.t_raman_pulse)

        delay(2.e-6)

        for i in range(self.p.N_pulses):
            self.integrated_imaging_pulse(self.data.apd, t=self.p.t_pci_pulse, idx=i)
            delay(self.p.t_pci_pulse)

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep(0)
        self.core.break_realtime()
        delay(30.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

        from waxa import atomdata
        ad = atomdata(0,'tweezy')

        # Mean APD over all pulses, grouped by xvar value (mean ± SEM)

        apd_2d = np.asarray(ad.data.apd)           # shape: (n_repeats, n_pulses)
        xvals = np.asarray(ad.xvars[0]).ravel()    # shape: (n_repeats,)

        if apd_2d.ndim != 2:
            raise ValueError(f"Expected ad.data.apd to be 2D, got shape {apd_2d.shape}")
        if xvals.shape[0] != apd_2d.shape[0]:
            raise ValueError(f"len(xvals)={xvals.shape[0]} does not match repeats={apd_2d.shape[0]}")

        # Flatten APD so each pulse contributes; repeat xvar for each pulse
        apd_all = apd_2d.reshape(-1)
        x_all = np.repeat(xvals, apd_2d.shape[1])

        # Keep first-appearance order of xvar values
        x_unique, first_idx = np.unique(x_all, return_index=True)
        x_unique = x_unique[np.argsort(first_idx)]

        mean_apd = np.zeros_like(x_unique, dtype=float)
        sem_apd = np.zeros_like(x_unique, dtype=float)

        for i, xv in enumerate(x_unique):
            m = np.isclose(x_all, xv, rtol=0, atol=1e-15)
            vals = apd_all[m]
            mean_apd[i] = np.mean(vals)
            sem_apd[i] = np.std(vals, ddof=1) / np.sqrt(vals.size) if vals.size > 1 else 0.0

        from waxa.plotting import detect_unit
        xvarunit, xvarmult, xvarname = detect_unit(ad, 0)

        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.errorbar(
            x_unique * xvarmult / (ad.p.t_raman_pi_pulse * 1.e6),
            mean_apd,
            yerr=sem_apd,
            fmt="o-",
            capsize=4,
            lw=1.2
        )
        ax.set_xlabel(f"{xvarname} ($\pi$)")
        ax.set_ylabel("Mean APD voltage (V)")
        ax.set_title(f"Run {ad.run_info.run_id}: mean APD (all pulses) vs {xvarname}")
        ax.grid(alpha=0.3)
        plt.tight_layout()
        plt.show()

        print(mean_apd[0], mean_apd[-1])