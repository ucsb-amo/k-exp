from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.control.artiq.TTL import TTL
from kexp.control.artiq.DDS import DDS
from kexp.calibrations import tweezer as tweezer_calibrations
from kexp.config import ExptParams
from kexp.util.artiq.async_print import aprint
from artiq.language.core import now_mu
from artiq.coredevice.core import Core
from artiq.experiment import rpc
import spcm
from spcm import units

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

from artiq.experiment import kernel, delay, parallel, TFloat, portable

import numpy as np

# di = 666420695318008 #causes failure
di = 0
dv = -1000.
dv_list = np.linspace(0.,1.,5)

class tweezer():
    def __init__(self,
                  ao1_dds=DDS, pid1_dac=DAC_CH, 
                  ao2_dds=DDS, pid2_dac=DAC_CH,
                  sw_ttl=TTL,
                  awg_trg_ttl=TTL,
                  pid1_int_hold_zero_ttl=TTL,
                  pid2_enable_ttl=TTL,
                  painting_dac=DAC_CH,
                  expt_params=ExptParams,
                  core=Core):
        """Controls the tweezers.

        Args:
            sw_ttl (TTL): TTL
            awg_trg_ttl (TTL): TTL
        """        
        self.ao1_dds = ao1_dds
        self.pid1_dac = pid1_dac
        self.ao2_dds = ao2_dds
        self.pid2_dac = pid2_dac
        self.sw_ttl = sw_ttl
        self.awg_trg_ttl = awg_trg_ttl
        self.pid1_int_hold_zero = pid1_int_hold_zero_ttl
        self.pid2_enable_ttl = pid2_enable_ttl
        self.paint_amp_dac = painting_dac
        self.params = expt_params
        self._awg_ip = 'TCPIP::192.168.1.83::inst0::INSTR'
        self.core = core

    @kernel
    def on(self,paint=False,v_awg_am=dv):
        if v_awg_am == dv:
            v_awg_am = self.params.v_tweezer_paint_amp_max

        self.pid1_dac.set(v=.0)
        delay(300.e-6)
        self.ao2_dds.on()

        if paint:
            self.paint_amp_dac.set(v=v_awg_am)
        else:
            self.paint_amp_dac.set(v=-7.)
        with parallel:
            self.ao1_dds.on()
            self.sw_ttl.on()
            self.pid1_int_hold_zero.pulse(1.e-6)

    @kernel
    def off(self):
        self.ao1_dds.off()
        self.ao2_dds.off()
        self.pid1_int_hold_zero.on()
        self.pid1_dac.set(v=0.)
        self.pid2_enable_ttl.off()
        self.sw_ttl.off()

    @kernel 
    def pulse(self,t=1.e-6):
        self.awg_trg_ttl.on()
        delay(t)
        self.awg_trg_ttl.off()

    @kernel
    def set_power(self,v_pd=dv,load_dac=True):
        if v_pd == dv:
            v_pd = self.params.v_pd_tweezer_1064
        self.pid1_dac.set(v=v_pd,load_dac=load_dac)

    @kernel(flags={"fast-math"})
    def ramp(self,t,
             v_start=dv,
             v_end=dv,
             n_steps=di,
             paint=False,
             v_awg_am_max=dv,
             v_pd_max=dv,
             keep_trap_frequency_constant=True,
             low_power=False):
        """Ramps the voltage that controls the tweezer power according to v_ramp_list.
        
        If painting is enabled, paints the tweezer by controlling the amplitude
        of the FM source waveform, which in turn controls the FM modulation
        depth.

        Args:
            t (float): The ramp time.

            v_ramp_list (nd.nparray(float), optional): The list of voltages to
            be ramped. This should be the voltage that controls the tweezer
            power. Defaults to ExptParams.v_pd_tweezer_1064_ramp_list.

            v_awg_am_max (float, optional): The voltage that corresponds to the
            maximum desired painting amplitude. Defaults to
            ExptParams.v_tweezer_paint_amp_max.

            v_pd_max (float, optional): The voltage corresponding to the maximum
            tweezer power used during the ramp. The trap frequency at this power
            and at maximum painting amplitude is the one which is kept constant
            if keep_trap_frequency_constant == True. Defaults to
            ExptParams.v_pd_tweezer_1064_ramp_end (the endpoint of the ramp up).

            paint (bool, optional): If True, enables painting. If False, sets
            the paint amplitude control voltage to -7., which should disable
            painting entirely. Defaults to False.

            keep_trap_frequency_constant (bool, optional): If True, the painting
            amplitude will be adjusted along with the tweezer power in order to
            keep the trap frequency constant, and equal to the trap frequency at
            maximum power (v_pd_max) and maximum painting amplitude
            (v_awg_am_max). Defaults to True.
        """        

        if v_start == dv:
            v_start = 0.
        if v_end == dv:
            v_end = self.params.v_pd_tweezer_1064_ramp_end
        if n_steps == di:
            n_steps = self.params.n_tweezer_ramp_steps
        if v_awg_am_max == dv:
            v_awg_am_max = self.params.v_tweezer_paint_amp_max
        if v_pd_max == dv:
            v_pd_max = self.params.v_pd_tweezer_1064_ramp_end

        dt_ramp = t / n_steps
        delta_v = (v_end - v_start)/(n_steps - 1)

        if low_power:
            pid_dac = self.pid2_dac
            v_pd_max = tweezer_vpd1_to_vpd2(v_awg_am_max)
        else:
            pid_dac = self.pid1_dac

        if not paint:
            self.painting_off()

        pid_dac.set(v=v_start)
        if low_power:
            self.pid2_enable_ttl.on()
        else:
            self.pid2_enable_ttl.off()
        for i in range(n_steps):
            v = v_start + i * delta_v
            if paint:
                if keep_trap_frequency_constant:
                    v_awg_amp_mod = self.v_pd_to_painting_amp_voltage(v,v_pd_max)
                else:
                    v_awg_amp_mod = v_awg_am_max
                self.paint_amp_dac.set(v_awg_amp_mod,load_dac=False)
            pid_dac.set(v=v,load_dac=True)
            delay(dt_ramp)

    @portable
    def v_pd_to_painting_amp_voltage(self,v_pd=dv,
                                        v_pd_max=dv,
                                        v_awg_am_max=dv) -> TFloat:
        if v_awg_am_max == dv:
            v_awg_am_max = self.params.v_tweezer_paint_amp_max

        if v_pd_max == dv:
            v_pd_max = self.params.v_pd_tweezer_1064_ramp_end

        p_frac = v_pd / v_pd_max
        # trap frequency propto sqrt( P / h^3 ), where P is power and h is painting
        # amplitude. To keep constant frequency, h should decrease by a factor equal
        # to the cube root of the fraction by which P changes
        paint_amp_frac = p_frac**(1/3)
        # rescale to between -6V (fraction painting = 0) and the maximum
        # painting amplitude specified (fraction painting = 1) for the
        # AWG input
        v_awg_amp_mod = (paint_amp_frac - 0.5)*(v_awg_am_max - (-6)) \
                            + (v_awg_am_max + (-6))/2
        return v_awg_amp_mod
        

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
        self.dds = spcm.DDSCommandList(self.card)
        self.dds.reset()

        self.dds.data_transfer_mode(spcm.SPCM_DDS_DTM_DMA)
        self.dds.mode = self.dds.WRITE_MODE.WAIT_IF_FULL

        self.dds.trg_src(spcm.SPCM_DDS_TRG_SRC_CARD)

        # thanks jp
        self.core_list = [hex(2**n) for n in range(20)]

        # assign dds cores to channel
        # self.dds.cores_on_channel(1, *self.core_list)

        self.dds.write_to_card()

        # Start command including enable of trigger engine
        self.card.start(spcm.M2CMD_CARD_ENABLETRIGGER)

    def set_static_tweezers(self, freq_list, amp_list, phase_list):
        """_summary_

        Args:
            freq_list (nd array): array of frequencies in Hz
            amp_list (nd array): array of amplitudes (min=0, max=1)

        Raises:
            ValueError: _description_
        """
        if isinstance(freq_list,float):
            print('is a float!')
            freq_list = [freq_list]
        
        if len(freq_list) != len(amp_list):
            raise ValueError('Amplitude and frequency lists are not of equal length')

        for tweezer_idx in range(len(self.core_list)):
            if tweezer_idx < len(freq_list):
                self.dds[tweezer_idx].amp(amp_list[tweezer_idx])
                self.dds[tweezer_idx].freq(freq_list[tweezer_idx])
                self.dds[tweezer_idx].phase(phase_list[tweezer_idx])
            else:
                pass
        self.dds.exec_at_trg()
        self.dds.write()

    def cubic_move(self,t,total_distance,total_time):
            A = -2*total_distance / total_time**3
            B = 3*total_distance / total_time**2
            return A*t**3 + B*t**2

    def write_movement(self,which_tweezer,distance,time):

        # tweezer movement calibrations in meter / MHz
        cat_eye_xpf = tweezer_calibrations.cat_eye_xpf
        non_cat_eye_xpf = tweezer_calibrations.non_cat_eye_xpf

        if self.params.frequency_tweezer_list[which_tweezer] < 75.e6:
            dpf = cat_eye_xpf
        else:
            dpf = non_cat_eye_xpf

        # how many steps?
        # n_steps = self.params.n_steps_tweezer_move

        # time per step
        self.dt = self.params.t_tweezer_movement_dt

        # generate array of slopes
        self.slopes = np.zeros([int(time/self.dt)],dtype=float)
        self.zero_array = np.array([0])

        for step in range(1,int(time/self.dt)):
                self.slopes[step-1] = (self.cubic_move(self.dt*(step),distance,time) - self.cubic_move(self.dt*(step-1),distance,time)) / (self.dt*dpf)  
        self.slopes = np.concatenate([self.slopes,self.zero_array])

        self.dds.trg_src(spcm.SPCM_DDS_TRG_SRC_TIMER)
        self.dds.trg_timer(self.dt)
        self.dds.exec_at_trg()
        self.dds.write()

        for slope in self.slopes:
            self.dds.frequency_slope(which_tweezer,slope)
            self.dds.exec_at_trg()
        self.dds.write()

        self.dds.trg_src(spcm.SPCM_DDS_TRG_SRC_CARD)
        self.dds.exec_at_trg()
        self.dds.write()
        
        # self.dds.trg_src(spcm.SPCM_DDS_TRG_SRC_TIMER)
        # self.dds.trg_timer(self.dt)
        # self.dds.exec_at_trg()
        # self.dds.write_to_card()

        # for slope in self.slopes:
        #     self.dds.frequency_slope(which_tweezer,slope)
        #     self.dds.exec_at_trg()

        # self.dds.write_to_card()
        
        # self.dds.trg_src(spcm.SPCM_DDS_TRG_SRC_CARD)
        # self.dds.exec_at_trg()
        # self.dds.write_to_card()

    @rpc(flags={"async"})
    def write_to_awg_rpc(self,twz_idx,distance,time):
        self.write_movement(twz_idx,distance,time)
        pass

    @kernel
    def write_to_awg(self,twz_idx,distance,time):
        self.core.wait_until_mu(now_mu())
        self.write_to_awg_rpc(twz_idx,distance,time)
        self.core.break_realtime()
        delay(100.e-3)
        
    @kernel
    def move_tweezer(self,twz_idx,distance,time,awg_write_bool=True):
        if awg_write_bool:
            self.write_to_awg(twz_idx,distance,time)
        self.awg_trg_ttl.pulse(1.e-6)
        delay(time)

    def sinusoidal_modulation(self,t,amplitude,frequency):
        return amplitude*np.sin(2*np.pi*frequency*t)
    
    def reset_awg(self):
        self.dds.reset()