from kexp.analysis.fitting import gaussian as g
from kexp.analysis.base_analysis import atomdata

class tof():
    def __init__(self, atomdata: atomdata):
        self._ad = atomdata

    def compute_T_x(self,t):
        T = g.GaussianTemperatureFit(t,self._ad.fit_sd_x).T
        return T

    def compute_T_y(self,t):
        T = g.GaussianTemperatureFit(t,self._ad.fit_sd_y).T
        return T