from artiq.experiment import *
from artiq.experiment import delay
from artiq.language import TFloat
from kexp import Base, cameras, img_types
import numpy as np

class imaging_apd_v_per_t_vs_amp(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION,
                      suppress_live_od=False)

        # goal: measure the background-subtracted integrated APD voltage per
        # unit imaging time, (v_light - v_dark) / t_img_pulse, versus the
        # imaging power setpoint amp_imaging.

        # no atoms are involved -- the APD sees the imaging beam directly, so
        # this is a pure imaging-beam power calibration.

        # the integrator model in kexp.calibrations.imaging.integrator_calibration
        # is v_signal = b + k_t * t + k_a * amp, so v_signal / t should be flat
        # in t_img_pulse and linear in amp_imaging. Scanning t as a second xvar
        # tests exactly that -- comment it out for a plain 1D scan vs amp.

        self.xvar('amp_imaging',np.linspace(0.05,0.5,16))
        self.p.amp_imaging = 0.25

        # self.xvar('t_img_pulse',np.array([50.e-6,100.e-6,200.e-6]))
        self.p.t_img_pulse = 100.e-6

        # amp_imaging steps between shots are large (and shuffled) compared to
        # the servo steps in imaging_apd_pid, so the PID integrator is cleared
        # on each set_power and given room to re-acquire before we integrate.
        # CHECK ON A SCOPE that the beam has actually settled within this time.
        self.p.t_pid_settle = 20.e-3

        self.p.N_repeats = 50

        self.data.v_light = self.data.add_data_container(1)
        self.data.v_dark = self.data.add_data_container(1)
        self.data.v_signal = self.data.add_data_container(1)
        self.data.v_per_t = self.data.add_data_container(1)

        self.finish_prepare(shuffle=True)

    @kernel
    def measure_v_signal(self, t) -> TFloat:
        """One light/dark pair at imaging pulse length t. Returns v_light -
        v_dark.

        Both windows use reset=True so each integration starts from a genuinely
        reset integrator -- that is what makes the dark window a valid
        subtraction for the amplifier offset rather than for whatever charge the
        previous window happened to leave behind. measure_integrated_v re-arms
        t_apd_slack after each blocking sampler read, so the two calls can run
        back to back without starving the second pretrigger.
        """
        v_light = self.imaging.measure_integrated_v(t, reset=True)
        v_dark = self.imaging.measure_integrated_v(t, dark=True, reset=True)

        self.data.v_light.put_data(v_light)
        self.data.v_dark.put_data(v_dark)

        return v_light - v_dark

    @kernel
    def scan_kernel(self):

        # reset_devices (via init_scan_kernel) puts the detuning and power back
        # to the camera_params defaults every shot, so both have to be set here.
        # Detuning is pinned to the high-field imaging point the APD absorption
        # imaging actually runs at, since imaging AOM efficiency -- and so the
        # amp -> power map being calibrated here -- depends on drive frequency.
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging, reset_pid=True)
        delay(self.p.t_pid_settle)

        t = self.p.t_img_pulse
        v_signal = self.measure_v_signal(t)

        self.data.v_signal.put_data(v_signal)
        self.data.v_per_t.put_data(v_signal / t)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False, setup_slm=False)
        self.scan()

    def analyze(self):
        import os
        import matplotlib.pyplot as plt

        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

        # This runs before the saved file is reloaded, so pull the data straight
        # from the in-memory run arrays. (The saved run is what
        # lightshift_vs_integrated_apd_voltage.ipynb consumes -- keep
        # suppress_live_od=False or there will be no run ID to give it.)
        #
        # scan_xvars[i].values is the actual per-shot value list for axis i of
        # _run_data (already repeated and shuffled), so using it as the axis
        # coordinate keeps everything aligned without un-shuffling by hand.
        amp = np.asarray(self.scan_xvars[0].values, dtype=float)
        v_per_t = np.asarray(self.data.v_per_t._run_data, dtype=float)
        v_dark = np.asarray(self.data.v_dark._run_data, dtype=float)

        if v_per_t.ndim == 1:
            # single t_img_pulse (t xvar commented out)
            v_per_t = v_per_t[:,None]
            t_vals = np.array([self.p.t_img_pulse])
        else:
            t_vals = np.asarray(self.scan_xvars[1].values, dtype=float)

        amp_unique = np.unique(amp)
        N_t = v_per_t.shape[1]

        mean = np.zeros((len(amp_unique), N_t))
        sem = np.zeros((len(amp_unique), N_t))
        for i, a in enumerate(amp_unique):
            sel = (amp == a)
            mean[i] = v_per_t[sel].mean(axis=0)
            sem[i] = v_per_t[sel].std(axis=0) / np.sqrt(sel.sum())

        print(f"mean dark (background) voltage = {v_dark.mean():.5f} V "
              f"(std {v_dark.std():.5f} V)")

        fig, ax = plt.subplots(figsize=(6,4.5))

        for j in range(N_t):
            t = t_vals[j]
            slope, intercept = np.polyfit(amp_unique, mean[:,j], 1)
            print(f"t_img_pulse = {t*1e6:7.1f} us:  "
                  f"v_signal/t = {slope:.4g} * amp_imaging + {intercept:.4g}  [V/s]")
            ax.errorbar(amp_unique, mean[:,j], yerr=sem[:,j],
                        fmt='o', ms=4, capsize=2,
                        label=f'{t*1e6:.0f} $\\mu$s')
            ax.plot(amp_unique, slope*amp_unique + intercept, '-', lw=1, alpha=0.6)

        ax.set_xlabel('amp_imaging')
        ax.set_ylabel('$(v_{light} - v_{dark})\\,/\\,t_{img}$ (V/s)')
        ax.set_title('background-subtracted APD voltage per imaging time')
        if N_t > 1:
            ax.legend(title='$t_{img}$')

        fig.tight_layout()
        plt.show()
