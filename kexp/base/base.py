import numpy as np
import os

from artiq.experiment import *
from artiq.language.core import kernel_from_string, now_mu, delay

from waxa.data import DataSaver
from waxa.config.img_types import img_types as img
from waxx.base.expt import Expt
from waxx.config.timeouts import INIT_KERNEL_CAMERA_CONNECTION_TIMEOUT
from waxx.util import console

from kexp.base import Devices, Cooling, Image, Cameras, Control, Clients
from kexp.base.cameras import resolve_run_config
from kexp.config.camera_id import cameras
from kexp.config.ip import PATHS, server_talk
from kexp.config.data_vault import DataVault

from kexp.util.artiq.async_print import aprint

class Base(Expt, Devices, Cooling, Image, Cameras, Control, Clients):
    def __init__(self,
                 setup_camera=True,
                 save_data=True,
                 imaging_type=img.ABSORPTION,
                 absorption_image=None,
                 camera_select=cameras.xy_basler,
                 expt_params=None,
                 data_vault=None,
                 suppress_live_od=False,
                 save_on_underflow=False,
                 override_apd_stage=None,
                 warmup_shots=0,
                 verbosity=None):

        # camera_select picks the detector and setup_camera says whether to
        # acquire with it: liveOD frames for a camera, the pickoff stage in
        # for the APD.  See resolve_run_config.
        camera_select, capture_frames, save_data, apd_stage = resolve_run_config(
            camera_select=camera_select, setup_camera=setup_camera,
            override_apd_stage=override_apd_stage,
            suppress_live_od=suppress_live_od, save_data=save_data)

        super().__init__(setup_camera=capture_frames,
                         absorption_image=absorption_image,
                         save_data=save_data,
                         server_talk=server_talk,
                         verbosity=verbosity)

        if expt_params == None:
            from kexp.config.expt_params import ExptParams
            self.params = ExptParams()
        else:
            self.params = expt_params

        self.p = self.params
        if data_vault == None:
            self.data = DataVault(self)
        else:
            self.data = data_vault
        # Per-shot latch for Image.record_imaging_conditions (the mixin
        # __init__s are not chained, so it is set here). Reset each shot in
        # init_scan_kernel.
        self._imaging_conditions_recorded = False
        
        self.prepare_devices(expt_params=self.params)

        _img_config = self.choose_camera(imaging_type, camera_select)
        self.configure_imaging_system(imaging_configuration=_img_config)

        
        self.ds = DataSaver(*PATHS, server_talk=server_talk)

        self.run_info.save_on_underflow = int(save_on_underflow)

        Clients.__init__(self, suppress_live_od=suppress_live_od)

        # OPX+ program manager (kexp.control.opx). Host-only and inert --
        # nothing talks to (or imports) qm until self.opx.use(sequence) is
        # called in prepare(). Never referenced in a kernel.
        from kexp.control.opx.opx_config import make_opx_manager
        self.opx = make_opx_manager(self)

        # Resolved above: in when acquiring with the APD, out when a camera
        # grabs frames, None (stage left alone) when acquiring nothing.
        self.pdxc.set_apd_stage(apd_stage)

        # Warm-up dry run. The first shot of a run is typically ~25% low in
        # atom number (measured 2026-09-08, runs 78510-78570): a seconds-scale
        # thermal transient in the evaporation hardware. warmup_shots = N runs
        # N imaging-free preparations (Cooling.warmup_kernel) before the first
        # real shot, invisible to the camera, DataSaver and liveOD.
        self.params.N_warmup_shots = int(warmup_shots)
        if self.params.N_warmup_shots <= 0:
            console.info("[warmup] none: first shot likely ~25% low "
                         "(Base(warmup_shots=2) to fix).")
        else:
            console.info(f"[warmup] {self.params.N_warmup_shots} warm-up "
                         "shot(s) before the first real shot.")

    def finish_prepare(self,N_repeats=[],shuffle=True):
        """
        To be called at the end of prepare.
        """

        self.finish_prepare_wax(N_repeats=N_repeats,shuffle=shuffle)

        # self.configure_imaging_system(polmod_ao_bool=self._polmod_config)
        self.dds.stash_defaults()

        if self.tweezer.traps == []:
            self.tweezer.add_tweezer_list()
        self.tweezer.save_trap_list()

        # After finish_prepare_wax so the xvars are repeated and shuffled:
        # builds the per-shot value tables, compiles the QUA program and
        # starts the job (it parks on its first wait_for_trigger). No-op
        # unless self.opx.use(...) was called in prepare().
        self.opx.on_finish_prepare()

    @kernel
    def init_kernel(self, run_id = True,
                    init_dds =  True, 
                    init_dac = True,
                    dds_set = True, 
                    dds_off = True, 
                    init_sampler = True,
                    init_imaging = True,
                    beat_ref_on=True,
                    init_shuttler = True, 
                    init_lightsheet = True,
                    setup_awg = True, 
                    setup_slm = True,
                    init_magnets = True,
                    init_ry = True,
                    force_dds_init = True):
        """
        force_dds_init: run the full AD9910 init on every channel. By default
        (False) channels that still hold their PLL / SYNC setup from an earlier
        run are skipped, which saves ~1.5 s per run -- see Devices.init_all_dds
        for the checks. Pass True after touching the Urukul clocking or SYNC
        wiring, or whenever DDS phase coherence is in doubt.
        """

        self.core.reset()

        if self.setup_camera:
            self.wait_for_camera_ready(timeout=INIT_KERNEL_CAMERA_CONNECTION_TIMEOUT)
            if self._verbosity >= 2:   # console.VERBOSE
                print("[camera] ready.")
        if setup_slm:
            self.setup_slm(self.run_info.imaging_type)
        if run_id:
            # the host already printed the run id at finish_prepare
            if self._verbosity >= 2:   # console.VERBOSE
                print(self._ridstr)
        if setup_awg:
            self._setup_awg = setup_awg
            self.tweezer.awg_init()
        self.core.break_realtime()
        if init_dac:
            self.dac.dac_device.init() # initializes DAC
            delay(self.params.t_rtio)
        if init_shuttler:
            self.shuttler.init()
            self.core.break_realtime()
        if init_dds:
            self.init_all_cpld() # initializes DDS CPLDs
            self.init_all_dds(force_dds_init) # initializes DDS channels (skips intact ones)
        if dds_set:
            delay(1*ms)
            self.dds.stash_defaults()
            self.set_all_dds() # set DDS to default values
        if dds_off:
            self.switch_all_dds(0) # turn all DDS off to start experiment
        self.core.break_realtime()
        # A crashed OPX run leaves this line HIGH (raman 80/150 AOs routed to
        # a halted OPX); nothing else drops it before the first shot's
        # cleanup_scan_kernel, and switch_all_dds does not cover a TTL.
        self.ttl.quantum_machines_raman_rf_handoff_ttl.off()
        if beat_ref_on:
            self.dds.beatlock_ref.on()
        if init_imaging:
            self.imaging.init()
            self.integrator.init()
            self.set_imaging_detuning()
            self.imaging.set_power(self.camera_params.amp_imaging)
        if init_sampler:
            self.sampler.init()
        if init_lightsheet:
            self.lightsheet.init()
        if init_magnets:
            self.outer_coil.off()
            self.inner_coil.off()
        if init_ry:
            self.ry_405.init()
            self.ry_980.init()
        
    @kernel
    def init_scan_kernel(self,two_d_tweezers = False):

        self.arm_scopes()

        self.background_field()
        self.read_magnetometer()
        # arm the once-per-shot capture of the outer-coil current at imaging
        self._imaging_conditions_recorded = False
        
        self.core.reset()
        
        self.reset_devices()

        self.reset_tweezers(two_d_tweezers)
        
    @kernel
    def reset_devices(self):
        # 2D MOT current back on
        self.dac.supply_current_2dmot.set(v=self.p.v_2d_mot_current)
        
        self.init_cooling()
        self.core.break_realtime()

        self.dds.reset_defaults()
        self.set_all_dds()
        self.core.break_realtime()

        # turn on 2D MOT beams
        self.dds.d2_2dh_c.on()
        self.dds.d2_2dh_r.on()
        self.dds.d2_2dv_c.on()
        self.dds.d2_2dv_r.on()
        self.dds.push.on()

        # reset imaging detuning, power
        self.set_imaging_shutters()
        delay(10.e-3)
        if self.p.imaging_state == 1.:
            self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging_F1)
        elif self.p.imaging_state == 2.:
            self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging)
        self.imaging.set_power(self.camera_params.amp_imaging,
                                reset_pid=False)

        self.integrator.init()

        self.ry_405.reset_used_flag()
        self.ry_980.reset_used_flag()

    @kernel
    def pre_scan(self):
        """Runs once, before the scan loop (see waxx Scanner.scan). Executes
        the opt-in warm-up shots requested via Base.__init__(warmup_shots=N).

        Each warm-up shot is: per-shot device reset, Cooling.warmup_kernel
        (overridable per experiment), then cleanup_warmup_kernel. It uses
        reset_devices()/reset_tweezers() directly rather than
        init_scan_kernel(), because the latter arms the scopes and writes a
        magnetometer reading into the DataVault, which would leave entries not
        matched to a real shot. Nothing here triggers the camera, writes shot
        data, or notifies liveOD.
        """
        for i in range(self.p.N_warmup_shots):
            aprint("[warmup] warm-up shot", i + 1)
            self.core.break_realtime()
            self.reset_devices()
            self.core.break_realtime()
            self.reset_tweezers(False)
            self.core.break_realtime()

            self.warmup_kernel()
            self.cleanup_warmup_kernel()
            
            delay(self.p.t_recover)
            self.core.break_realtime()

    @kernel
    def cleanup_warmup_kernel(self):
        """The safety-relevant part of cleanup_scan_kernel after a warm-up
        shot: raman shutter closed, coils stopped and discharged, 1064 beams
        off. Deliberately omits the PWOA/dark images, the DataVault write and
        the liveOD shot notification.
        """
        self.core.break_realtime()
        self.ttl.raman_shutter.off()
        self.core.break_realtime()
        self.reset_coils()
        self.lightsheet.off()
        self.tweezer.off()
        self.core.break_realtime()

    @kernel
    def cleanup_scan_kernel(self):

        self.cleanup_image_count()

        self.core.break_realtime()
        self.ttl.raman_shutter.off()
        self.raman.clean_up_fast_frequency_update()

        self.core.break_realtime()
        self.reset_coils()
        self.lightsheet.off()

        # line_trigger (and every other TTLInOut) input FIFO is drained in
        # cleanup_scan_kernel_wax via ttl_frame.clear_input_events().

        # The raman AOs belong to the ARTIQ DDSs between shots, whatever
        # happened inside an OPX window (an underflow there skips the
        # hand-back that normally drops this line).
        self.ttl.quantum_machines_raman_rf_handoff_ttl.off()
        # An RTIOUnderflow inside the take-back skips its RF-off events; the
        # OPX releases its blocks overlap after the hand-back regardless, so
        # RF left on here is light on the atoms. One RTIO event each (these
        # two switch DDSs have no DAC channel).
        self.imaging.off()
        self.raman.off()

        self.core.break_realtime()
        self.ry_405.lock_status()
        self.ry_980.lock_status()

        self.cleanup_scan_kernel_wax()

    @kernel
    def post_scan(self):
        # Siglent writes never raise: with the LAN down the sweep is reported
        # as failed (loudly) and skipped, and the run still ends normally.
        if self.ry_980._used:
            self.ry_980.sweep_to(reset=True)
        self.tweezer.reset_awg()
        self.core.break_realtime()
        self.background_field()
        

    def end(self, expt_filepath, notify=True, restart_monitor=True):
        # OPX stream data must land in its containers before end_wax
        # serializes the DataVault. A fetch failure must not lose the rest
        # of the run's data, but it must be loud: the OPX containers then
        # save as their zero placeholders.
        if getattr(self, 'opx', None) is not None and self.opx.active:
            try:
                self.opx.finish()
            except Exception as e:
                print(f"[opx] *** ERROR fetching OPX data: {e} -- the OPX "
                      f"data containers for this run are NOT populated. ***")
        self.end_wax(expt_filepath=expt_filepath, notify=notify, restart_monitor=restart_monitor)