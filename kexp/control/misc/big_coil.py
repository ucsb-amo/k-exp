from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.control.artiq.TTL import TTL_OUT
from kexp.config.expt_params import ExptParams
from artiq.experiment import kernel, delay, parallel, portable, TFloat
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.calibrations.magnets import compute_pid_overhead             

dv = -1.
di = 0
dv_list = np.linspace(0.,1.,5)

V_FULLSCALE_DAC = 10.
V_SUPPLY_DEFAULT = 70.

I_PID_OVERHEAD = 1.

T_ANALOG_DELAY = 30.e-3

@portable
def identity(x) -> TFloat:
    return x

class igbt_magnet():
    def __init__(self,
                 v_control_dac = DAC_CH, i_control_dac = DAC_CH,
                 pid_dac = DAC_CH, pid_ttl = TTL_OUT,
                 igbt_ttl = TTL_OUT, discharge_igbt_ttl = TTL_OUT,
                 expt_params:ExptParams = ExptParams(),
                 max_current = 0., max_voltage = 0.,
                 slope_current_per_vdac_supply=1.,
                 offset_current_per_vdac_supply=0.,
                 slope_current_per_vdac_pid=1.,
                 offset_current_per_vdac_pid=0.):
        
        self.max_voltage = max_voltage
        self.max_current = max_current
        self.v_control_dac = v_control_dac
        self.i_control_dac = i_control_dac
        self.pid_dac = pid_dac
        self.pid_ttl = pid_ttl
        self.igbt_ttl = igbt_ttl
        self.discharge_igbt_ttl = discharge_igbt_ttl
        self.params = expt_params
        self.i_supply = 0.
        self.i_pid = 0.

        self.slope_current_per_vdac_supply = slope_current_per_vdac_supply
        self.offset_current_per_vdac_supply = offset_current_per_vdac_supply
        self.slope_current_per_vdac_pid = slope_current_per_vdac_pid
        self.offset_current_per_vdac_pid = offset_current_per_vdac_pid

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
    def snap_off(self,discharge_igbt=False,load_dac=True):

        self.igbt_ttl.off()
        self.set_supply(i_supply=0.,load_dac=False)
        self.set_voltage(v_supply=0.,load_dac=False)
        if load_dac:
            self.load_dac()

    @kernel
    def set_supply(self,i_supply,load_dac=True):
        """Sets the actual current output of the current supply in amps.
        Corrects for discrepancy between supply set point and actual output.

        Args:
            i (float): the current limit to be set in amps.
            load_dac (bool, optional): Loads the dac if true. Defaults to True.
        """        
        v_dac_current = self.current_to_supply_vdac(i_supply)
        self.i_control_dac.set(v=v_dac_current,load_dac=load_dac)
        self.i_supply = i_supply

    @kernel
    def set_pid(self,i_pid,load_dac=True):
        """Sets the PID set point to the given current.

        Args:
            i_pid (float): The desired current in A.
            load_dac (bool, optional): Loads the dac if true. Defaults to True.
        """        
        v_pid = self.current_to_pid_vdac(i_pid)
        self.pid_dac.set(v=v_pid,load_dac=load_dac)
        self.i_pid = i_pid
        
    @kernel
    def set_voltage(self,v_supply=V_SUPPLY_DEFAULT,load_dac=True):
        v_dac_voltage = self.supply_voltage_to_dac_voltage(v_supply)
        self.v_control_dac.set(v=v_dac_voltage,load_dac=load_dac)

    @portable(flags={"fast-math"})
    def current_to_pid_vdac(self,i) -> TFloat:
        return (i - self.offset_current_per_vdac_pid) / self.slope_current_per_vdac_pid
    
    @portable(flags={"fast-math"})
    def pid_vdac_to_current(self,v) -> TFloat:
        return self.slope_current_per_vdac_pid * v + self.offset_current_per_vdac_pid

    @portable(flags={"fast-math"})
    def current_to_supply_vdac(self,i) -> TFloat:
        return (i - self.offset_current_per_vdac_supply) / self.slope_current_per_vdac_supply
    
    @portable(flags={"fast-math"})
    def supply_vdac_to_current(self,v) -> TFloat:
        return self.slope_current_per_vdac_supply * v + self.offset_current_per_vdac_supply
    
    @portable(flags={"fast-math"})
    def supply_voltage_to_dac_voltage(self,v_supply) -> TFloat:
        return (v_supply/self.max_voltage) * V_FULLSCALE_DAC
    
    @kernel(flags={"fast-math"})
    def ramp_supply(self,t,i_start=dv,i_end=0.,n_steps=di,t_analog_delay=T_ANALOG_DELAY):
        """Ramps the supply current from i_start to i_end in n_steps over time t
        using the supply current set point. If no i_start is provided, defaults
        to the last current the supply was set to.

        Args:
            t (float): The time of the ramp.
            i_start (float, optional): The current at the start of the ramp.
            Defaults to the attribute `i_current`, which corresponds to the last
            current the supply was set to.
            i_end (float, optional): The current at the end of the ramp. Defaults to 0.
            n_steps (int, optional): The number of steps. Defaults to
            ExptParams.n_field_ramp_steps.
            t_analog_delay (float, optional): the time delay of the current
            supply in response to analog changes. Defaults to T_ANALOG_DELAY.
        """        
        if n_steps == di:
            n_steps = self.params.n_field_ramp_steps
        if i_start == dv:
            i_start = self.i_supply
        else:
            self.i_supply = i_start
        if i_end == dv:
            i_end = 0.

        v_start = self.current_to_supply_vdac(i_start)
        v_end = self.current_to_supply_vdac(i_end)

        self.i_control_dac.linear_ramp(t,v_start,v_end,n_steps)
        delay(t_analog_delay)
        self.i_supply = i_end

    @kernel(flags={"fast-math"})
    def ramp_pid(self,t,i_start=dv,i_end=0.,n_steps=di):
        """Ramps the supply current from i_start to i_end in n_steps over time t
        using the current PID. If no i_start is provided, defaults to the last
        current the supply was set to.

        Args:
            t (float): The time of the ramp.
            i_start (float, optional): The current at the start of the ramp.
            Defaults to the attribute `i_current`, which corresponds to the last
            current the supply was set to.
            i_end (float, optional): The current at the end of the ramp. Defaults to 0.
            n_steps (int, optional): The number of steps. Defaults to
            ExptParams.n_field_ramp_steps.
            t_analog_delay (float, optional): the time delay of the current
            supply in response to analog changes. Defaults to T_ANALOG_DELAY.
        """        
        if n_steps == di:
            n_steps = self.params.n_field_ramp_steps
        if i_start == dv:
            i_start = self.i_pid
        else:
            self.i_pid = i_start
        if i_end == dv:
            i_end = 0.
        v_start = self.current_to_pid_vdac(i_start)
        v_end = self.current_to_pid_vdac(i_end)
        self.pid_dac.linear_ramp(t,v_start,v_end,n_steps)
        self.i_pid = i_end

    @kernel
    def start_pid(self, i_pid=dv, overhead=True):
        """Starts the PID, then sets the supply with some current overhead for
        the PID to eat.

        Args:
            i_pid (float, optional): The desired current in A. Defaults to the
            current value of the supply output (as measured by the coil
            transducer).
            overhead (bool, optional): Whether or not to ramp up the current
            supply set point after engaging the PID in order to put the mosfet
            gate-source voltage at a predetermined value for optimum PID
            performance.
        """        
        ##note for setting coils with the new subtract PID method
        ##the PID target value should only take the target current as a paremeter,
        ##but it will be a function of the gain of the SR560 box, which is default 100, but perhaps artiq should know
        ##what that gain is/be able to set it
        ##

        if i_pid == dv:
            i_pid = self.i_supply

        t_ramp = 50.e-3
        n_steps = 50

        self.set_pid(i_pid)
        self.pid_ttl.on()

        i_start = i_pid
        if overhead:
            i_end = self.i_pid + compute_pid_overhead(self.i_pid)
            delta_i = (i_end - i_start)/(n_steps-1)
            dt = t_ramp / n_steps
            for j in range(n_steps):
                self.set_supply( i_start + delta_i * j )
                delay(dt)
        else:
            self.set_supply(i_start)
            delay(t_ramp)
        delay(T_ANALOG_DELAY)

    @kernel
    def stop_pid(self, i_supply=dv):
        """Brings the supply set point back in line with the desired current,
        then stops the PID.

        Args:
            i_supply (float, optional): The desired current in A. Defaults to the
            current pid current set point.
        """        
        if i_supply == dv:
            i_supply = self.i_pid
        self.set_supply(i_supply)
        delay(T_ANALOG_DELAY)
        self.pid_ttl.off()

    @kernel(flags={"fast-math"})
    def rampdown(self,t_rampdown=50.e-3):
        """Ramps the coils to off from the current set point.
        """       
        self.pid_ttl.off()
        self.ramp_supply(t=t_rampdown,
                  i_start=self.i_supply,
                  i_end=0.,
                  n_steps=100)
        self.set_voltage(0.)
        delay(T_ANALOG_DELAY)

    @kernel
    def discharge(self):
        """Closes the coil contacts, makes sure the set points are zero, and
        waits for any charge to dissipate.
        """        
        self.on()
        self.set_supply(0.)
        self.set_voltage(0.)
        delay(T_ANALOG_DELAY)
        delay(100.e-3)
        self.igbt_ttl.off()

    @kernel
    def off(self):
        self.ramp_supply(t=10.e-3, i_end=self.i_pid)
        self.rampdown()
        self.igbt_ttl.off()
        self.pid_ttl.off()
        delay(5.e-3)
        self.discharge()
        
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

class hbridge_magnet(igbt_magnet):
    def __init__(self,
                 v_control_dac = DAC_CH, i_control_dac = DAC_CH,
                 pid_dac = DAC_CH, pid_ttl = TTL_OUT,
                 hbridge_ttl = TTL_OUT, igbt_ttl = TTL_OUT, discharge_igbt_ttl = TTL_OUT,
                 expt_params = ExptParams, max_current = 0., max_voltage = 0.,
                 slope_current_per_vdac_supply=1.,
                 offset_current_per_vdac_supply=0.,
                 slope_current_per_vdac_pid=1.,
                 offset_current_per_vdac_pid=0.):
        super().__init__(v_control_dac,
                         i_control_dac,
                         pid_dac,pid_ttl,
                         igbt_ttl,discharge_igbt_ttl,
                         expt_params,
                         max_current,max_voltage,
                         slope_current_per_vdac_supply,
                         offset_current_per_vdac_supply,
                         slope_current_per_vdac_pid,
                         offset_current_per_vdac_pid)
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