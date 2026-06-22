from artiq.experiment import *
from artiq.language import delay, delay_mu, now_mu, at_mu
from kexp import Base, aprint
import numpy as np
from numpy import int32, int64

from waxx.control.artiq import DDS

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
        
        self.p.df_requested = 250.e3

        self.p.dt_u = np.int64(91)
        self.p.dt_i = np.int64(0)
        # self.xvar('dt_i', np.linspace(685,705,5).astype(np.int64))
        # self.xvar('dt_i', np.linspace(-100,100,21).astype(np.int64))

        self.p.dftw = int32(0)
        self.p.df = 0.
        self.p.T_beat_mu = int64(0)

        self.p.n_T = 2

        # self.p.relphase = 0.56*np.pi
        self.p.relphase = np.pi * (0.25/0.56)
        # self.xvar('relphase',np.linspace(0.,1.,11)*np.pi)

        self.data.v = self.data.add_data_container(2)

        self.p.N_repeats = 1

        self.p.n_sampler_avg = 300
        self.p.t_sampler_sample_rate = 500.e-6

        self.finish_prepare(shuffle=True)

    @kernel
    def clear_phase_accumulators(self):

        self.dds.dds_lo.clear_phase_accumulator()
        self.raman.dds0.clear_phase_accumulator()
        self.raman.dds1.clear_phase_accumulator()

    @kernel
    def set_lo_raman_match(self):
        ftw = self.raman.dds0._ftw - self.raman.dds1._ftw
        if ftw < 0: ftw = -ftw
        self.dds.dds_lo.set_frequency_mu(ftw=ftw)

    @kernel
    def initial_dds_setup(self):

        self.dds.dds_lo.init()
        delay_mu(1000000)
        self.raman.dds0.init()
        delay_mu(1000000)
        self.raman.dds1.init()
        delay_mu(1000000)

        # self.raman.dds1.

        self.dds.dds_lo.set_phase_mode(0)
        delay(1.e-3)
        self.prep_raman(phase_mode=0,
                        relative_phase=0.)
        delay(1.e-3)
        self.dds.dds_lo.set_dds(phase=self.p.relphase, init=True)
        delay(1.e-3)
        self.dds.dds_lo.on()

    @kernel
    def sample(self,idx):
        v = 0.
        n = self.p.n_sampler_avg
        for _ in range(n):
            self.sampler.sample()
            v += self.sampler.data[0]
            delay(self.p.t_sampler_sample_rate)
        self.data.v.put_data(v / n, idx)
        delay(10.e-3)

    @kernel
    def scan_kernel(self):
        # pass

        self.initial_dds_setup()
        self.set_lo_raman_match()
        self.clear_phase_accumulators()

        self.raman.set_up_fast_frequency_update(1)

        delay(100.e-3)

        self.sample(0)

        delay(10.e-3)

        # Work in integer FTW space: capture the exact current dds0 word, apply
        # one explicit integer step, and write raw FTW. The saved word is written
        # back verbatim for a bit-exact return (no SI round-trip rounding).
        ftw0_old = self.raman.dds0._ftw
        dftw0 = self.f_to_ftw(self.p.df_requested)   # int32 step for dds0 (only rounding)
        ftw0_new = int32(ftw0_old + dftw0)

        # T_beat_mu = n_T periods of the raman-vs-LO beat (FTW = dftw0), exact
        # integer math (ref_period cancels via sysclk_per_mu). Round to nearest mu.
        spm = self.raman._sysclk_per_mu
        num = self.p.n_T * (int64(1) << 32)
        den = int64(dftw0) * int64(spm)
        self.p.T_beat_mu = int64((num + den // 2) // den)

        # aprint(self.ftw_to_f(2*(ftw0_new - self.raman.dds1._ftw)))

        # queue up frequency change but don't pulse io update yet
        self.raman.set_ftw_fast(ftw0_new, do_io_update=False)

        delay(10.e-3)

        at_mu(now_mu() & ~7)

        # pulse io update to apply last queued frequency change
        t = self.raman.io_update()
        at_mu(t)

        delay_mu(self.p.dt_u)
        t = now_mu()
        # frequency should update here
        
        self.trig()

        # queue up the next update
        self.raman.stage_ffua()
        self.raman.set_ftw_fast(ftw0_old, do_io_update=False)

        # pretrigger the update by dt_u so that total on interval is T_beat_mu
        at_mu(t + self.p.T_beat_mu - self.p.dt_u + self.p.dt_i)
        t = self.raman.io_update()
        at_mu(t)
        delay_mu(self.p.dt_u)

        delay(0.1)
        
        self.sample(1)

        delay(1.)

        self.raman.clean_up_fast_frequency_update()

        # self.raman.set_frequency_fast(frequency_transition=f_raman_new)

        # self.reset_profiles()

    @kernel
    def trig(self):
        self.ttl.trig.pulse_mu(100, compensate_timeline=True) # introduces no delay
        
    @kernel
    def print_settings(self):
        self.print_settings_single(self.raman.dds0)
        # self.print_settings_single(self.raman.dds1)
        # self.print_settings_single(self.dds.dds_lo)

    @kernel
    def print_settings_single(self, dds):
        aprint('dds key: ', dds.key)
        f,p,a = dds.dds_device.get()
        aprint('profile registers: ', f/1.e6, p, a)
        delay(1.e-3)
        f = dds.dds_device.get_frequency()
        delay(1.e-3)
        a = dds.dds_device.get_amplitude()
        delay(1.e-3)
        p = dds.dds_device.get_phase()
        delay(1.e-3)
        aprint('direct registers: ', f/1.e6, p, a)

    @kernel
    def setup_fast_update_profiles(self):
        self.raman.dds0._configure_ffua_profile()
        # self.raman.dds1._configure_ffua_profile()
        # self.dds.dds_lo._configure_ffua_profile()

    @kernel
    def reset_profiles(self):
        self.raman.dds0._restore_default_profile_mode()
        # self.raman.dds1._restore_default_profile_mode()
        # self.dds.dds_lo._restore_default_profile_mode()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):

        import os
        import numpy as np
        
        np.save(r'C:\Users\bananas\code\k-jam\jpagett\data\data_xvars.npy', self.scan_xvars[0].values)
        np.save(r'C:\Users\bananas\code\k-jam\jpagett\data\data_v.npy', self.data.v._run_data)

        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath, notify=False)