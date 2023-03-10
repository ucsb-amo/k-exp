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

        T = self.fit(xdata,ydata)
        self.T = T
        
        self.y_fitdata = self._fit_func(xdata,T)

    def _fit_func(self, t, T):
        return cam.pixel_size_m / cam.magnification * np.sqrt( c.kB * T / c.m_K * t**2 + self.sigma0**2 )

    def _fit(self, x, y):
        popt, pcov = curve_fit(self._fit_func, x, y, p0=[1.e-3], bounds=(0,1))
        return popt
    
    def fit(self, x, y):
        '''
        Parameters
        ----------
        x: ArrayLike
        y: ArrayLike
        sigma0: float
            The initial width of the cloud.

        Returns
        -------
        T: float
        '''
        T = self._fit(x,y)
        return T