import numpy as np
from scipy.optimize import curve_fit

class GaussianFit():
    def __init__(self,xdata,ydata):
        self.xdata = xdata
        self.ydata = ydata

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
        sigma_guess = np.abs(x_center_guess - x[np.argmax(np.abs(y - 0.65*np.max(y)))])
        y_offset_guess = np.min(y)
        popt, pcov = curve_fit(self._fit_func, x, y,
                                p0=[amplitude_guess, sigma_guess, x_center_guess, y_offset_guess],
                                bounds=((0,0,-np.inf,0),(np.inf,np.inf,np.inf,np.inf)))
        return popt
