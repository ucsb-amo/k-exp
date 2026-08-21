from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=False,
                      imaging_type=img_types.ABSORPTION,
                      suppress_live_od=True)

        # goal: correct for imaging beam coupling changes before each shot

        # suppose some calibration to map lightshift to integrated voltage on APD (for
        # some predetermined time to get good SNR). Suppose target v_target
        # corresponds to a target lightshift.

        # call the integrated APD voltage v_apd for imaging beam on for
        # integration time t_apd.

        # we can then just check the integrated apd value and adjust the PID
        # setpoint to set v_apd = v_target

        # v_apd should be exceptionally linear in the imaging power PID setpoint.

        self.p.t_apd_imaging_check = 100.e-6

        self.p.N_max_iter = 50
        self.data.apd_check = self.data.add_data_container(2) # 2 points, one each for light + dark
        self.data.frac_err = self.data.add_data_container(self.p.N_max_iter)

        self.finish_prepare(shuffle=True)

    @kernel
    def lightshift_to_v_target(self, f_lightshift):
        # CALIBRATED -- values here are an example
        # 0.05 integrated voltage above background per 10 kHz light shift
        slope_v_apd_per_f_lightshift = 0.05 / 10.e3 
        offset_v_apd_per_f_lightshift = 0. # should be exactly 0

        m = slope_v_apd_per_f_lightshift
        y0 = offset_v_apd_per_f_lightshift
        
        return m * f_lightshift + y0

    @kernel
    def check_current_v_apd(self):
        # check current light level
        self.integrated_imaging_pulse(self.data.apd_check,
                                      t=self.p.t_apd_imaging_check,
                                      idx=0)
        delay(5.e-6)

        # dark image
        self.integrated_imaging_pulse(self.data.apd_check,
                                      t=self.p.t_apd_imaging_check,
                                      dark=True,
                                      idx=1)
        
        delay(5.e-6)
        
        v_light = self.data.apd_check.shot_data[0]
        v_dark = self.data.apd_check.shot_data[1]
        v_signal = v_light - v_dark
        return v_signal

    @kernel
    def jump_to_target(self, v_target):
        
        v_signal = self.check_current_v_apd()

        v_pid_current = self.imaging.dac_pid.v
        v_pid_target = v_pid_current * (v_target / v_signal)

        # self.imaging.set_power(v_pid_target)

    @kernel
    def feedback_check_pid_for_lightshift(self, v_target):
        p = -0.01

        i = 0
        N_MAX_ITER = self.p.N_max_iter

        while i < N_MAX_ITER:

            v_signal = self.check_current_v_apd()
            err = v_signal - v_target

            frac_err = abs(err / v_target)
            self.data.frac_err.put_data(frac_err, i=i)
            if frac_err < 0.01:
                aprint('target met, fractional error = ', frac_err)
                break
            else:
                aprint('step ', i, ': frac err =', frac_err)
                self.core.break_realtime()
                v_pid_current = self.imaging.dac_pid.v
                new_v_pid = p * err + v_pid_current
                self.imaging.set_power(new_v_pid)
                delay(1.e-3)
                i += 1

    @kernel
    def scan_kernel(self):

        # f_lightshift_target = 20.e3
        # v_target = self.lightshift_to_v_target(f_lightshift_target)
        v_target = 0.20
        self.jump_to_target(v_target)
        # v = self.check_current_v_apd()
        self.feedback_check_pid_for_lightshift(v_target)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False, setup_slm=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)