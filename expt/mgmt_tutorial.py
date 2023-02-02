from artiq.experiment import *


class MgmtTutorial(EnvExperiment):
    """Management tutorial"""
    def build(self):
        pass  # no devices used

    def run(self):
        print("Hello World")