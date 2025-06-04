from artiq.experiment import delay, kernel
from artiq.experiment import *

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu
import numpy as np

T16 = 1 << 16
T32 = 1 << 32
T48 = 1 << 48
T64 = 1 << 64

class Shuttler_CH():
    def __init__(self,ch,shuttler_idx=0,relay_state=np.zeros(16)):
        self.ch = ch
        self.shuttler_idx = shuttler_idx
        self._name = f'shuttler{shuttler_idx}ch{ch}'

        self._dc_name = f'shuttler{shuttler_idx}_dcbias{ch}'
        self._dds_name = f'shuttler{shuttler_idx}_dds{ch}'
        self._relay_name = f'shuttler{shuttler_idx}_relay'
        self._trigger = f'shuttler{shuttler_idx}_trigger'

        self._dc = []
        self._dds = []
        self._relay = []
        self._trigger = []

        self._dc: DCBias
        self._dds: DDS
        self._relay: Relay
        self._trigger: Trigger

        self._relay_state = relay_state
        self._STATE_BASE = np.array([1 << n for n in range(16)])

        self._ch_relay_state = self._relay_state[ch]

    @kernel
    def _relay_state_to_int(self):
        return self._STATE_BASE @ self._relay_state
    
    @kernel
    def _update_ch_relay_state(self):
        self._ch_relay_state = self._relay_state[self.ch]

    @kernel
    def on(self):
        if not self._ch_relay_state:
            self._relay_state[self.ch] = 1
            state_int = self._relay_state_to_int()
            self._relay.enable(en=state_int)
            self._update_ch_relay_state()

    @kernel
    def off(self):
        if self._ch_relay_state:
            self._relay_state[self.ch] = 0
            state_int = self._relay_state_to_int()
            self._relay.enable(en=state_int)
            self._update_ch_relay_state()

    @kernel
    def trigger(self):
        self._trigger.trigger(trig_out=(1 << self.ch))
    
    @portable
    def compute_coeffs_dc(self,p0,p1,p2,p3):
        """
        Computes the arguments for the DC bias spline. 
        The DC bias spline is of the form:
        
        V(t) = a(t), where
        
        a(t) = p0 + p1*t + p2*t**2 + p3*t**3

        See the ARTIQ manual for details.
        (https://m-labs.hk/artiq/manual/core_drivers_reference.html#artiq.coredevice.shuttler.DCBias)
        """
        T = 8.e-9
        a0 = round( p0 * T16 / 20 ) & 0xffff
        a1 = round( (p1 * T + p2 * T**2 / 2 + p3 * T**3 / 6) * T32 / 20 ) & 0xffffffff
        a2 = round( (p2 * T**2 + p3 * T**3) * T48 / 20 ) & 0xffffffffffff
        a3 = round( (p3 * T**3) * T48 / 20 ) & 0xffffffffffff
        return a0, a1, a2, a3
    
    @portable
    def compute_coeffs_dds(self,n0,n1,n2,n3,r0,r1,r2):
        """
        Computes the arguments for the DDS spline.
        The DDS spline is of the form:
        
        V(t) = b(t) * cos( c(t) ), where
        
        b(t) = g * ( q0 + q1*t + q2*t**2 + q3*t**3 ) = n0 + n1*t + n2*t**2 + n3*t**3
        c(t) = r0 + r1*t + r2*t**2

        where g = 1.64676, and where we've defined the coefficients ni as:
        n0 = g*q0, n1 = g*q1, n2 = g*q2, n3 = g*q3

        See the ARTIQ manual for details.
        (https://m-labs.hk/artiq/manual/core_drivers_reference.html#artiq.coredevice.shuttler.DCBias)
        """
        T = 8.e-9
        g = 1.64676
        q0 = n0/g
        q1 = n1/g
        q2 = n2/g
        q3 = n3/g
        
        b0 = round(q0 * T16 / 20) & 0xffff
        b1 = round((q1 * T + q2 * T**2 / 2 + q3 * T**3 / 6) * T32 / 20) & 0xffffffff
        b2 = round((q2 * T**2 + q3 * T**3) * T48 / 20) & 0xffffffffffff
        b3 = round((q3 * T**3) * T48 / 20) & 0xffffffffffff

        c0 = round( r0 * T16 ) & 0xffff
        c1 = round( (r1 * T + r2 * T**2) * T32) & 0xffffffff
        c2 = round( (r2 * T**2) * T32 ) & 0xffffffff

        return b0, b1, b2, b3, c0, c1, c2
    
    @kernel
    def set_waveform_dc(self,p0=0.,p1=0.,p2=0.,p3=0.,trigger=True):
        '''
        The DC bias spline is of the form:
        
        V(t) = a(t), where
        
        a(t) = p0 + p1*t + p2*t**2 + p3*t**3
        '''
        a0, a1, a2, a3 = self.compute_coeffs_dc(p0,p1,p2,p3)
        self._dc.set_waveform(a0=a0,a1=a1,a2=a2,a3=a3)
        if trigger:
            self._trigger.trigger(1 << self.ch)

    @kernel
    def set_waveform_dds(self,n0=0.,n1=0.,n2=0.,n3=0.,r0=0.,r1=0.,r2=0.,trigger=True):
        '''
        The DDS spline is of the form:
        
        V(t) = b(t) * cos( c(t) ), where
        
        b(t) = g * ( q0 + q1*t + q2*t**2 + q3*t**3 ) = n0 + n1*t + n2*t**2 + n3*t**3
        c(t) = r0 + r1*t + r2*t**2
        '''
        b0, b1, b2, b3, c0, c1, c2 = self.compute_coeffs_dds(n0,n1,n2,n3,r0,r1,r2)
        self._dds.set_waveform(b0=b0, b1=b1, b2=b2, b3=b3, c0=c0, c1=c1, c2=c2)
        if trigger:
            self._trigger.trigger(1 << self.ch)

    @kernel
    def set_waveform(self,
                     p0=0.,p1=0.,p2=0.,p3=0.,
                     n0=0.,n1=0.,n2=0.,n3=0.,
                     r0=0.,r1=0.,r2=0.,
                     trigger=True):
        self.set_waveform_dc(p0=p0,p1=p1,p2=p2,p3=p3)
        self.set_waveform_dds(n0=n0,n1=n1,n2=n2,n3=n3,r0=r0,r1=r1,r2=r2)
        if trigger:
            self._trigger.trigger(1 << self.ch)

    @kernel
    def linear_ramp(self,
                    t,v_start,v_end,
                    dwell_end=True):
        slope = (v_end - v_start) / t
        if dwell_end: 
            vf = v_end
        else: 
            vf = v_start
        self.set_waveform_dc(p0=v_start,p1=slope)
        self.on()
        self.set_waveform_dc(p0=vf,p1=0.,trigger=False)
        delay(t)
        self.trigger()

    @kernel
    def sine(self,
             frequency,
             v_amplitude,
             v_offset=0.,
             trigger_bool=True):
        if v_offset:
            self.set_waveform_dc(p0=v_offset,trigger=True)
        self.set_waveform_dds(n0=v_amplitude, r1=frequency, trigger=trigger_bool)
        self.on()

    @kernel
    def dc(self,
             v_dc,
             trigger_bool=True):
        self.set_waveform(p0=v_dc, trigger=trigger_bool)
        self.on()