from artiq.experiment import *
from artiq.language import delay, delay_mu, now_mu, at_mu
from kexp import Base, aprint
import numpy as np
from numpy import int32, int64

class mot_killa(EnvExperiment, Base):

    @portable
    def f_to_ftw(self, f) -> np.int32:
        return self.dds.dds_lo.dds_device.frequency_to_ftw(f)
    
    @portable
    def ftw_to_f(self, ftw) -> float:
        return self.dds.dds_lo.dds_device.ftw_to_frequency(ftw)

    def prepare(self):
        Base.__init__(self,
                      setup_camera=False,
                      save_data=False,
                      suppress_live_od=True)
        
        self.p.df_requested = 50.e3

        self.p.dt_u = np.int64(91)
        self.p.dt_i = np.int64(10000)

        self.p.dftw = int32(0)
        self.p.df = 0.
        self.p.T_beat_mu = int64(0)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        t0 = now_mu()

        self.dds.dds_lo.set_phase_mode(1)
        delay(1.e-3)
        self.prep_raman(phase_mode=1, t_phase_origin_mu=t0)
        delay(1.e-3)
        self.dds.dds_lo.set_dds(phase=0.5,t_phase_origin_mu=t0)
        delay(1.e-3)

        ftw = self.raman.dds0._ftw - self.raman.dds1._ftw
        if ftw < 0: ftw = -ftw
        self.dds.dds_lo.set_frequency_mu(ftw=ftw)

        self.dds.dds_lo.on()

        aprint(self.ftw_to_f(self.raman.dds0._ftw - self.raman.dds1._ftw))
        FTW = (self.raman.dds0._ftw - self.raman.dds1._ftw)*2
        aprint(self.ftw_to_f(FTW))
        # self.raman.set_frequency_fast_dumb(frequency_transition=self.ftw_to_f(FTW))
        # aprint((self.raman.dds0._ftw + self.raman.dds1._ftw)*2)

        # self.raman.set_up_fast_frequency_update(0)
        # self.raman.set_frequency_fast(frequency_transition=self.raman.frequency_transition + self.p.df_requested,
        #                               do_io_update=False)
        
        # aprint(self.raman.dds0._ftw - self.raman.dds1._ftw)

        # self.p.dftw = self.raman.dds0._ftw - self.raman.dds1._ftw
        # self.p.df = self.ftw_to_f(self.p.dftw)

        # self.p.T_beat_mu = np.int64(1/self.p.df * 1.e9)

        # t = now_mu()

        # self.raman.io_update()
        # aprint(self.raman.dds0._ftw - self.raman.dds1._ftw)
        
        # self.raman.clean_up_fast_frequency_update()

        # self.raman._configure_ffua_profile()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)