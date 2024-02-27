from kexp.config import ExptParams
from artiq.experiment import *
import numpy as np

class Scanner():
    def __init__(self):
        self.params = ExptParams()

    def prepare_scan(self,*argv):
        for xvar in argv:
            if xvar.key in self.

    @kernel
    def scan(self,scan_kernel:function,*argv,**kwarg):
        scan_kernel(**kwarg)


class xvar():
    def __init__(self,key:str,value:np.ndarray):
        self.key = key
        self.value = value