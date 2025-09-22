from pylablib.devices import Tektronix
import numpy as np
from artiq.language import TBool

class TektronixScope_TBS1104():
    def __init__(self,device_id=""):
        self.load_scope(device_id)
        self.scope_data = []

    def load_scope(self,device_id="") -> TBool:
        self.device_id = self.handle_devid_input(device_id)
        self.scope = Tektronix.ITektronixScope(self.device_id)
        return True

    def read_sweep(self,channels) -> TBool:
        if isinstance(channels,int):
            channels = [channels]

        sweeps = self.scope.read_sweep(channels)
        data = [[sweep[:,0],sweep[:,1]] for sweep in sweeps]
        self.scope_data.append(data)
        return True
    
    def save_data_to_expt(self,expt_object):
        if self.scope_data != []:
            self.scope_data = np.array(self.scope_data)
            Npts = len(self.scope_data[0][0])
            xvardims = [len(xvar.values) for xvar in expt_object.scan_xvars]
            self.scope_data = self.scope_data.reshape(*xvardims,2,Npts)

    def handle_devid_input(self,device_id):
        if device_id == "":
            from pylablib import list_backend_resources
            devs = list_backend_resources("visa")
            devs_usb = [dev for dev in devs if "USB" in dev]

            if devs_usb > 1:
                print(devs_usb)
                idx = input("More than one USB device connected. Input the index of which device to use.")
            if idx == '':
                idx = 0
            else:
                try:
                    idx = int(idx)
                except:
                    print('Input cannot be cast to int, using idx = 0.')
            device_id = devs[0]
        return device_id