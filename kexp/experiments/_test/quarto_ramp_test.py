from artiq.experiment import *
from artiq.coredevice.core import Core
from artiq.language.core import now_mu
from artiq.experiment import delay, parallel, sequential, delay_mu
import numpy as np

class quarto_ramp_test(EnvExperiment):
    def prepare(self):
        self.core = self.get_device("core")
        self.core: Core
        self.ttl = self.get_device("ttl4")
        self.ttl2 = self.get_device("ttl3")

        self.connect()

        self.choose_ramp(1,0)

        self.t1 = 30.e-3
        self.t2 = 60.e-3
        self.write_ramp(ch=1,ramp_idx=0,t=self.t1,v0=0.,vf=5.)
        self.write_ramp(ch=1,ramp_idx=1,t=self.t2,v0=5.,vf=0.)

        self.t_serial = 4.e-3
        self.t = 0.

    def connect(self):
        import serial
        COM = 'COM3'
        BAUDRATE = 9600
        self.ser = serial.Serial(COM,BAUDRATE)

    def ser_write(self,command:str):
        if command.split(" ")[-1] != "\n":
            command += "\n"
        self.ser.write(command.encode())

    # @rpc(flags={'async'})
    def choose_ramp(self,ch,ridx):
        command = f"r{ch:1.0f} {ridx:1.0f}\n".encode()
        self.ser.write(command)

    @kernel
    def choose_ramp_kernel(self,ch,ridx):
        # delay(-self.t_serial)
        self.core.wait_until_mu(now_mu())
        self.choose_ramp(ch,ridx)
        delay(self.t_serial)

    def write_ramp(self,ch,ramp_idx,t,v0,vf):
        t_us = int(t*1.e6)
        command = f"go {ch:1.0f} {ramp_idx:1.0f} {t_us:1.2f} {v0:1.4f} {vf:1.4f}"
        self.ser_write(command)

    @kernel
    def do_ramp(self,ch=1,ramp_idx=0,change_ramp_idx=True):
        if change_ramp_idx:
            self.choose_ramp_kernel(ch,ramp_idx)
        self.ttl.pulse(1.e-6)
        if ramp_idx == 0:
            t = self.t1
        elif ramp_idx == 1:
            t = self.t2
        else:
            t = 0.
        delay(t)

    @kernel
    def run(self):
        self.core.reset()

        self.do_ramp(0,0,change_ramp_idx=False)

        self.do_ramp(1,1)
        
        delay(1*s)

