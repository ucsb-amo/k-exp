from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

import spcm

class tweezer_snug(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,camera_select='andor',save_data=False)

        # self.xvar('t_tweezer_mod',np.linspace(3.,500.,20)*1.e-3)
        self.p.t_tweezer_mod = 110.e-3

        self.xvar('f_tweezer_mod',np.linspace(100.,100.,1))

        # self.p.f_tweezer_mod = 100.

        self.p.x_tweezer_mod_amp = 1.e-6

        # self.p.frequency_tweezer_list = [73.15e6,77.e6]
        # a_list = [.0,.5]

        # self.slopes = np.zeros((100000,),float)
        # self.p.N = 2500
        # self.xvar('N',range(2500,50000,2500))

        self.finish_prepare(shuffle=False)

    # @rpc(flags={"async"})
    # def write_move(self):
    #     """Writes the slopes list to the AWG at update interval dt.

    #     Args:
    #         slopes (ndarray): The list of frequency slopes (Hz/s) to be written
    #         to the awg.
    #     """
    #     dt = self.p.t_tweezer_movement_dt

    #     self.tweezer.dds.trg_src(spcm.SPCM_DDS_TRG_SRC_TIMER)
    #     self.tweezer.dds.trg_timer(dt)
    #     self.tweezer.dds.exec_at_trg()
    #     self.tweezer.dds.write()

    #     self.slopes[self.p.N - 1] = self.tweezer.dds.avail_freq_slope_min() - 1000
    #     aprint(self.p.N,self.slopes[(self.p.N-1)])

    #     for slope in self.slopes[0:self.p.N]:
    #         self.tweezer.dds.frequency_slope(1,slope)
    #         self.tweezer.dds.exec_at_trg()
    #     self.tweezer.dds.write()

    #     self.tweezer.dds.trg_src(spcm.SPCM_DDS_TRG_SRC_CARD)
    #     self.tweezer.dds.exec_at_trg()
    #     self.tweezer.dds.write()

    @kernel
    def scan_kernel(self):

        self.tweezer.traps[1].sine_move(t_mod=self.p.t_tweezer_mod,x_mod=self.p.x_tweezer_mod_amp,f_mod=self.p.f_tweezer_mod,trigger=False)
        aprint(self.p.f_tweezer_mod)
        delay(200.e-3)

        # self.core.wait_until_mu(now_mu())
        # self.write_move()
        # delay(200.e-3)

        self.tweezer.trigger()
        delay(self.p.t_tweezer_mod)

        self.tweezer.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)