from artiq.experiment import *
from artiq.language.core import now_mu, delay
from artiq.coredevice.core import CompileError

from kexp import Base

from waxx.util.artiq.async_print import aprint

# maybe liveOD runs this when an experiment is not running? It knows when experiments are running...

class testcrate_base(EnvExperiment, Base):

    def prepare(self):
        # setup_camera=False: the monitor acquires nothing, so the APD pickoff
        # stage stays wherever the last experiment left it.
        Base.__init__(self, setup_camera=False, suppress_live_od=True)
        # The monitor is not a run: it must not fence composite ops (they
        # are what it serves), nor get the pre-run hazard check and stamp.
        self._is_monitor = True
        self.finish_prepare(shuffle=False)
        # Composite-device ops for the Device Control GUI's Composite tab
        # (kexp.config.composite_devices): one kernel per op, compiled into
        # monitor_loop.  Also seeds the kernel's channel cache from the device
        # state file, so what the monitor writes back after an op is true --
        # see waxx Monitor.init_composites.  Bad definitions cost the tab,
        # never the monitor.
        try:
            from kexp.config.composite_devices import COMPOSITE_DEVICES
            self.monitor.init_composites(COMPOSITE_DEVICES)
        except Exception as e:
            print(f"[Monitor] ERROR: composite device definitions rejected ({e!r}); "
                  f"running without composite ops.")
            self.monitor.disable_composites(repr(e))

    def run(self):
        """Host entry point; the kernel is compiled here.  A composite op that
        does not compile must not take the monitor down -- it holds the
        hardware in its idle state and serves the DDS/DAC/TTL tabs -- so on a
        CompileError the kernel is rebuilt without composite ops and started
        anyway, with the compiler's message in the monitor log."""
        try:
            self.run_kernel()
        except CompileError as e:
            if not self.monitor.composites_enabled:
                raise
            print("[Monitor] ERROR: the monitor did not compile with its composite "
                  "ops -- starting it WITHOUT them. Compiler output:")
            print(e)
            self.monitor.disable_composites("did not compile")
            self.run_kernel()

    @kernel
    def run_kernel(self):
        self.init_kernel(run_id=False,
                         init_lightsheet=False,
                         setup_awg=False,
                         setup_slm=False,
                         dds_set=False,
                         dds_off=False,
                         beat_ref_on=True,
                         init_shuttler=False,
                         init_imaging=False,
                         init_ry=False,
                         init_magnets=False)
        # self.init_kernel(run_id=False,
        #                  dds_off=False,
        #                  dds_set=False,
        #                  init_dac=True,
        #                  init_dds=True)

        self.monitor.monitor_loop(verbose=False)
