from artiq.experiment import *
from artiq.language import now_mu, delay, at_mu, kernel, TFloat, TInt32, TInt64, delay_mu
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.urukul import DEFAULT_PROFILE
from artiq.coredevice.ttl import TTLOut
import numpy as np
from numpy import int64, int32

from waxx.control.artiq.DDS import DDS
from kexp.util.db.device_db import device_db

_PHASE_MODE_DEFAULT = -1
PHASE_MODE_CONTINUOUS = 0
PHASE_MODE_ABSOLUTE = 1
PHASE_MODE_TRACKING = 2

_AD9910_REG_CFR1 = 0x00
_AD9910_REG_CFR2 = 0x01
_AD9910_REG_CFR3 = 0x02
_AD9910_REG_AUX_DAC = 0x03
_AD9910_REG_IO_UPDATE = 0x04
_AD9910_REG_FTW = 0x07
_AD9910_REG_POW = 0x08
_AD9910_REG_ASF = 0x09
_AD9910_REG_SYNC = 0x0a
_AD9910_REG_RAMP_LIMIT = 0x0b
_AD9910_REG_RAMP_STEP = 0x0c
_AD9910_REG_RAMP_RATE = 0x0d
_AD9910_REG_PROFILE0 = 0x0e
_AD9910_REG_PROFILE1 = 0x0f
_AD9910_REG_PROFILE2 = 0x10
_AD9910_REG_PROFILE3 = 0x11
_AD9910_REG_PROFILE4 = 0x12
_AD9910_REG_PROFILE5 = 0x13
_AD9910_REG_PROFILE6 = 0x14
_AD9910_REG_PROFILE7 = 0x15
_AD9910_REG_RAM = 0x16

# RAM destination
RAM_DEST_FTW = 0
RAM_DEST_POW = 1
RAM_DEST_ASF = 2
RAM_DEST_POWASF = 3

@rpc(flags={'async'})
def aprint(*args):
    print(*args)

