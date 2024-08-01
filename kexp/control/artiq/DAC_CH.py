from artiq.experiment import kernel, rpc
from artiq.coredevice.zotino import Zotino

from kexp.util.artiq.async_print import aprint

dv = -10432.

class DAC_CH():
    def __init__(self,ch,dac_device=Zotino,max_v=dv):
        self.ch = ch
        self.dac_device = dac_device
        self.v = 0.
        if max_v == dv:
            self.max_v = 9.99
        else:
            self.max_v = max_v
        self.key = ""

    def set_errmessage(self):
        self.errmessage = f"Attempted to set dac ch {self.key} to a voltage > specified maximum voltage ({self.max_v:1.3f}) for that channel. DAC voltage was replaced by zero for these instances."

    @kernel
    def set(self,v=dv,load_dac=True):
        if v != dv:
            if v > self.max_v:
                self.v = 0.
                self.max_voltage_error()
            else:
                self.v = v
                
        self.dac_device.write_dac(self.ch,self.v)
        if load_dac:
            self.dac_device.load()

    @rpc(flags={'async'})
    def max_voltage_error(self):
        print(self.errmessage)

    @rpc(flags={'async'})
    def handle_dac_error(self,v):
        if ( v <= -10.) | (v >= 10.):
            print("DAC voltage must be between -10 and 10 V (noninclusive).")
        
    @kernel
    def load(self):
        self.dac_device.load()