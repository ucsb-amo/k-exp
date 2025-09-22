from pylablib.devices import Tektronix
import numpy as np
from artiq.language import TBool

class ScopeData:
    def __init__(self):
        self.scopes = []
        self.xvardims = []
        self._scope_trace_taken = False

class TektronixScope_TBS1104():
    def __init__(self,device_id="",label="",
                 scope_data=ScopeData()):
        """A scope object.

        Args:
            device_id (str): The USB VISA string that identifies the scope. If
            nothing is provided, will prompt user for an input. Default for no
            input is the first element (0 index) of
            pylablib.list_backend_resources.
            label (str): labels the scope. Defaults to "scope{idx}" where idx is
            how many scopes have been initialized for the given ScopeData
            object.
            scope_data (ScopeData): Should be the ScopeData object of the
            experiment ("self.scope_data").
        """        
        self._scope_data = scope_data

        if label == "":
            idx = len(self._scope_data)
            label = f"scope{idx}"
        self.label = label

        self.load_scope(device_id)
        self.data = []

    def load_scope(self,device_id="") -> TBool:
        self.device_id = self.handle_devid_input(device_id)
        self.scope = Tektronix.ITektronixScope(self.device_id)
        self._scope_data.scopes.append(self)
        return True

    def read_sweep(self,channels) -> TBool:
        if isinstance(channels,int):
            channels = [channels]
        self._scope_data._scope_trace_taken = True
        sweeps = self.scope.read_sweep(channels)
        data = [[sweep[:,0],sweep[:,1]] for sweep in sweeps]
        self.data.append(data)
        return True
    
    def reshape_data(self):
        if self.data != []:
            self.data = np.array(self.data)
            Npts = len(self.data[0][0])
            self.data = self.data.reshape(*self._scope_data.xvardims,2,Npts)

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