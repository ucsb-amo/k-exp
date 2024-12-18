import vxi11
from artiq.experiment import kernel, delay
from artiq.coredevice.core import Core
from artiq.language import now_mu

T_RPC_DELAY = 10.e-3

class SSG3021X():
    def __init__(self,ip="192.168.1.97",
                 core=Core):
        self.ip = ip
        self.instr = vxi11.Instrument(self.ip)
        self.core = core

    def set_freq_rpc(self,f):
        self.instr.write(f"FREQ {f} Hz")

    @kernel
    def set_freq(self,f):
        self.core.wait_until_mu(now_mu())
        self.set_freq_rpc(f)
        delay(T_RPC_DELAY)