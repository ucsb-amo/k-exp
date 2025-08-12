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
    def __init__(self):
        self._dummy = dummy()
        self.k = kernel_from_string(["obj","state"],"obj.set_o(state)")

class kernel_to_string(EnvExperiment):

    def prepare(self):
        self.core = self.get_device('core')
        self.ttl = self.get_device('ttl4')

        # self.ttl.on()

        self.test = test()
        self._dummy = dummy()

    @kernel
    def run(self):
        self.core.reset()

        # self.a = kernel_from_string(["self","ttl","state"],"self.ttl.set_o(state)")
        # self.a(self,"ttl",True)
        # delay(2.e-3)
        # self.a(self,"ttl",False)

        self.test.k(self.ttl,True)
        delay(2.e-3)
        self.test.k(self.ttl,False)