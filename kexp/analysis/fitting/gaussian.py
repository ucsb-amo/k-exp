import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import savgol_filter
import kamo.constants as c
import matplotlib.pyplot as plt

class Fit():
    def __init__(self,xdata,ydata):
        self.xdata = xdata
        self.ydata = ydata

        self.y_fitdata = []

    def _fit_func(self,x):
        pass

    def _fit(self,x,y):
        pass

    def plot_fit(self):
        plt.figure()
        plt.plot(self.xdata,self.ydata,'.k',markersize=2)
        plt.plot(self.xdata,self.y_fitdata,'--k')
        plt.legend(["Data","Fit"])
        plt.show()

class GaussianFit(Fit):
    def __init__(self,xdata,ydata):
        super().__init__(xdata,ydata)

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
        smth_y = savgol_filter(y,10,3)
        amplitude_guess = np.max(y) - np.min(y)
        x_center_guess = x[np.argmax(y)]
        sigma_guess = np.abs(x_center_guess - x[np.argmin(np.abs(smth_y - 0.65*np.max(y)))])
        y_offset_guess = np.min(y)
        popt, pcov = curve_fit(self._fit_func, x, y,
                                p0=[amplitude_guess, sigma_guess, x_center_guess, y_offset_guess],
                                bounds=((0,0,-np.inf,0),(np.inf,np.inf,np.inf,np.inf)))
        return popt

class GaussianTemperatureFit(Fit):
    def __init__(self, xdata, ydata):
        super().__init__(xdata,ydata)

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