from artiq.experiment import delay, kernel
from artiq.language.core import at_mu
from artiq.coredevice.ttl import TTLOut, TTLInOut
import artiq.experiment

class TTL():
    def __init__(self,ch):
        self.ch = ch
        self.name = f'ttl{self.ch}'
        self.key = ""

    def get_device(self,expt:artiq.experiment.EnvExperiment):
        self.ttl_device = expt.get_device(self.name)

class TTL_OUT(TTL):
    def __init__(self,ch):
        super().__init__(ch)
        self.ttl_device = TTLOut
    
    @kernel
    def on(self):
        self.ttl_device.on()

    @kernel
    def off(self):
        self.ttl_device.off()

    @kernel
    def pulse(self,t):
        self.ttl_device.on()
        delay(t)
        self.ttl_device.off()

T_LINE_TRIGGER_SAMPLE_INTERVAL = 30.e-3
T_LINE_TRIGGER_RTIO_DELAY = 5.e-6

class TTL_IN(TTL):
    def __init__(self,ch):
        super().__init__(ch)
        self.ttl_device = TTLInOut

    @kernel
    def wait_for_line_trigger(self):
        while True:
            t_end = self.ttl_device.gate_rising(T_LINE_TRIGGER_SAMPLE_INTERVAL)
            t_edge = self.ttl_device.timestamp_mu(t_end)
            
            while True:
                t_other_edge = self.ttl_device.timestamp_mu(t_end)
                if t_other_edge == -1:
                    break
            
            if t_edge > 0:
                at_mu(t_edge)
                delay(T_LINE_TRIGGER_RTIO_DELAY)
                # read out the remaining input events to clear the input FIFO
                break

class DummyTTL(TTL):
    def __init__(self):
        super().__init__(ch=0)
    
    @kernel
    def get_device(self,expt:artiq.experiment.EnvExperiment):
        return TTLOut

    @kernel
    def on(self):
        pass

    @kernel
    def off(self):
        pass

    @kernel
    def pulse(self,t):
        pass