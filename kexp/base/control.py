import numpy as np

from artiq.experiment import *
from artiq.experiment import delay, delay_mu, parallel, sequential, at_mu
from artiq.language.core import now_mu
from waxx.control.artiq.dummy_core import DummyCore
from waxx.control.exceptions import TriggerTimeout

from waxx.control.raman_beams import RamanBeamPair
from kexp.util.artiq.async_print import aprint

from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.dac_id import dac_frame
from kexp.config.expt_params import ExptParams
from kexp.config.data_vault import DataVault
from kexp.control.big_coil import igbt_magnet, hbridge_magnet
from kexp.control.awg_tweezer import tweezer
from kexp.control.painted_lightsheet import lightsheet
from waxx.control.integrator import Integrator
from waxx.util.guis.HMR_magnetometer.hmr_magnetometer_client import HMRClient
from waxx.control.misc.oscilloscopes import ScopeData
from waxx.control.beat_lock import BeatLockImagingPID

dv = -0.1
dvlist = np.linspace(1.,1.,5)

# Sanity bound on the wait for the OPX hand-back edge, from the trigger. Not
# a window to match to a sequence's length -- the gate is armed before the
# trigger and stays open until the edge comes -- only how long a dead or
# untriggered OPX takes to become a TriggerTimeout. Override per call:
# wait_for_quantum_machines_handback(t_timeout=...).
T_OPX_HANDBACK_TIMEOUT = 2.
T_OPX_TRIGGER_PULSE = 1.e-6

