from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.control.artiq.TTL import TTL
from kexp.control.artiq.DDS import DDS
from kexp.config import ExptParams
from kexp.util.artiq.async_print import aprint
import spcm
from spcm import units

from artiq.experiment import kernel, delay

import numpy as np

dv = -1000.
dv_list = np.linspace(0.,1.,5)

class tweezer():
    def __init__(self, ao_dds:DDS, vva_dac:DAC_CH, sw_ttl:TTL,
                  awg_trg_ttl:TTL, pid_int_hold_zero_ttl:TTL,
                  painting_dac:DAC_CH,
                  expt_params:ExptParams):
        """Controls the tweezers.

        Args:
            sw_ttl (TTL): TTL
            awg_trg_ttl (TTL): TTL
        """        
        self.ao_dds = ao_dds
        self.vva_dac = vva_dac
        self.sw_ttl = sw_ttl
        self.awg_trg_ttl = awg_trg_ttl
        self.pid_int_hold_zero = pid_int_hold_zero_ttl
        self.paint_amp_dac = painting_dac
        self.params = expt_params
        self._awg_ip = 'TCPIP::192.168.1.83::inst0::INSTR'

    @kernel
    def on(self,painting=False,v_awg_am=dv):
        if v_awg_am == dv:
            v_awg_am = self.params.v_awg_am_fixed_paint_amplitude

        self.vva_dac.set(v=.0)
        if painting:
            self.paint_amp_dac.set(v=v_awg_am)
        with parallel:
            self.ao_dds.on()
            self.sw_ttl.on()
            self.pid_int_hold_zero.pulse(1.e-6)

    @kernel
    def off(self):
        self.ao_dds.off()
        self.pid_int_hold_zero.on()
        self.vva_dac.set(v=0.)
        self.sw_ttl.off()

    @kernel 
    def pulse(self,t=1.e-6):
        self.awg_trg_ttl.on()
        delay(t)
        self.awg_trg_ttl.off()

    @kernel
    def set_power(self,v_tweezer_vva=dv,load_dac=True):
        if v_tweezer_vva == dv:
            v_tweezer_vva = self.params.v_pd_tweezer_1064
        self.vva_dac.set(v=v_tweezer_vva,load_dac=load_dac)

    @kernel
    def ramp(self,t,v_ramp_list=dv_list,
             v_awg_am_max=dv,painting=False,
             keep_trap_frequency_constant=True):

        v_pd_max = self.params.v_pd_tweezer_1064_ramp_end

        if v_ramp_list == dv_list:
            v_ramp_list = self.params.v_pd_tweezer_1064_ramp_list

        if v_awg_am_max == dv:
            v_awg_am_max = self.params.v_tweezer_paint_amp_max

        n_ramp = len(v_ramp_list)
        dt_ramp = t / n_ramp

        # prep an array of the same length
        v_awg_amp_mod_list = self.params.v_pd_tweezer_1064_ramp_list

        if not painting:
            self.paint_amp_dac.set(v=-7.)
        else:
            if not keep_trap_frequency_constant:
                # prep an empty list of just ones
                v_awg_amp_mod_list[:] = v_awg_am_max
            else:
                # convert your list of vpds (propto trap power) to fractional power
                p_frac_list = v_ramp_list / v_pd_max
                # trap frequency propto sqrt( P / h^3 ), where P is power and h is painting
                # amplitude. To keep constant frequency, h should decrease by a factor equal
                # to the cube root of the fraction by which P changes
                paint_amp_frac_list = p_frac_list**(1/3)
                # rescale to between -6V (fraction painting = 0) and the maximum
                # painting amplitude specified (fraction painting = 1) for the
                # AWG input
                v_awg_amp_mod_list = (paint_amp_frac_list - 0.5)*(v_awg_am_max - (-6)) + (v_awg_am_max + (-6))/2

        # for v in v_ramp_list:
        for i in range(n_ramp):
            self.vva_dac.set(v=v_ramp_list[i],load_dac=False)
            if painting:
                self.paint_amp_dac.set(v=v_awg_amp_mod_list[i],load_dac=False)
            self.vva_dac.load()
            delay(dt_ramp)

    @kernel
    def static_modulated_ramp(self,t,v_ramp_list=dv_list,v_awg_am=dv):
        if v_ramp_list == dv_list:
            v_ramp_list = self.params.v_pd_tweezer_1064_ramp_list

        if v_awg_am == dv:
            v_awg_am = self.params.v_awg_am_fixed_paint_amplitude

        n_ramp = len(v_ramp_list)
        dt_ramp = t / n_ramp

        for v in v_ramp_list:
            self.vva_dac.set(v=v)
            delay(dt_ramp)

    @kernel
    def painting_off(self):
        self.paint_amp_dac.set(v=-7.)
    
    def awg_init(self):

        self.card = spcm.Card(self._awg_ip)

        self.card.open(self._awg_ip)

        # self.card.reset()

        # setup card for DDS
        self.card.card_mode(spcm.SPC_REP_STD_DDS)

        # Setup the channels
        channels = spcm.Channels(self.card)
        channels.enable(True)
        channels.output_load(50 * units.ohm)
        channels.amp(1. * units.V)
        self.card.write_setup()

        # trigger mode
        trigger = spcm.Trigger(self.card)
        trigger.or_mask(spcm.SPC_TMASK_EXT0) # disable default software trigger
        trigger.ext0_mode(spcm.SPC_TM_POS) # positive edge
        trigger.ext0_level0(1.5 * units.V) # Trigger level is 1.5 V (1500 mV)
        trigger.ext0_coupling(spcm.COUPLING_DC) # set DC coupling
        self.card.write_setup()

        # Setup DDS functionality
        self.dds = spcm.DDS(self.card, channels=channels)
        self.dds.reset()

        self.dds.trg_src(spcm.SPCM_DDS_TRG_SRC_CARD)

        # thanks jp
        self.core_list = [hex(2**n) for n in range(20)]

        # assign dds cores to channel
        # self.dds.cores_on_channel(1, *self.core_list)

        # Start command including enable of trigger engine
        self.card.start(spcm.M2CMD_CARD_ENABLETRIGGER)

    def set_static_tweezers(self, freq_list, amp_list):
        """_summary_

        Args:
            freq_list (nd array): array of frequencies in Hz
            amp_list (nd array): array of amplitudes (min=0, max=1)

        Raises:
            ValueError: _description_
        """

        if len(freq_list) != len(amp_list):
            raise ValueError('Amplitude and frequency lists are not of equal length')

        for tweezer_idx in range(len(self.core_list)):
            if tweezer_idx < len(freq_list):
                self.dds[tweezer_idx].amp(amp_list[tweezer_idx])
                self.dds[tweezer_idx].freq(freq_list[tweezer_idx])
            else:
                pass
        self.dds.exec_at_trg()
        
        self.dds.write_to_card()

    # def close(self):
    #     self.card.close(self.card._handle)