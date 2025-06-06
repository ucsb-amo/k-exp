from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class calibrate_hf_image_detuning(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)

        self.p.t_tof = 5.e-6
        # self.xvar('t_tof',np.linspace(100,900.,10)*1.e-6)
        # self.xvar('dumy',[0]*500)
        
        self.p.t_lightsheet_hold = 0.1

        self.xvar('i_lf_current', np.linspace(12.,20.,10))
        self.p.i_lf_current = 20.

        self.xvar('lf_imaging_detuning', np.arange(270.,360.,6.)*1.e6)
        # self.p.lf_imaging_detuning = 294.e6

        # self.p.amp_imaging = .12
        self.p.imaging_state = 2.

        # self.p.N_repeats = 1
        self.p.t_mot_load = .5

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.lf_imaging_detuning)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        # self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.set_shims(v_zshim_current=0.,
                        v_yshim_current=0.,
                        v_xshim_current=0.)

        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_lf_current)

        delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
