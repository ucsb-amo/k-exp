from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.control.artiq.TTL import TTL
from kexp.config import ExptParams
from artiq.experiment import kernel, delay, parallel, portable, TFloat
import numpy as np
from kexp.util.artiq.async_print import aprint

dv = -1.
dv_list = np.linspace(0.,1.,5)

V_FULLSCALE_DAC = 10.
V_SUPPLY_DEFAULT = 70.

T_ANALOG_DELAY = 30.e-3

class igbt_magnet():
    def __init__(self,
                 v_control_dac = DAC_CH, i_control_dac = DAC_CH,
                 igbt_ttl = TTL, discharge_igbt_ttl = TTL, expt_params:ExptParams = ExptParams,
                 max_current = 0., max_voltage = 0.):
        self.max_voltage = max_voltage
        self.max_current = max_current
        self.v_control_dac = v_control_dac
        self.i_control_dac = i_control_dac
        self.igbt_ttl = igbt_ttl
        self.discharge_igbt_ttl = discharge_igbt_ttl
        self.params = expt_params

    @kernel
    def load_dac(self):
        """It doesn't actually matter that we're calling the load method of a
        particular dac channel -- this calls the load method of the entire
        dac, which loads the register values to all channels.
        """        
        self.v_control_dac.load()

    @kernel
    def on(self):
        self.igbt_ttl.on()

    @kernel
    def off(self,discharge_igbt=False,load_dac=True):

        self.igbt_ttl.off()
        self.set_current(i_supply=0.,load_dac=False)
        self.set_voltage(v_supply=0.,load_dac=False)
        if load_dac:
            self.load_dac()

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
    def set_voltage(self,v_supply=V_SUPPLY_DEFAULT,load_dac=True):
        v_dac_voltage = self.supply_voltage_to_dac_voltage(v_supply)
        self.v_control_dac.set(v=v_dac_voltage,load_dac=load_dac)

    @portable(flags={"fast-math"})
    def supply_current_to_dac_voltage(self,i_supply) -> TFloat:
        return (i_supply/self.max_current) * V_FULLSCALE_DAC
    
    @portable(flags={"fast-math"})
    def supply_voltage_to_dac_voltage(self,v_supply) -> TFloat:
        return (v_supply/self.max_voltage) * V_FULLSCALE_DAC
    
    @kernel(flags={"fast-math"})
    def ramp(self,t,i_start,i_end,n_steps=dv,t_analog_delay=T_ANALOG_DELAY):
        if n_steps == dv:
            n_steps = self.params.n_field_ramp_steps
        v_start = self.supply_current_to_dac_voltage(i_start)
        v_end = self.supply_current_to_dac_voltage(i_end)
        self.i_control_dac.linear_ramp(t,v_start,v_end,n_steps)
        delay(t_analog_delay)
        
    # @kernel
    # def open_discharge_igbt(self):
    #     """Opens the discharge_igbt.
    #     """
    #     self.discharge_igbt_ttl.off()

    # @kernel
    # def close_discharge_igbt(self):
    #     """Closes the discharge_igbt. Does not do any timeline fuckery.
    #     """
    #     self.discharge_igbt_ttl.on()
    
    # @kernel
    # def discharge_igbt_pulse(self,t):
    #     self.discharge_igbt_ttl.pulse(t)

    @kernel
    def discharge(self):
        self.on()
        self.set_current(0.)
        self.set_voltage(0.)
        delay(T_ANALOG_DELAY)
        self.off()

class hbridge_magnet(igbt_magnet):
    def __init__(self,
                 v_control_dac = DAC_CH, i_control_dac = DAC_CH,
                 hbridge_ttl = TTL, igbt_ttl = TTL, discharge_igbt_ttl = TTL,
                 expt_params = ExptParams, max_current = 0., max_voltage = 0.):
        super().__init__(v_control_dac,i_control_dac,igbt_ttl,discharge_igbt_ttl,expt_params,max_current,max_voltage)
        self.max_current = max_current
        self.max_voltage = max_voltage
        self.v_control_dac = v_control_dac
        self.i_control_dac = i_control_dac
        self.igbt_ttl = igbt_ttl
        self.discharge_igbt_ttl = discharge_igbt_ttl
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