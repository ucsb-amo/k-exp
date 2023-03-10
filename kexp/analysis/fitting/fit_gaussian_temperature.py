import numpy as np
from scipy.optimize import curve_fit
import kamo.constants as c
import kexp.config.camera_params as cam

class GaussianTemperatureFit():
    def __init__(self, xdata, ydata, sigma0=[]):
        self.xdata = xdata
        self.ydata = ydata

        if not sigma0:
            self.sigma0 = ydata[np.argmin(xdata)]

        T = self._fit(xdata,ydata)
        self.T = T
        
        self.y_fitdata = self._fit_func(xdata,T)

    def _fit_func(self, t, T):
        return np.sqrt( c.kB * T / c.m_K * t**2 + self.sigma0**2 )

    def _fit(self, x, y):
        popt, pcov = curve_fit(self._fit_func, x, y, p0=[0], bounds=(0,1))
        return popt