class dds(EnvExperiment):
    def prepare(self):
        self.core = self.get_device('core')
        self.ttl1 = self.get_device('ttl5')
        self.zotino0 = self.get_device('zotino0')

        self.dds0 = DDS(0,1,1.e6,0.5,device_db=device_db,dac_device=self.zotino0)
        self.dds0.get_devices(self)

        self.dds1 = DDS(0,2,0.71e6,0.5,device_db=device_db,dac_device=self.zotino0)
        self.dds1.get_devices(self)

        self.f = [10.e6, 11.e6]

        self.t_idx = 0
        self.t = np.zeros(2).astype(np.int64)

    @kernel
    def get_slack(self):
        self.t[self.t_idx] = now_mu() - self.core.get_rtio_counter_mu()
        self.t_idx += 1

    @kernel
    def set_mu2(self, dds_device, ftw: TInt32 = 0, pow_: TInt32 = 0, asf: TInt32 = 0x3fff,
               phase_mode: TInt32 = _PHASE_MODE_DEFAULT,
               ref_time_mu: TInt64 = int64(-1),
               profile: TInt32 = DEFAULT_PROFILE,
               ram_destination: TInt32 = -1) -> TInt32:
        """Set DDS data in machine units.

        This uses machine units (FTW, POW, ASF). The frequency tuning word
        width is 32, the phase offset word width is 16, and the amplitude
        scale factor width is 14.

        After the SPI transfer, the shared IO update pin is pulsed to
        activate the data.

        .. seealso: :meth:`AD9910.set_phase_mode` for a definition of the different
            phase modes.

        :param ftw: Frequency tuning word: 32-bit.
        :param pow_: Phase tuning word: 16-bit unsigned.
        :param asf: Amplitude scale factor: 14-bit unsigned.
        :param phase_mode: If specified, overrides the default phase mode set
            by :meth:`set_phase_mode` for this call.
        :param ref_time_mu: Fiducial time used to compute absolute or tracking
            phase updates. In machine units as obtained by :meth:`~artiq.language.core.now_mu()`.
        :param profile: Single tone profile number to set (0-7, default: 7).
            Ineffective if ``ram_destination`` is specified.
        :param ram_destination: RAM destination (:const:`RAM_DEST_FTW`,
            :const:`RAM_DEST_POW`, :const:`RAM_DEST_ASF`,
            :const:`RAM_DEST_POWASF`). If specified, write free DDS parameters
            to the ASF/FTW/POW registers instead of to the single tone profile
            register (default behaviour, see ``profile``).
        :return: Resulting phase offset word after application of phase
            tracking offset. When using :const:`PHASE_MODE_CONTINUOUS` in
            subsequent calls, use this value as the "current" phase.
        """
        t0 = int64(0)
        tf = int64(0)
        if phase_mode == _PHASE_MODE_DEFAULT:
            phase_mode = dds_device.phase_mode
        # Align to coarse RTIO which aligns SYNC_CLK. I.e. clear fine TSC
        # This will not cause a collision or sequence error.
        t0 = now_mu()
        at_mu(t0 & ~7)
        if phase_mode != PHASE_MODE_CONTINUOUS:
            # Auto-clear phase accumulator on IO_UPDATE.
            # This is active already for the next IO_UPDATE
            dds_device.set_cfr1(phase_autoclear=1)
            if phase_mode == PHASE_MODE_TRACKING and ref_time_mu < 0:
                # set default fiducial time stamp
                ref_time_mu = 0
            if ref_time_mu >= 0:
                # 32 LSB are sufficient.
                # Also no need to use IO_UPDATE time as this
                # is equivalent to an output pipeline latency.
                dt = int32(t0) - int32(ref_time_mu)
                pow_ += dt * ftw * dds_device.sysclk_per_mu >> 16
        if ram_destination == -1:
            dds_device.write64(_AD9910_REG_PROFILE0 + profile,
                         (asf << 16) | (pow_ & 0xffff), ftw)
        else:
            if not ram_destination == RAM_DEST_FTW:
                dds_device.set_ftw(ftw)
            if not ram_destination == RAM_DEST_POWASF:
                if not ram_destination == RAM_DEST_ASF:
                    dds_device.set_asf(asf)
                if not ram_destination == RAM_DEST_POW:
                    dds_device.set_pow(pow_)
        # tf = now_mu()
        # delay_mu(int64(self.sync_data.io_update_delay))
        # self.cpld.io_update.pulse_mu(8)  # assumes 8 mu > t_SYN_CCLK
        # at_mu(now_mu() & ~7)  # clear fine TSC again
        # if phase_mode != PHASE_MODE_CONTINUOUS:
        #     self.set_cfr1()
            # future IO_UPDATE will activate
        # aprint(tf-t0)
        return pow_
    
    @kernel
    def set(self, dds_device, frequency: TFloat = 0.0, phase: TFloat = 0.0,
            amplitude: TFloat = 1.0, phase_mode: TInt32 = _PHASE_MODE_DEFAULT,
            ref_time_mu: TInt64 = int64(-1), profile: TInt32 = DEFAULT_PROFILE,
            ram_destination: TInt32 = -1) -> TFloat:
        """Set DDS data in SI units.

        See also :meth:`AD9910.set_mu`.

        :param frequency: Frequency in Hz
        :param phase: Phase tuning word in turns
        :param amplitude: Amplitude in units of full scale
        :param phase_mode: Phase mode constant
        :param ref_time_mu: Fiducial time stamp in machine units
        :param profile: Single tone profile to affect.
        :param ram_destination: RAM destination.
        :return: Resulting phase offset in turns
        """
        return dds_device.pow_to_turns(self.set_mu2(dds_device,
            dds_device.frequency_to_ftw(frequency), dds_device.turns_to_pow(phase),
            dds_device.amplitude_to_asf(amplitude), phase_mode, ref_time_mu,
            profile, ram_destination))

    @kernel
    def run(self):
        self.core.reset()

        self.dds0.init()
        delay(1.e-6)
        self.dds1.init()
        delay(1.e-6)

        # t0 = 0
        # t1 = 0
        # t0 = self.dds0.dds_device.tune_io_update_delay()
        # t1 = self.dds1.dds_device.tune_io_update_delay()
        # aprint(t0,t1)

        delay(10.e-3)
        
        self.dds0.on()
        self.dds1.on()

        # self.dds0.off()
        # self.dds1.off()
        PHASE_MODE_CONTINUOUS = 0
        PHASE_MODE_ABSOLUTE = 1
        PHASE_MODE_TRACKING = 2
        self.dds0.dds_device.set_phase_mode(PHASE_MODE_TRACKING)
        self.dds1.dds_device.set_phase_mode(PHASE_MODE_TRACKING)
        
        t_pulse_start = now_mu() + 50000 
        # self.dds0.set_dds(frequency=self.f[0], t_phase_origin_mu=t_pulse_start, phase=0., init=True)
        # self.dds1.set_dds(frequency=self.f[1], t_phase_origin_mu=t_pulse_start, phase=0., init=True)

        self.set(self.dds0.dds_device,
                  frequency=self.f[0], 
                    amplitude=0.5,
                      phase=0.0,
                        phase_mode=1,
                        ref_time_mu=t_pulse_start)
        self.set(self.dds1.dds_device,
                  frequency=self.f[0],
                    amplitude=0.5,
                      phase=0.0,
                        phase_mode=1,
                        ref_time_mu=t_pulse_start)
        self.dds0.dds_device.cpld.io_update.pulse_mu(8)
        at_mu(now_mu() & ~7)
        self.dds0.dds_device.set_cfr1()

        at_mu(t_pulse_start)
        self.ttl1.pulse(1.e-6)

        # delay(10.e-6)
        
        # at_mu(t_pulse_start)
        # p00 = self.dds0.update_phase()/(np.pi)
        # p11 = self.dds1.update_phase()/(np.pi)

        # self.ttl1.pulse(1.e-6)

        # print(p00, p11, (p11 - p00))

    # def analyze(self):
        # print(self.t)
        # t = np.zeros_like(self.t)
        # t[1:] = np.diff(self.t)
        # print(t)
        