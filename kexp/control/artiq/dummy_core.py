from artiq.experiment import kernel
class DummyCore():
    @kernel
    def break_realtime(self):
        pass

    @kernel
    def wait_until_mu(self,t):
        pass