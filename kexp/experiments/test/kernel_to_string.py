from artiq.experiment import *
from artiq.experiment import delay

import numpy as np

from artiq.language.core import kernel_from_string

class dummy():
    def __init__(self):
        pass

    def set_o(self,state):
        pass

class test():
    def __init__(self,core):
        self._dummy = dummy()
        self.k = kernel_from_string(["obj","state"],"obj.set_o(state)")
        self.core = core

    def testfunc(self,device):
        self.do_ttl(device)

    @kernel
    def do_ttl(self,device):
        self.k(device,True)
        delay(2.e-3)
        self.k(device,False)

class kernel_to_string(EnvExperiment):

    def prepare(self):
        self.core = self.get_device('core')
        self.ttl = self.get_device('ttl4')

        # self.ttl.on()

        self.test = test(self.core)
        self._dummy = dummy()

    @kernel
    def run(self):
        self.core.reset()

        # self.a = kernel_from_string(["self","ttl","state"],"self.ttl.set_o(state)")
        # self.a(self,"ttl",True)
        # delay(2.e-3)
        # self.a(self,"ttl",False)

        # self.test.k(self.ttl,True)
        # delay(2.e-3)
        # self.test.k(self.ttl,False)

        self.test.testfunc(self.ttl)

    