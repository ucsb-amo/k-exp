import numpy as np
from scipy.optimize import curve_fit
import kamo.constants as c
from kexp.analysis.fitting.fit import Fit

class GaussianFit(Fit):
    def __init__(self,xdata,ydata):
        super().__init__(xdata,ydata,savgol_window=20)

        amplitude, sigma, x_center, y_offset = self._fit(xdata,ydata)
        self.amplitude = amplitude
        self.sigma = sigma
        self.x_center = x_center
        self.y_offset = y_offset

        self.y_fitdata = self._fit_func(xdata,amplitude,sigma,x_center,y_offset)

    def _fit_func(self, x, amplitude, sigma, x_center, y_offset):
        return y_offset + amplitude * np.exp( -(x-x_center)**2 / (2 * sigma**2) )

    def _fit(self, x, y):
        '''
        Returns the gaussian fit parameters for y(x).

        Fit equation: offset + amplitude * np.exp( -(x-x0)**2 / (2 * sigma**2) )

        Parameters
        ----------
        x: ArrayLike
        y: ArrayLike

        Returns
        -------
        amplitude: float
        sigma: float
        x0: float
        offset: float
        '''
        amplitude_guess = np.max(y) - np.min(y)
        x_center_guess = x[np.argmax(y)]
        sigma_guess = np.abs(x_center_guess - x[np.argmin(np.abs(self.ydata_smoothed - 0.65*np.max(y)))])
        y_offset_guess = np.min(y)
        popt, pcov = curve_fit(self._fit_func, x, y,
                                p0=[amplitude_guess, sigma_guess, x_center_guess, y_offset_guess],
                                bounds=((0,0,-np.inf,0),(np.inf,np.inf,np.inf,np.inf)))
        return popt

class GaussianTemperatureFit(Fit):
    def __init__(self, xdata, ydata):

        super().__init__(xdata,ydata,savgol_window=4,savgol_degree=2)

        # scales up small numbers
        self._mult = 1.e6

        self._xdata_sq = (self.xdata * self._mult)**2
        self._ydata_sq = (self.ydata * self._mult)**2

        fit_params, cov = self._fit(self._xdata_sq,self._ydata_sq)
        T, sigma0_squared = fit_params
        err = np.sqrt(np.diag(cov))
        err_T, _ = err
        self.T = T
        self.err_T = err_T
        self.sigma0 = np.sqrt(sigma0_squared) / self._mult

        self.y_fitdata = np.sqrt( self._fit_func(self._xdata_sq,T,sigma0_squared) ) / self._mult

    def _fit_func(self, t_squared, T, sigma0_squared):
        return c.kB * T / c.m_K * t_squared + sigma0_squared

    def _fit(self, x, y):
        # sigma0_guess = self.ydata[np.argmin(self.xdata)]
        sigma0_guess = 500
        popt, pcov = curve_fit(self._fit_func, x, y, p0=[0.001,sigma0_guess**2], bounds=((0,0),(1,np.inf)))
        return popt, pcov