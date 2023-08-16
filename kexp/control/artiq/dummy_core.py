from artiq.experiment import *
class DummyCore():
    @kernel
    def break_realtime():
        pass