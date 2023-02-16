from pypylon import pylon

class BaslerUSB(pylon.InstantCamera):
    def __init__(self):
        super().__init__()

        tl_factory = pylon.TlFactory.GetInstance()
        self.Attach(tl_factory.CreateFirstDevice())
        