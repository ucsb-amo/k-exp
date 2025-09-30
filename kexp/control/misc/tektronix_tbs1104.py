from pylablib.devices import Tektronix
import numpy as np
from artiq.language import TBool

class ScopeData:
    def __init__(self):
        self.scopes = []
        self.xvardims = []
        self._scope_trace_taken = False

    def close(self):
        for scope in self.scopes:
            try:
                scope.close()
            except:
                pass

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
            idx = len(self._scope_data.scopes)
            label = f"scope{idx}"
        self.label = label

        self.device_id = self.handle_devid_input(device_id)
        print(self.device_id)
        self.scope = Tektronix.ITektronixScope(self.device_id)
        self._scope_data.scopes.append(self)

        self.data = []

    def read_sweep(self,channels) -> TBool:
        """Read out the specified channels and records result to self.data.
        Channels not read in will be stored as all zeros.

        Args:
            channels (list/int): The channels to read out. 0-indexed.

        Returns:
            TBool: Returns true when read is complete.
        """        
        if isinstance(channels,int):
            channels = [channels]
        channels = np.asarray(channels)
        self._scope_data._scope_trace_taken = True
        sweeps = self.scope.read_multiple_sweeps(np.array(channels) + 1)
        Npts = len(sweeps[0][:,0])
        data = np.zeros((4,2,Npts))
        for idx in range(3):
            if idx in channels:
                data[idx][0] = sweeps[idx][:,0]
                data[idx][1] = sweeps[idx][:,1]
        self.data.append(data)
        return True
    
    def reshape_data(self):
        if self.data != []:
            self.data = np.array(self.data)
            Npts = len(self.data[0][0])
            self.data = self.data.reshape(*self._scope_data.xvardims,2,Npts)

    def handle_devid_input(self,device_id):
        default = (device_id == "")
        is_int = (isinstance(device_id,int))
        if default or is_int:
            from pylablib import list_backend_resources
            devs = list_backend_resources("visa")
            devs_usb = [dev for dev in devs if "USB" in dev]
            
            if default:
                if len(devs_usb) > 1:
                    print(*[dev+'\n' for dev in devs_usb])
                    idx = input("More than one USB device connected. Input the index of which device to use.")
                if idx == '':
                    idx = 0
                else:
                    try:
                        idx = int(idx)
                    except:
                        print('Input cannot be cast to int, using idx = 0.')
            if is_int:
                idx = device_id
            device_id = devs[idx]
        return device_id