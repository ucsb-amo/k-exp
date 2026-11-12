
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel, now_mu, at_mu
from kexp import Base, img_types, cameras
from kexp.calibrations.imaging import high_field_imaging_detuning


class hf_bec_rydberg_hole_burn(EnvExperiment, Base):
    """hf_bec_rydberg_scan with a hole-burn frequency toggle on the 405 switch AO.

    While both Rydberg beams are on (t_tweezer_hold), the ry_405_sw DDS
    frequency alternates every t_ry_405_burn:

        burn center -> burn center + burn shift -> burn center -> ...

    starting at the burn center when the beams turn on. The last segment is
    cut off at the end of the hold. t_ry_405_burn <= 0 (or a zero shift)
    holds at the burn center for the whole hold. After the hold the DDS goes
    back to its default frequency.

    Each jump is a DDS SPI write (a few us of dead time per write), placed on
    an absolute timeline so the burn period does not drift. Keep
    t_ry_405_burn well above ~50 us so the kernel CPU stays ahead of the
    timeline (RTIO underflow otherwise).
    """

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('t_tof',np.linspace(20.,3000.,7)*1.e-6)
        self.p.t_tof = 2300.e-6

        # self.xvar('do_405_pulse',[0,1])
        self.p.do_405_pulse = 1
        # self.xvar('do_980_pulse',[0,1])
        self.p.do_980_pulse = 1
        self.p.amp_dds_405 = 0.06

        # hole burn: ry_405_sw DDS toggles between the center and center + shift
        # self.xvar('frequency_ry_405_ao_burn_line', np.linspace(130.,140.,6)*1.e6)
        self.p.frequency_ry_405_ao_burn_line = ((280.e6) / 2)
        # self.xvar('frequency_ry_405_ao_burn_shift', np.linspace(0.,10.,6)*1.e6)
        self.p.frequency_ry_405_ao_burn_shift = 0.e6
        # self.xvar('frequency_ry_405_ao_ao_burn_line', [135*1.e6,140.*1.e6])
        self.xvar('frequency_ry_405_ao_burn_shift', np.linspace(-5.,5.,50)*(1.e6)) # double for actual frequency
        # self.xvar('t_ry_405_burn', np.linspace(100.,1000.,5)*1.e-6)
        self.p.t_ry_405_burn = 500.e-6

        # self.xvar('compress',[0,1])
        self.p.compress = 0

        # outer coil during the Rydberg hold, PID on (prepare_hf_tweezers magnet_PID=True default)
        self.p.i_hf_raman = 176.4

        # imaging F=1 mF=-1: -568 MHz measured at 182 A, PID imaging slope -4.0935 MHz/A
        # (calibrations/imaging.py, PID fit valid 174-182 A) -> -545.1 MHz at 176.4 A
        self.p.frequency_detuned_hf_f1m1 = -568.e6 - 4.0935e6 * (self.p.i_hf_raman - 182.)

        # 980 EO: 418.7 MHz at 182 A, Rydberg line slope -2.35 MHz/A vs PID set point
        # (measured 182-192 A, 2026-11-04) -> 431.9 MHz at 176.4 A, EXTRAPOLATED 5.6 A below the data
        # self.xvar('frequency_eo_980', np.linspace(410.,440.,10)*1.e6)
        self.p.frequency_eo_980 = 434.56e6 # to make dimer peak center of the 405 scan range
        # self.xvar('frequency_eo_980', 418.1e6 + 1e6*np.linspace(-1,1,3))

        # self.xvar('t_tweezer_paint_rampdown',np.linspace(0.0,10.,5)*1.e-3)

        # self.xvar('t_tweezer_hold', np.linspace(0.0, 800.0, 7) * 1.e-3)
        self.p.t_tweezer_hold = 512.e-3

        # self.p.v_pd_hf_tweezer_1064_rampdown3_end=3.5
        self.p.hf_imaging_detuning = self.p.frequency_detuned_hf_f1m1 # not read by the sequence; kept in step
        self.p.v_pd_ry_405 = 0.45
        self.p.v_pd_ry_980 = 2.8

        self.p.N_repeats = 9
        self.finish_prepare(shuffle=True)

        if self.p.do_405_pulse == 1:
            print(f'doing 405 pulse')
        else:
            print(f'not doing 405 pulse')
        if self.p.do_980_pulse == 1:
            print(f'doing 980 pulse')
        else:
            print(f'not doing 980 pulse')

    @kernel
    def burn_hold(self):
        """Hold for t_tweezer_hold, toggling the ry_405_sw DDS frequency
        between the burn center and center + shift every t_ry_405_burn."""
        t_start = now_mu()
        t_end = t_start + self.core.seconds_to_mu(self.p.t_tweezer_hold)
        t_burn_mu = self.core.seconds_to_mu(self.p.t_ry_405_burn)

        f_center = self.p.frequency_ry_405_ao_burn_line
        f_shifted = self.p.frequency_ry_405_ao_burn_line + self.p.frequency_ry_405_ao_burn_shift

        if t_burn_mu > 0:
            t_next = t_start + t_burn_mu
            at_shifted = False
            while t_next < t_end:
                at_mu(t_next)
                if at_shifted:
                    self.ry_405.dds_sw.set_dds(frequency=f_center)
                else:
                    self.ry_405.dds_sw.set_dds(frequency=f_shifted)
                at_shifted = not at_shifted
                t_next += t_burn_mu

        # a write that ran past t_end ends the hold where it finished
        if now_mu() < t_end:
            at_mu(t_end)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)

        self.ry_405.set_power(self.p.v_pd_ry_405)
        self.ry_980.set_power(self.p.v_pd_ry_980)
        self.ttl.ry_intensity_pid_clear.pulse(10.e-6)

        if self.p.compress:
            self.p.t_tof = 450.e-6
        # if self.p.do_980_pulse == 1:
        self.ry_980.sweep_to(self.p.frequency_eo_980)

        # self.ry_980.set_power(9.9)

        # if self.p.compress:
        #     self.prepare_hf_tweezers(squeeze=True)
        # else:
        self.prepare_hf_tweezers(squeeze=False, do_tweezer_evap_2=True)

        if self.p.do_405_pulse == 1:
            self.ry_405.reboot()
            self.ry_405.dds_sw.set_dds(frequency=self.p.frequency_ry_405_ao_burn_line,
                                       amplitude=self.p.amp_dds_405)
            self.ry_405.on()
        if self.p.do_980_pulse == 1:
            self.ry_980.on()

        self.burn_hold()

        self.ry_405.off()
        self.ry_980.off()
        self.ry_405.ttl_shutter.off()
        self.ry_405.dds_sw.set_dds(frequency=self.ry_405.dds_sw._frequency_default)

        delay(40e-3)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
