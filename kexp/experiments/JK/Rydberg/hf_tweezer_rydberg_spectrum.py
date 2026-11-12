
# Tweezer-BEC Rydberg spectrum (45S main line + molecular lines), 176.4 A WITH outer-coil PID.
# Copied 2026-11-10 from the queued run file
#   C:/lab/skynet_log/outputs/2026-11-06_17-30_rydberg_field2/runs/L1764v2/L1764v2_00.py
# (the 176.4 A spectrum runs from 94151 on used these settings; the ref182 / imaging-check runs between them did not). Only the scan list differs: the queued files each scan a 24-25 point
# shuffled chunk of the 423.5-450.7 MHz x 0.1 MHz grid; here the whole grid is one scan (273 shots, ~25 min).
# Sequence = HF_experiments/Rydberg/hf_bec_rydberg_scan.py (sha256 4f40f8f2c0d5) scan_kernel, do_tweezer_evap_2=True.
# Main line at 176.4 A: 431.96 MHz on the 980 EO (k-jam/jk/rydberg_calcs/ry_line_vs_current.ipynb).
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras
from kexp.calibrations.imaging import high_field_imaging_detuning
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2, tweezer_vpd2_to_vpd1, tweezer_vpd2_to_vpd1_squeezer


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=3)

        self.p.i_hf_raman = 176.4
        self.p.frequency_detuned_hf_f1m1 = -544010000.0

        self.p.t_tof = 0.001325
        self.p.do_405_pulse = 1
        self.p.do_980_pulse = 1
        self.xvar('do_980_pulse',[0,1])
        self.p.amp_dds_405 = 0.06
        self.p.compress = 0
        # self.p.frequency_eo_980 = 437100000.0
        self.p.t_tweezer_hold = 0.3
        self.p.hf_imaging_detuning = -568.e6
        self.p.v_pd_ry_405 = 0.45
        self.p.v_pd_ry_980 = 1.0

        # self.xvar('frequency_eo_980', np.round(np.arange(423.5, 450.75, 0.1), 1) * 1.e6)
        self.p.frequency_eo_980=431.957*1.e6

        self.p.N_repeats = 4
        self.finish_prepare(shuffle=True)

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
            self.ry_405.dds_sw.set_dds(amplitude=self.p.amp_dds_405)
            self.ry_405.on()
        if self.p.do_980_pulse == 1:
            self.ry_980.on()
        
    

        delay(self.p.t_tweezer_hold)

        self.ry_405.off()
        self.ry_980.off()
        self.ry_405.ttl_shutter.off()

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
