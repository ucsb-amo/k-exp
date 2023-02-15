from pypylon import pylon

class BaslerUSB():
    def __init__(self):
        self.tl_factory = pylon.TlFactory.GetInstance()
        pass

    def init_camera(self):
        self.camera = pylon.InstantCamera()
        self.camera.Attach(self.tl_factory.CreateFirstDevice())

    def grab_frames(self,N,timeout_ms):
        self.camera.Open()
        self.camera.StartGrabbing(N)
        grab = self.camera.RetrieveResult(2000, pylon.TimeoutHandling_Return)
        if grab.GrabSucceeded():
            img = grab.GetArray()
            return img
        self.camera.Close()

        
        