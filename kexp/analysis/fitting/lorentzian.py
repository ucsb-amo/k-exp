import numpy as np
from scipy.optimize import curve_fit
import kamo.constants as c
from kexp.analysis.fitting.fit import Fit

class LorentzianFit(Fit):
    def __init__(self,xdata,ydata):
        super().__init__(xdata,ydata,savgol_window=20)

        try:
            amplitude, sigma, x_center, y_offset = self._fit(self.xdata,self.ydata)
        except Exception as e:
            print(e)
            amplitude, sigma, x_center, y_offset = np.NaN, np.NaN, np.NaN, np.NaN
            self.y_fitdata = np.zeros(self.ydata.shape); self.y_fitdata.fill(np.NaN)

        self.amplitude = amplitude
        self.sigma = sigma
        self.x_center = x_center
        self.y_offset = y_offset

        self.y_fitdata = self._fit_func(self.xdata,amplitude,sigma,x_center,y_offset)

        self.area = amplitude

    def _fit_func(self, x, amplitude, sigma, x_center, y_offset):
        return y_offset + amplitude * sigma/(2*np.pi) / ( (x-x_center)**2 + (sigma/2)**2 )

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