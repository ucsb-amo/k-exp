from pypylon import pylon

class TriggeredImage(pylon.ImageEventHandler):
    def __init__(self):
        super().__init__()
        self.grab_times = []
        self.images = []
    def OnImageGrabbed(self, camera, grabResult):
        self.grab_times.append(grabResult.TimeStamp)
        self.images.append(grabResult.GetArray())