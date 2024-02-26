from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.control.artiq.TTL import TTL
from kexp.config import ExptParams
from artiq.experiment import kernel, delay, parallel, portable, TFloat
import numpy as np
from kexp.util.artiq.async_print import aprint

dv = -1.
dv_list = np.linspace(0.,1.,5)

V_FULLSCALE_DAC = 10.
V_SUPPLY_DEFAULT = 10.

class igbt_magnet():
    def __init__(self,
                 v_control_dac = DAC_CH, i_control_dac = DAC_CH,
                 igbt_ttl = TTL, contactor_ttl = TTL, expt_params:ExptParams = ExptParams,
                 max_current = 0., max_voltage = 0.):
        self.max_voltage = max_voltage
        self.max_current = max_current
        self.v_control_dac = v_control_dac
        self.i_control_dac = i_control_dac
        self.igbt_ttl = igbt_ttl
        self.contactor_ttl = contactor_ttl
        self.params = expt_params

    @kernel
    def load_dac(self):
        """It doesn't actually matter that we're calling the load method of a
        particular dac channel -- this calls the load method of the entire
        dac, which loads the register values to all channels.
        """        
        self.v_control_dac.load()

    @kernel
    def on(self,i_supply=0.,v_supply=V_SUPPLY_DEFAULT,contactor=False,
           wait_for_analog=False,
           pretrigger=False,
           load_dac=True):

        if contactor:
            self.open_contactor(pretrigger=pretrigger)

        self.igbt_ttl.on()
        self.set_current(i_supply,load_dac=False)
        self.set_voltage(v_supply,load_dac=False)
        if load_dac:
            self.load_dac()
        if wait_for_analog:
            delay(self.params.t_keysight_analog_response)

    @kernel
    def off(self,contactor=False,load_dac=True):

        self.igbt_ttl.off()
        self.set_current(i_supply=0.,load_dac=False)
        self.set_voltage(v_supply=0.,load_dac=False)
        if load_dac:
            self.load_dac()

        if contactor:
            self.close_contactor()

    @kernel
    def set_current(self,i_supply,load_dac=True):
        """Sets the current limit of the current supply in amps.

        Args:
            i (float): the current limit to be set in amps.
            load_dac (bool, optional): Loads the dac if true. Defaults to True.
        """        
        v_dac_current = self.supply_current_to_dac_voltage(i_supply)
        self.i_control_dac.set(v=v_dac_current,load_dac=load_dac)
        
    @kernel
    def set_voltage(self,v_supply,load_dac=True):
        v_dac_voltage = self.supply_voltage_to_dac_voltage(v_supply)
        self.v_control_dac.set(v=v_dac_voltage,load_dac=load_dac)

    @portable(flags={"fast-math"})
    def supply_current_to_dac_voltage(self,i_supply) -> TFloat:
        return (i_supply/self.max_current) * V_FULLSCALE_DAC
    
    @portable(flags={"fast-math"})
    def supply_voltage_to_dac_voltage(self,v_supply) -> TFloat:
        return (v_supply/self.max_voltage) * V_FULLSCALE_DAC
        
    @kernel
    def open_contactor(self,pretrigger=False):
        """Opens the contactor, and guarantees that the next event occurs after
        the contactor has opened.

        Args:
            pretrigger (bool, optional): Selects whether or not the event is
            pretriggered. Defaults to False.
        """        
        if pretrigger:
            delay(-self.params.t_contactor_open_delay)
        self.contactor_ttl.off()
        if pretrigger:
            delay(self.params.t_contactor_open_delay)
        else:
            delay(self.params.t_contactor_open_delay)

    @kernel
    def close_contactor(self):
        """Closes the contactor. Does not do any timeline fuckery.
        """
        self.contactor_ttl.on()
    
    @kernel
    def contactor_pulse(self,t,delay_for_complete=False,pretrigger=False):
        '''
        Closes the contactor time t. Minimum close time is t_close, otherwise
        the contactor does nothing.

        Leaves the timeline cursor at the now_mu() + t if pretriggered, or
        now_mu() + t + t_on_delay_max + t_off_delay if not.
        '''
        t_close = t
        t_on_delay_max = self.params.t_contactor_close_delay
        t_off_delay = self.params.t_contactor_open_delay
        if t_close < t_off_delay:
            aprint("pulse time is too short for the contactor, probably didn't close")
        t_ttl = t + t_on_delay_max - t_off_delay

        if pretrigger and delay_for_complete:
            delay(-t_on_delay_max)

        self.contactor_ttl.pulse(t_ttl)

        if delay_for_complete:
            if not pretrigger:
                delay(t_on_delay_max)
            delay(t_off_delay)

class hbridge_magnet(igbt_magnet):
    def __init__(self,
                 v_control_dac = DAC_CH, i_control_dac = DAC_CH,
                 hbridge_ttl = TTL, igbt_ttl = TTL, contactor_ttl = TTL,
                 expt_params = ExptParams, max_current = 0., max_voltage = 0.):
        super().__init__(v_control_dac,i_control_dac,igbt_ttl,contactor_ttl,expt_params,max_current,max_voltage)
        self.max_current = max_current
        self.max_voltage = max_voltage
        self.v_control_dac = v_control_dac
        self.i_control_dac = i_control_dac
        self.igbt_ttl = igbt_ttl
        self.contactor_ttl = contactor_ttl
        self.h_bridge_ttl = hbridge_ttl
        self.params = expt_params

    def switch_to_helmholtz(self):
        self.off()
        delay(self.params.t_hbridge_switch_delay)
        self.h_bridge_ttl.on()

    def switch_to_antihelmholtz(self):
        self.off()
        delay(self.params.t_hbridge_switch_delay)
        self.h_bridge_ttl.off()