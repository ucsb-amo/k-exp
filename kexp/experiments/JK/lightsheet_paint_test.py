from artiq.experiment import *
from artiq.experiment import delay
import numpy as np
from kexp import Base, img_types, cameras, Adjust

# Lightsheet painting test: the lightsheet load of
# default_experiments/lightsheet_load.py, scanning the FM of the Siglent at
# 192.168.1.126 that drives the lightsheet AO (self.lightsheet_painting_test,
# 80 MHz carrier, <= 2 Vpp). The amplitude is never changed here.
#
# A 0 rate or 0 deviation means painting OFF: FM is switched off and the
# carrier sits at 80 MHz. (At a near-zero FM rate the carrier would instead be
# frozen at an arbitrary point within +/- the deviation.) Those points are
# the unpainted reference.
#
# The Siglent's FM state is read in prepare() (recorded in params as
# *_at_start) and put back after the scan. It is NOT put back if the run
# aborts on an exception.

class lightsheet_paint_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                    save_data=True,
                    camera_select=cameras.xy_basler,
                    imaging_type=img_types.ABSORPTION, warmup_shots=2)

        self.p.t_tof = 900.e-6

        self.xvar('frequency_fm_deviation_lightsheet',[0.0,(0.35)*1.e6])
        self.p.frequency_fm_deviation_lightsheet=0.35*1.e6
        self.p.frequency_fm_rate_lightsheet = 192.e3
        # self.xvar('frequency_fm_deviation_lightsheet', np.linspace(0.3, 0.6, 7)*1.e6)
        # self.xvar('frequency_fm_rate_lightsheet', np.linspace(170.e3, 230.e3, 9))

        self.p.N_repeats = 7
        self.p.t_mot_load = 1.
        self.p.imaging_state = 2.

        self._record_siglent_start_state()

        # Adjust.__init__(self)

        self.finish_prepare(shuffle=True)

    def _record_siglent_start_state(self):
        """Read (only) the Siglent's FM state, to put it back after the scan."""
        ch = self.lightsheet_painting_test
        try:
            st = ch.read_state()
        except Exception as e:
            raise RuntimeError(f"lightsheet Siglent {ch._instr.ip} could not be read "
                               f"({type(e).__name__}: {e}); not starting.") from e
        print(f"lightsheet Siglent at start: {ch.describe(st)}")
        fm_on = (st['mod_state'] == 'ON' and st['mod_type'] == 'FM'
                 and isinstance(st['fm_deviation'], float)
                 and isinstance(st['fm_rate'], float))
        if fm_on:
            # The restore after the scan must not raise (that would skip the
            # save): refuse now if the start values are outside the limits.
            ch._check(-1., st['fm_deviation'], st['fm_rate'])
        self.p.fm_on_lightsheet_at_start = 1. if fm_on else 0.
        self.p.frequency_fm_deviation_lightsheet_at_start = st['fm_deviation'] if fm_on else -1.
        self.p.frequency_fm_rate_lightsheet_at_start = st['fm_rate'] if fm_on else -1.

    @kernel
    def set_painting(self, fm_deviation, fm_rate):
        if fm_deviation > 0. and fm_rate > 0.:
            self.lightsheet_painting_test.set(fm_deviation=fm_deviation, fm_rate=fm_rate)
            self.lightsheet_painting_test.fm_on()
        else:
            self.lightsheet_painting_test.fm_off()

    @kernel
    def scan_kernel(self):

        # Host RPCs (write + read-back, tens of ms): before the sequence starts.
        self.set_painting(self.p.frequency_fm_deviation_lightsheet,
                          self.p.frequency_fm_rate_lightsheet)

        self.imaging.set_power(self.camera_params.amp_imaging)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)

        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        delay(self.p.t_lightsheet_hold)

        self.lightsheet.off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.lightsheet_painting_test.init()   # carrier 80 MHz, amplitude <= 2 Vpp checked
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        if self.p.fm_on_lightsheet_at_start == 1.:
            self.set_painting(self.p.frequency_fm_deviation_lightsheet_at_start,
                              self.p.frequency_fm_rate_lightsheet_at_start)
        else:
            self.lightsheet_painting_test.fm_off()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
