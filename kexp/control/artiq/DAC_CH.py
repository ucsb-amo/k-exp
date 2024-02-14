from artiq.experiment import kernel, rpc
from artiq.coredevice.zotino import Zotino

dv = -100.

class DAC_CH():
    def __init__(self,ch,dac_device=Zotino):
        self.ch = ch
        self.dac_device = dac_device
        self.v = 0.
        self.key = ""

    @kernel
    def set(self,v=dv,load_dac=True):
        if v != dv:
            self.v = v
        self.dac_device.write_dac(self.ch,float(self.v))
        if load_dac:
            self.dac_device.load()

    @rpc(flags={'async'})
    def handle_dac_error(self,v):
        if ( v <= -10.) | (v >= 10.):
            raise ValueError("DAC voltage must be between -10 and 10 V (noninclusive).")