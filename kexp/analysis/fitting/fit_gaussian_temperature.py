import numpy as np
from scipy.optimize import curve_fit
import kamo.constants as c

class GaussianTemperatureFit():
    def __init__(self, xdata, ydata):
        self.xdata = xdata
        self.ydata = ydata

        T, sigma0 = self._fit(xdata,ydata)
        self.T = T
        self.sigma0 = sigma0
        
        self.y_fitdata = self._fit_func(xdata,T,sigma0)

    def _fit_func(self, t, T, sigma0):
        return np.sqrt( c.kB * T / c.m_K * t**2 + sigma0**2 )

    def _fit(self, x, y):
        sigma0_guess = self.ydata[np.argmin(self.xdata)]
        popt, pcov = curve_fit(self._fit_func, x, y, p0=[0,sigma0_guess], bounds=((0,0),(1,np.inf)))
        return popt