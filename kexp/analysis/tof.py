from kexp.analysis.fitting import gaussian as g
from kexp.analysis.base_analysis import atomdata

class tof():
    def __init__(self, atomdata: atomdata):
        self._ad = atomdata

    def compute_T_x(self,t):
        self.T_x = g.GaussianTemperatureFit(t,self._ad.sd_x)

    def compute_T_y(self,t):
        self.T_y = g.GaussianTemperatureFit(t,self._ad.sd_y)