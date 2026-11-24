import json
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
from kexp.config.calibration import CALIBRATION_CONFIG
from kexp.config.camera_id import cameras
from kexp.config.ip import PATHS, server_talk
from kexp.config.data_vault import DataVault
from kexp.control.cameras.diagnostic_images import diagnostic_images as make_diagnostic_images
from kexp.control.cameras.camera_stream import connect_camera_streams

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
                 verbosity=None,
                 diagnostic_images=True,
                 fast_coil_reset=True,
                 read_magnetometer_per_shot=True,
                 mot_preload=True):

        # camera_select picks the detector, setup_camera whether to acquire with it
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
        # self.calibrates(...) (waxx.calibration)
        self.calibration_config = CALIBRATION_CONFIG
        if data_vault == None:
            self.data = DataVault(self)
        else:
            self.data = data_vault
        # per-shot latch for Image.record_imaging_conditions (reset in init_scan_kernel)
        self._imaging_conditions_recorded = False
        # Control.reset_coils skips the ramps of a coil already off after a normal shot
        self.fast_coil_reset = bool(fast_coil_reset)
        # per-shot field read (Control.read_magnetometer); False: data.b = 0. every shot
        self.read_magnetometer_per_shot = bool(read_magnetometer_per_shot)
        # MOT pre-load: the MOT goes on at the end of each shot and loads until
        # the next mot(); the field read moves to the shot's end. Tested
        # 2026-10-23 (runs 88092-88098, outputs/2026-10-23_07-38_mot_preload):
        # N 0.979 (90 % CI 0.93-1.03), period -0.156 s, throughput gain not
        # resolved. data.b is ~4x noisier in this mode and not comparable with
        # a shot-start read; the pre-load runs on a rising inner-coil gradient.
        self.mot_preload = bool(mot_preload)
        self._mot_preloaded = False
        self._t_mot_preload_on_mu = np.int64(0)

        self.prepare_devices(expt_params=self.params)

        _img_config = self.choose_camera(imaging_type, camera_select)
        self.configure_imaging_system(imaging_configuration=_img_config)

        self.ds = DataSaver(*PATHS, server_talk=server_talk)
        self._snapshot_source_texts()   # params file + base classes, saved at end()

        self.run_info.save_on_underflow = int(save_on_underflow)

        Clients.__init__(self, suppress_live_od=suppress_live_od)

        # reference images of the cooling sequence (camera_id.diagnostic_frame):
        # sent to liveOD every shot, saved only by a run that saves; the claim
        # connects the cameras
        self.diagnostic_images = bool(diagnostic_images) and not bool(suppress_live_od)
        self.diag = make_diagnostic_images(self, enabled=self.diagnostic_images)

        self._apd_stage = apd_stage   # in (APD), out (camera), None (left alone)
        self._move_apd_stage_early()

        self.params.N_warmup_shots = int(warmup_shots)
        self.params.do_read_magnetometer_per_shot = int(self.read_magnetometer_per_shot)
        self.params.do_mot_preload = int(self.mot_preload)
        # 1: data.frequency_siglent_980/_405 hold the RF consultant's read-back
        self.params.ry_980_rf_consultant = int(self.ry_980.uses_rf_consultant)
        self.params.ry_405_rf_consultant = int(self.ry_405.uses_rf_consultant)
        self._note_warmup()

        # last: params assigned from here to finish_prepare are the experiment's overrides
        self.start_param_override_recording()

    def _move_apd_stage_early(self):
        """A cold process moves the APD stage here, so a tool that never calls
        finish_prepare still gets it; the claim then finds it in place. When
        the claim overlaps the compile (claim_overlap) the move runs on a
        thread, and _claim_apd_stage waits for it. A warm-launched process
        touches no hardware before GO: its claim moves the stage."""
        from waxx.util.device_state import queue_gate, claim_overlap
        self._apd_stage_task = None
        if queue_gate.is_warm():
            return
        stage = self._apd_stage
        if stage is not None and claim_overlap.applies_to(self):
            self._apd_stage_task = claim_overlap.background(
                "APD stage", lambda: self.pdxc.set_apd_stage(stage))
        else:
            self.pdxc.set_apd_stage(stage)

    def _claim_apd_stage(self):
        """The claim's stage step: wait for an early move (raising what it
        raised), then set the stage ("already <state>" if it was moved)."""
        from waxx.util.device_state import claim_overlap
        claim_overlap.wait(getattr(self, '_apd_stage_task', None))
        self.pdxc.set_apd_stage(self._apd_stage)

    def _note_warmup(self):
        """The warm-up's note on the Scan: line. Warm-up shots exist because a
        run's first shot is ~25 % low in N (2026-09-08, runs 78510-78570)."""
        if self.params.N_warmup_shots <= 0:
            self._scan_line_notes["warmup"] = ("warm-up none (first shot likely ~25% "
                                               "low; Base(warmup_shots=2) to fix)")
        else:
            self._scan_line_notes["warmup"] = (f"warm-up {self.params.N_warmup_shots} "
                                               "shot(s)")

    def finish_prepare(self,N_repeats=[],shuffle=True):
        """
        To be called at the end of prepare.
        """

        # (a cold run claims inside finish_prepare_wax; a warm one after its compile)

        # the stage each diagnostic frame is taken in (the kernel reads it);
        # claim_hardware rewrites the record once the cameras are connected
        self.diag.resolve_stages(self.params, self.scan_xvars)
        self._extra_file_texts["diagnostic_images"] = json.dumps(self.diag.record())
        self._check_mot_preload()

        self.finish_prepare_wax(N_repeats=N_repeats,shuffle=shuffle)

        # self.configure_imaging_system(polmod_ao_bool=self._polmod_config)
        self.dds.stash_defaults()

        if self.tweezer.traps == []:
            self.tweezer.add_tweezer_list()
        self.tweezer.save_trap_list()

    def _check_mot_preload(self):
        """Refuse (before any run id) a scanned or hand-set p.do_mot_preload --
        the pre-load is Base(mot_preload=...) -- and record what it does in the
        root text 'mot_preload'."""
        if 'do_mot_preload' in self.xvarnames:
            raise ValueError("do_mot_preload cannot be scanned: the pre-load is set for "
                             "the whole run with Base(mot_preload=...).")
        if int(self.params.do_mot_preload) != int(self.mot_preload):
            raise ValueError(f"p.do_mot_preload = {self.params.do_mot_preload} but "
                             f"Base(mot_preload={self.mot_preload}): set it with the "
                             f"Base argument, not the parameter.")
        if self.mot_preload:
            # the MOT stays on between shots: needs a scan loop that runs
            # cleanup_abort_kernel on any cleanup or between-shot exception
            from waxx.base import scanner as _scanner
            if not getattr(_scanner, "SAFE_STATE_ON_EVERY_CLEANUP_FAILURE", False):
                raise ValueError("Base(mot_preload=True) needs a waxx scan loop with "
                                 "SAFE_STATE_ON_EVERY_CLEANUP_FAILURE (jep/mot-preload wax); "
                                 f"the loaded one ({_scanner.__file__}) lacks it.")
        self._extra_file_texts["mot_preload"] = json.dumps(self._mot_preload_record())
        if self.mot_preload:
            self._scan_line_notes["mot_preload"] = ("MOT preload on (data.b read at "
                                                    "the shot's end)")

    def _mot_preload_record(self):
        """What the MOT pre-load does, for the run file."""
        record = {"enabled": self.mot_preload}
        if self.mot_preload:
            record.update({
                "what": "MOT (2D beams + push + 2D coil, 3D beams, inner coil at i_mot, "
                        "MOT shims) switched on at the end of each data shot that "
                        "returned normally -- after the coil reset and the shims / 2D "
                        "coil to 0 (and the field read, when on), before the "
                        "shot-complete message -- and after each warm-up shot; it "
                        "loads until the next shot's mot().",
                "parameters": "the MOT parameters the kernel holds when the pre-load goes "
                              "on: those of the shot that just ended, "
                              "so a scanned MOT parameter's pre-load uses the previous "
                              "shot's value (shuffled order).",
                "data_b": ("read once per shot at the END of the shot (coils reset, shims "
                           "and 2D coil at 0, before the MOT goes on): the magnetometer "
                           "server's latest sample, no wait; its delay after the end of the "
                           "outer-coil discharge is data.mot_preload[2] (negative = taken "
                           "before that end). Stored in that shot's slot. Runs without the "
                           "pre-load read it at the shot's start.")
                          if self.read_magnetometer_per_shot else
                          "not read (read_magnetometer_per_shot=False): 0. every shot",
                "data_mot_preload": "[pre-load s, in-shot MOT load s, magnetometer sample "
                                    "delay after the outer-coil discharge s (-1 = no read)] "
                                    "per shot",
                "t_mot_load_total": float(self.params.t_mot_load_total),
                "t_mot_load_min": float(self.params.t_mot_load_min),
                "end_of_run": "post_scan switches the pre-loaded MOT's light and 2D coil "
                              "current off and turns the inner coil off (background_field).",
                "on_error": "cleanup_abort_kernel: coils reset (full path), MOT light and "
                            "2D coil current off, 1064 off.",
            })
        return record

    def claim_hardware(self):
        """The claim's machine part (waxx Expt.claim), before the liveOD start:
        raising here stops the run before it has a run id. APD stage, a due
        SLM reinit, the wavemeter (exclusive), the camera streams. Sets nothing
        a kernel reads: a warm-launched run claims after its compile."""
        self._claim_apd_stage()
        self._slm_reinit_at_start()
        self._fzw.connect()
        connect_camera_streams(self)
        self.diag.report_connected()
        # as taken: a camera that failed to connect stores nothing;
        # exposure_delays_loaded rewrites it with the kernel's delays
        self._extra_file_texts["diagnostic_images"] = json.dumps(self.diag.record())

    def exposure_delays_loaded(self):
        """waxx hook: the kernel has loaded the claim's exposure delays; the
        diagnostic_images record says so."""
        diag = getattr(self, 'diag', None)
        if diag is not None:
            self._extra_file_texts["diagnostic_images"] = json.dumps(diag.record())

    def claim_after_start(self):
        """After the liveOD start, before the monitor announcement (which
        marks the state untrusted): stamp the device state the run starts
        from. Not for the monitor experiment."""
        if hasattr(self, 'monitor') and not getattr(self, '_is_monitor', False):
            self._stamp_device_state()

    def _slm_reinit_at_start(self):
        """A due (or running) SLM reinit is done now, between runs, and the run
        waits for it (back-to-back runs may never leave the machine idle for
        the monitor's). An Andor-path run (the SLM is in its beam) refuses a
        failed reinit; others warn. Saved as 'slm_at_start'. Not for the
        monitor experiment."""
        if getattr(self, '_is_monitor', False):
            return
        uses_slm = self.camera_params.optical_path_key == cameras.andor.key
        record = self.slm.reinit_if_due(by=f"run start ({self._expt_file_stem()})",
                                        required=uses_slm)
        record["uses_slm"] = uses_slm
        try:
            self._extra_file_texts["slm_at_start"] = json.dumps(record, default=repr)
        except Exception as e:
            print(f"[slm] WARNING: could not store the SLM state at run start ({e!r}).")

    def _stamp_device_state(self):
        """The monitor server's pre-run report (state, trust, hazards, journal)
        stored as 'device_state_at_start'. Only a failed check is printed:
        a run sets the state it needs. Never raises."""
        from types import SimpleNamespace
        try:
            from waxx.util.device_state.run_stamp import pre_run_report, report_warnings
            from kexp.config.composite_devices import COMPOSITE_DEVICES
            report = pre_run_report(self.monitor, COMPOSITE_DEVICES, self.params,
                                    SimpleNamespace(dds=self.dds, dac=self.dac))
        except Exception as e:
            print(f"[device state] WARNING: the pre-run device-state check failed ({e!r}); "
                  f"nothing was checked and nothing is stamped.")
            return
        for line in report_warnings(report, hazards=False, untrusted=False):
            print(f"[device state] *** {line} ***")
        try:
            self._extra_file_texts["device_state_at_start"] = json.dumps(report, default=repr)
        except Exception as e:
            print(f"[device state] WARNING: could not store the device-state stamp ({e!r}).")

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
                    force_dds_init = False,
                    raman_aos_on = True):
        """
        raman_aos_on: raman_150_plus / raman_80_plus on after the all-off,
        before the first raman.init(); light stays gated by raman_switch (off)
        and the raman shutter.

        force_dds_init: the full AD9910 init on every channel (~1.4 s). False
        by default since 2026-11-19 (user's call, to be checked against the
        Raman relative phase): channels that kept their PLL / SYNC setup are
        skipped (Devices.init_all_dds; recorded as `dds_init`). Pass True
        after touching Urukul clocking or SYNC wiring, or when DDS phase
        coherence is in doubt.
        """

        # the claim's exposure delays (an RPC, before the reset: costs no slack)
        self.load_exposure_delays()
        self.core.reset()

        if self.setup_camera:
            self.wait_for_camera_ready(timeout=INIT_KERNEL_CAMERA_CONNECTION_TIMEOUT)
            if self._verbosity >= 2:   # console.VERBOSE
                print("[camera] ready.")
        if setup_slm:
            self.setup_slm(self.run_info.imaging_type)
        if run_id:
            # an RPC: a warm-launched run gets its id after the compile
            if self._verbosity >= 2:   # console.VERBOSE
                self._print_run_id()
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
            self.tweezer.ao2_idle()   # the PID2 AO stays on while PID2 is unused
        self.core.break_realtime()
        # a crashed OPX run leaves this HIGH (raman AOs routed to the OPX)
        self.ttl.quantum_machines_raman_rf_handoff_ttl.off()
        if beat_ref_on:
            self.dds.beatlock_ref.on()
        if raman_aos_on:
            self.dds.raman_150_plus.on()
            self.dds.raman_80_plus.on()
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

        # wait first: reset() drops unplayed events (e.g. the warm-up's coil ramp-down)
        self.core.wait_until_mu(now_mu())
        self.core.reset()

        self.arm_scopes()

        # -1 until mot() / the end-of-shot read fill them
        self.data.mot_preload.put_data(-1., 0)
        self.data.mot_preload.put_data(-1., 1)
        self.data.mot_preload.put_data(-1., 2)
        if not self._mot_preloaded:
            self.background_field()   # a pre-loaded MOT keeps its fields
        self._read_field_at_shot_start()
        self.read_raman_wavemeter()
        self._imaging_conditions_recorded = False

        self.core.reset()

        self.reset_devices()
        self.reset_tweezers(two_d_tweezers)

    @kernel
    def _read_field_at_shot_start(self):
        """data.b: read now, or 0. (not read, written explicitly). A pre-load
        run reads it at the shot's end instead (_mot_preload_at_shot_end)."""
        if not self.read_magnetometer_per_shot:
            self.data.b.put_data(0.)
        elif not self.mot_preload:
            self.read_magnetometer()

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
        """Once before the scan loop: the Base(warmup_shots=N) warm-up shots.
        Each is reset_devices/reset_tweezers (not init_scan_kernel, which
        writes data), warmup_kernel, cleanup_warmup_kernel: no camera, no shot
        data, no liveOD, diagnostic cameras off. Abort is checked between
        warm-ups (after the last, the scan loop checks)."""
        self.diag.active = False
        for i in range(self.p.N_warmup_shots):
            aprint("[warmup] warm-up shot", i + 1)
            self.core.break_realtime()
            self.reset_devices()
            self.core.break_realtime()
            self.reset_tweezers(False)
            self.core.break_realtime()

            self.warmup_kernel()
            self.cleanup_warmup_kernel()
            if self.mot_preload:
                self.mot_preload_on()

            self.core.break_realtime()
            if i < self.p.N_warmup_shots - 1:
                self._check_for_abort_signal()
        self.diag.active = self.diag.enabled

    @kernel
    def cleanup_warmup_kernel(self):
        """The safety part of cleanup_scan_kernel: raman shutter closed, coils
        discharged, 1064 off. No images, data or liveOD notification."""
        self.core.break_realtime()
        self.ttl.raman_shutter.off()
        self.core.break_realtime()
        self.reset_coils()
        self.lightsheet.off()
        self.tweezer.off()
        self.core.break_realtime()

    @kernel
    def cleanup_abort_kernel(self):
        """Safe state after scan_kernel raised anything but an underflow,
        overflow or trigger timeout (waxx Scanner runs it, then re-raises):
        cleanup_warmup_kernel, a pre-loaded MOT off, then the raman DDS out of
        fast-frequency-update mode. A failure in that last step is printed and
        swallowed, so the original exception reaches the host."""
        self.cleanup_warmup_kernel()
        if self.mot_preload:
            self.core.break_realtime()
            self.mot_preload_off()
        try:
            self.core.break_realtime()
            self.raman.clean_up_fast_frequency_update()
        except:
            aprint("[scan] cleanup_abort_kernel: restoring the raman DDS from fast "
                   "frequency update mode failed; the next run's init_kernel re-inits it.")

    @kernel
    def cleanup_scan_kernel(self):

        # cleanup_image_count can raise (a wrong PWA count after an underflow,
        # an underflow in the reference frames), and no cleanup runs after it
        try:
            self.cleanup_image_count()
        except:
            self._outputs_safe_now()
            raise

        self.core.break_realtime()
        self.ttl.raman_shutter.off()

        self.core.break_realtime()
        # coils and high-power outputs before the raman DDS restore, which can
        # raise (2026-10-23); the coil cache is trusted only after a normal shot
        self.reset_coils(trust_cached_state=self.shot_completed and self.fast_coil_reset)
        self.lightsheet.off()
        self.tweezer.keep_ao2_on()   # the PID2 AO stays on between shots

        # TTL input FIFOs are drained in cleanup_scan_kernel_wax

        # raman AOs back to the ARTIQ DDSs and their RF off: an underflow in an
        # OPX window skips the hand-back and its RF-off events
        self.ttl.quantum_machines_raman_rf_handoff_ttl.off()
        self.imaging.off()
        self.raman.off()

        self.core.break_realtime()
        self.raman.clean_up_fast_frequency_update()   # DDS registers only

        self.core.break_realtime()
        self.ry_405.lock_status()
        self.ry_980.lock_status()

        # raises if a parallel SLM write had not settled at its first use
        # (the shot is then not recorded)
        self.slm.end_of_shot(self.shot_completed)
        self.core.break_realtime()

        if self.mot_preload:
            self._mot_preload_at_shot_end()

        self.cleanup_scan_kernel_wax()

    @kernel
    def _outputs_safe_now(self):
        """Coils reset in full (cache not trusted), then 1064, OPX hand-off,
        imaging and raman RF and the raman shutter off."""
        self.core.break_realtime()
        self.reset_coils(trust_cached_state=False)
        self.lightsheet.off()
        self.tweezer.off()
        self.ttl.quantum_machines_raman_rf_handoff_ttl.off()
        self.imaging.off()
        self.raman.off()
        self.ttl.raman_shutter.off()
        self.core.break_realtime()

    @kernel
    def _mot_preload_at_shot_end(self):
        """Coils already reset: shims and 2D coil to 0, the run's one field
        read per shot (latest sample; its delay after the outer-coil discharge
        goes to data.mot_preload[2]), then the MOT on -- only after a shot that
        returned normally. An Abort at shot-complete gets cleanup_abort_kernel,
        which switches it off."""
        self.background_field()
        if self.read_magnetometer_per_shot:
            self.read_magnetometer_after_coil_reset()
        if self.shot_completed:
            self.mot_preload_on()

    @kernel
    def post_scan(self):
        # Siglent sweeps never raise (a LAN failure is reported and skipped)
        if self.ry_980._used:
            self.ry_980.sweep_to(reset=True)
        if self.ry_405._used:
            self.ry_405.sweep_to(reset=True)
        if self._setup_awg:   # only if init_kernel set the AWG up
            self.tweezer.reset_awg()
        self.core.break_realtime()
        if self.mot_preload:
            # light and 2D current off; background_field turns the inner coil off
            self.mot_preload_off()
            self.core.break_realtime()
        self.background_field()


    def end(self, expt_filepath, notify=True, restart_monitor=True):
        self.end_wax(expt_filepath=expt_filepath, notify=notify, restart_monitor=restart_monitor)