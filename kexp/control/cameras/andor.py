from pylablib.devices import Andor

class AndorEMCCD(Andor.AndorSDK2Camera):
    def __init__(self, ExposureTime=0.):
        super().__init__()
        self.set_exposure(ExposureTime)
        self.set_trigger_mode("ext_start")
    
    def Close(self):
        self.close()