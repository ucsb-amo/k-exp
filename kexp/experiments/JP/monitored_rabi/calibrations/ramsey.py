from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class ramsey(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('frequency_raman_transition', 147.2521e6 + np.linspace(-2.,2,5)*1.e3)
        # self.xvar('frequency_raman_transition', self.p.frequency_raman_transition + np.arange(-20.,20.,1.)*1.e3)
        self.xvar('frequency_raman_transition', self.p.frequency_raman_transition + np.linspace(-3.,3.,7)*1.e3)
        self.xvar('t_ramsey',np.linspace(0.,100.,5)*1.e-6)
        # self.p.t_ramsey = 40.e-6

        self.p.t_tof = 10.e-6
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # set up weak measurement
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.camera_params.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        self.raman.pulse(self.p.t_raman_pi_pulse/2)
        delay(self.p.t_ramsey)
        self.raman.pulse(self.p.t_raman_pi_pulse/2)

        self.ttl.raman_shutter.off()

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

        self.ramsey_analysis()

    def ramsey_analysis(self):
        from scipy.optimize import curve_fit
        from waxa import atomdata
        import matplotlib.pyplot as plt
        from waxa.plotting import detect_unit, mixOD_grid

        ad = atomdata(self.run_info.run_id,'tweezy')

        xvarunit0, xvarmult0, xvarname0 = detect_unit(ad, 0, xvarunit="", xvarmult=1.)
        xvarunit1, xvarmult1, xvarname1 = detect_unit(ad, 1, xvarunit="", xvarmult=1.)
        mixOD_grid(ad,
            xvar0unit=xvarunit0,
            xvar1unit=xvarunit1,
            xvar0mult=xvarmult0,
            xvar1mult=xvarmult1,
            xvar0format='1.4f',
            xvar1format='1.2f',
            max_od=2.5,
            figsize=(8,8),
            aspect='auto')
        plt.show(block=False)

        # Identify axes
        xnames = [str(n) for n in ad.xvarnames]
        i_t = next(i for i, n in enumerate(xnames) if "t_ramsey" in n)
        i_f = next(i for i, n in enumerate(xnames) if "frequency_raman_transition" in n)

        # Sum atom number over t_ramsey -> signal vs frequency_raman_transition
        atom = np.asarray(ad.atom_number, dtype=float)
        summed_atom_number = np.nansum(atom, axis=i_t)
        freq = np.asarray(ad.xvars[i_f], dtype=float)

        # Ensure 1D and sorted by frequency for fitting/plotting
        freq = freq.ravel()
        summed_atom_number = np.asarray(summed_atom_number).ravel()
        order = np.argsort(freq)
        freq = freq[order]
        summed_atom_number = summed_atom_number[order]

        # Fit a Gaussian to negative summed signal (darkest image -> largest negative dip)
        yfit = -summed_atom_number

        def gauss(x, A, x0, sigma, C):
            return A * np.exp(-0.5 * ((x - x0) / sigma) ** 2) + C

        A0 = np.nanmax(yfit) - np.nanmin(yfit)
        x0_0 = freq[np.nanargmax(yfit)]
        sigma0 = 0.2 * (np.nanmax(freq) - np.nanmin(freq)) if len(freq) > 1 else 1.0
        C0 = np.nanmin(yfit)

        p0 = [A0, x0_0, sigma0, C0]
        bounds = ([0, np.nanmin(freq), 0, -np.inf], [np.inf, np.nanmax(freq), np.inf, np.inf])

        popt, pcov = curve_fit(gauss, freq, yfit, p0=p0, bounds=bounds, maxfev=20000)
        A, x0, sigma, C = popt

        print(f"Darkest frequency (Gaussian center):\nself.frequency_raman_transition = {x0/1.e6:.4f}e6 #{ad.run_info.run_id}")
        # print(f"Gaussian sigma: {abs(sigma):.6g}")

        # Plot
        xf = np.linspace(np.nanmin(freq), np.nanmax(freq), 500)
        plt.figure(figsize=(6, 4))
        plt.plot(freq, yfit, "o", label="- summed atom number")
        plt.plot(xf, gauss(xf, *popt), "-", label="Gaussian fit")
        plt.axvline(x0, color="r", ls="--", label=f"darkest @ {x0:.6g}")
        plt.xlabel("frequency_raman_transition")
        plt.ylabel("- sum over t_ramsey of ad.atom_number")
        plt.title(f"Run {ad.run_info.run_id}: darkest-frequency fit")
        plt.legend()
        plt.tight_layout()
        plt.show(block=False)