class Control():
    def __init__(self):
        # just to get syntax highlighting, placeholders
        self.core = DummyCore()
        self.data = DataVault()
        self.dds = dds_frame()
        self.ttl = ttl_frame()
        self.dac = dac_frame()
        self.inner_coil = hbridge_magnet()
        self.outer_coil = igbt_magnet()
        self.tweezer = tweezer()
        self.lightsheet = lightsheet()
        self.params = ExptParams()
        self.raman = RamanBeamPair()
        self.raman_nf = RamanBeamPair()
        self.magnetometer = HMRClient()
        self.integrator = Integrator()
        self.scope_data = ScopeData()
        self.imaging = BeatLockImagingPID()
        self.p = self.params

    @kernel
    def warmup_ry(self):
        self.ry_980.on()
        self.ry_405.on()
        delay(100.e-3)
        self.ry_405.off()
        self.ry_980.off()

    @kernel
    def integrated_imaging_pulse(self, data_container, t, idx=0,
                                dark=False):
        """Thin delegate -- the implementation now lives on the imaging beam
        object (waxx.control.beat_lock.BeatLockImagingPID), which owns the
        integrator. Kept here so the existing self.integrated_imaging_pulse(...)
        call sites throughout kexp keep working; new code can call
        self.imaging.integrated_imaging_pulse(...) directly.
        """
        self.imaging.integrated_imaging_pulse(data_container, t, idx, dark)

    @kernel
    def tof_apd_abs_image(self):

        self.tweezer.off()
        delay(self.p.t_tof_apd_abs)
        
        t = self.p.t_imaging_pulse_apd_abs
        dc = self.data.post_shot_absorption

        self.integrated_imaging_pulse(dc,t,0)
        delay(3.e-6)
        self.raman.pulse(self.p.t_raman_pi_pulse)
        delay(2.e-6)
        self.integrated_imaging_pulse(dc,t,1)
        delay(200.e-6)
        self.integrated_imaging_pulse(dc,t,2)
        delay(10.e-6)
        self.integrated_imaging_pulse(dc,t,3,dark=True)
        
    @kernel
    def reset_tweezers(self, two_d_tweezers):
        if self._setup_awg:
            if two_d_tweezers:
                self.tweezer.set_static_2d_tweezers(freq_list1=self.params.frequency_tweezer_list1,
                                                    freq_list2=self.params.frequency_tweezer_list2,
                                                    amp_list1=self.params.amp_tweezer_list1,
                                                    amp_list2=self.params.amp_tweezer_list2)
            self.tweezer.reset_traps(self.xvarnames)
            delay(15.e-3)
            self.tweezer.awg_trg_ttl.pulse(t=1.e-6)
        
        self.tweezer.pid1_int_hold_zero.pulse(1.e-6)
        self.tweezer.pid1_int_hold_zero.on()

    @kernel
    def reset_coils(self):
        """
        Reset the inner, outer, and 2D coils to their default state.
        This includes stopping any PID control, turning off the coils,
        and discharging the power supplies through the coils.

        This is typically called at the end of an experiment to ensure
        that the coils are in a safe state for the next experiment.
        """
    
        # igbt_magnet.off() already ends with discharge() -- do not add a
        # second discharge() here, it costs ~130 ms per coil for nothing.
        self.outer_coil.stop_pid()
        delay(50.e-3)
        self.outer_coil.off()

        self.inner_coil.stop_pid()
        self.inner_coil.off()

    @kernel
    def arm_scopes(self):
        self.core.wait_until_mu(now_mu())
        self.scope_data.arm()
        self.core.break_realtime()

    @kernel
    def background_field(self):
        if self.outer_coil.i_supply != 0.:
            self.outer_coil.off()
        if self.inner_coil.i_supply != 0.:
            self.inner_coil.off()
        self.set_shims(0.,0.,0.)
        self.dac.supply_current_2dmot.set(0.)
        delay(10.e-3)

    @kernel
    def read_magnetometer(self):
        self.core.wait_until_mu(now_mu())
        b_magnitude = self.magnetometer.get_field_magnitude()
        self.data.b.put_data(b_magnitude)
        self.core.break_realtime()

    @kernel
    def prep_raman(self,
            frequency_transition=dv,
            fraction_power=dv,
            global_phase=0.,relative_phase=0.,
            t_phase_origin_mu=np.int64(-1),
            phase_mode=1,
            line_trigger=True):
        
        if frequency_transition == dv:
            frequency_transition = self.p.frequency_raman_transition
        if fraction_power == dv:
            fraction_power = self.p.fraction_power_raman
            
        self.raman.init(frequency_transition,
                        fraction_power,
                        global_phase,
                        relative_phase,
                        t_phase_origin_mu,
                        phase_mode)

        self.raman.pulse(3.e-3) # warm up
        delay(10.e-6)
        
        self.ttl.raman_shutter.on()
        delay(3.e-3)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(4.7e-3)
        if phase_mode == 1:
            self.raman.set_phase(t_phase_origin_mu=now_mu())

    @kernel
    def warmup_imaging(self):
        self.ttl.imaging_shutter_x.off()
        delay(3.e-3)
        self.imaging.pulse(1.e-3)
        self.ttl.imaging_shutter_x.on()
        

    @kernel
    def handoff_to_quantum_machines(self):
        """Start one OPX shot: arm the hand-back gate, trigger the OPX, turn
        the ARTIQ RF on for it to gate. Pairs with
        wait_for_quantum_machines_handback().

        The handshake, one shot, with the ExptParams values of 2026-09-25
        (the OPX half is framed by kexp.control.opx.builder from the channel
        map, which reads the same parameters):

            t0      trigger edge, ARTIQ -> OPX (ttl32, 1 us pulse); the
                    hand-back gate on ttl41 is armed at t0 as well
            t0 + L  OPX sees the trigger (L is unpublished by QM; the input
                    is sampled at 250 MHz) and plays 'block' (16 ns) on both
                    RF-switch lines, which hold HIGH (sticky)
            t0 + t_opx_handoff_artiq_side                          (350 ns)
                    ARTIQ: handoff TTL high, imaging RF on, raman RF on --
                    three RTIO events at one timestamp (one event each:
                    these two switch DDSs have no DAC channel).
                    *** ASSUMPTION, NEVER MEASURED (milestone M1): the OPX
                    block is complete before this RF reaches the switch
                    AOMs, i.e. L + 16 ns + switch turn-off <= 350 ns. If it
                    is not, both beams leak for the difference every shot.
            t0 + t_opx_handoff_artiq_side + t_opx_handoff_opx_side (1.35 us)
                    ARTIQ returns to the caller; the OPX body may start
                    here -- the builder waits this SUM after its block plays
                    (ChannelMap.t_handoff_settle_s)
            ... sequence body on the OPX ...
            Te      hand-back edge, OPX -> ARTIQ (OPX digital 3 -> ttl41,
                    200 ns pulse, rising edge); the OPX holds both blocks
                    and leaves its analog drives untouched from here
            Te + t_opx_handback_artiq_trigger_receive_latency      (1 us)
                    ttl41 timestamps the edge (t_edge)
            t_edge + t_opx_handback_artiq_rtio_delay               (3 us)
                    ARTIQ: imaging switch off, raman switch off, handoff
                    TTL low -- at the SAME timestamp (switch-only take-back)
            ... + t_opx_handback_switch_fall_delay                 (5 us)
                    those switches have fallen. OPX releases the blocks
                    (pass) and only now may ramp its analog drives; ARTIQ
                    imaging.off() / raman.off() bookkeeping (re-writes the
                    same level). The OPX waits the SUM of the three from
                    its edge (ChannelMap.t_handback_hold_s).

        The gate on quantum_machines_receive_trigger is armed BEFORE the
        trigger and closed only after the edge, so a shot with nothing to
        play (t_raman_pulse = 0) can hand back within a microsecond of the
        trigger and still be caught; nothing about the OPX shot's length is
        coded on this side. The handoff TTL routes the raman 80/150 AOs to
        the OPX analog outputs for the whole window.

        Crash state. After the trigger the OPX shot never waits for ARTIQ
        again: it fires the hand-back, holds its blocks for the hold time and
        releases them whatever ARTIQ does. A kernel that dies between here
        and the take-back (an exception scan() does not catch, a killed
        process) therefore leaves ARTIQ RF ON on both switch AOMs and the
        handoff TTL HIGH -- light on the atoms from Te + hold until the
        next run's init_kernel (switch_all_dds(0), and the handoff-TTL drop
        there), the same end state as any crash with a beam on. An
        RTIOUnderflow inside the take-back is caught by scan(), and
        cleanup_scan_kernel switches both RF off and drops the TTL. The
        blocks are only left HIGH if the OPX job itself stops mid-body; what
        the OPX digital lines do when a job is halted mid-block is not
        documented by QM (M1).
        """
        self.ttl.quantum_machines_receive_trigger.arm()
        t_trigger = now_mu()
        self.ttl.quantum_machines_trigger.pulse(T_OPX_TRIGGER_PULSE)
        at_mu(t_trigger)
        delay(self.p.t_opx_handoff_artiq_side)
        self.ttl.quantum_machines_raman_rf_handoff_ttl.on()
        self.imaging.on()
        self.raman.on()
        delay(self.p.t_opx_handoff_opx_side)

    @kernel
    def wait_for_quantum_machines_handback(self, t_timeout=T_OPX_HANDBACK_TIMEOUT):
        """End of the OPX shot: wait for the hand-back edge, then take the
        RF and the raman AOs back. Timing diagram in
        handoff_to_quantum_machines.

        The timeline resumes t_opx_handback_artiq_rtio_delay (2 us) after
        the edge's timestamp. That is the kernel CPU's slack to learn of the
        edge and submit the three time-critical events, all at one
        timestamp: the RF switches of the raman and imaging switch AOMs off
        (DDS.set_sw, one RTIO event each) and the handoff TTL low.
        t_opx_handback_switch_fall_delay later those switches have fallen,
        and the OPX -- which waits receive latency + rtio delay + switch
        fall from its own edge -- releases its blocks. The CPU reaction
        time has not been measured on this machine: the print at VERBOSE
        below IS the measurement (~4-7 us was expected when the take-back
        had 7.5 us; see TTL_IN.wait_for_edge). If it is longer than the
        rtio delay, every shot underflows here. An underflow here is caught
        by scan(), and cleanup_scan_kernel finishes the take-back (RF off,
        TTL low) -- but the OPX has released its blocks by then, so the RF
        reaches the atoms until cleanup runs.

        imaging.off() / raman.off() at the end of the hold re-write the
        same switch level and keep the cached switch state honest; these
        two DDSs have no DAC channel, so each is one RTIO event, not SPI
        traffic. They are not what makes the light safe -- the set_sw
        events inside the hold are.

        No edge within t_timeout of the trigger: the same take-back runs
        (the OPX released its blocks long ago, or never ran), then
        TriggerTimeout ends the shot -- the scan loop runs cleanup and
        aborts the run, or re-raises it under scan(raise_underflow=True).
        The cost of a dead job is t_timeout (2 s) per shot with both
        switch-AOM RFs on and the OPX lines idle low (= pass).
        """
        t_edge = self.ttl.quantum_machines_receive_trigger.wait_for_edge(
            self.p.t_opx_handback_artiq_rtio_delay, t_timeout)
        # time-critical, inside the OPX's hold
        self.imaging.dds_sw.set_sw(0)
        self.raman.dds_sw.set_sw(0)
        self.ttl.quantum_machines_raman_rf_handoff_ttl.off()
        if self._verbosity >= 2:   # console.VERBOSE
            # slack left once the critical events were in: how much of
            # t_opx_handback_artiq_rtio_delay was actually needed
            slack_mu = now_mu() - self.core.get_rtio_counter_mu()
            aprint("[opx] hand-back: timeline slack after the RF-off events =",
                   slack_mu, "mu")
        # bookkeeping, at the end of the hold (switches have fallen)
        delay(self.p.t_opx_handback_switch_fall_delay)
        self.imaging.off()
        self.raman.off()
        if t_edge < 0:
            aprint("[opx] no hand-back edge on quantum_machines_receive_trigger "
                   "within T_OPX_HANDBACK_TIMEOUT of the trigger: the OPX job is "
                   "not running, is not seeing the trigger, or its shot is longer "
                   "than the timeout. ARTIQ RF and the handoff TTL are back off.")
            raise TriggerTimeout("no OPX hand-back edge on ttl{0} within the "
                                 "timeout",
                                 np.int64(self.ttl.quantum_machines_receive_trigger.ch))
