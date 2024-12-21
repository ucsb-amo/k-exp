from kexp.analysis.fitting import Fit, GaussianFit

from scipy.signal import find_peaks
from scipy.optimize import curve_fit

import numpy as np

class Sine(Fit):
    def __init__(self,xdata,ydata):
        super().__init__(xdata,ydata,savgol_window=20)

        # self.xdata, self.ydata = self.remove_infnan(self.xdata,self.ydata)

        try:
            self.popt, self.pcov = self._fit(self.xdata,self.ydata)
        except Exception as e:
            print(e)
            self.popt = [np.NaN, np.NaN, np.NaN, np.NaN]
            self.pcov = np.array([])
            self.y_fitdata = np.zeros(self.ydata.shape); self.y_fitdata.fill(np.NaN)

        amplitude, y_offset, k, phase = self.popt
        self.amplitude = amplitude
        self.y_offset = y_offset
        self.k = k
        self.phase = phase

        self.y_fitdata = self._fit_func(self.xdata,*self.popt)


    def _fit_func(self, x, amplitude, y_offset, k, phase):
        return y_offset + amplitude * np.sin(k * x + phase)

    def _fit(self, x, y):
        '''
        Returns the fit parameters for y(x).

        Fit equation: y_offset + amplitude * np.sin(k * x + phase)

        Parameters
        ----------
        x: ArrayLike
        y: ArrayLike

        Returns
        -------
        amplitude: float
        y_offset: float
        k: float
        phase: float
        '''
        guesses = self._guesses(x,y)
        popt, pcov = curve_fit(self._fit_func, x, y,
                                p0=guesses,
                                bounds=((0.,-np.inf,0.,0.),(np.inf,np.inf,np.inf,2*np.pi)) )
        return popt, pcov
        
    def _guesses(self,x,y):

        y_offset_guess = (np.max(y) + np.min(y)) / 2
        # y_offset_guess = np.mean(y)

        rms = np.sqrt(np.mean((y- np.mean(y))**2))
        amplitude_guess = rms

        prom = rms/2
        idx, _ = find_peaks(y, prominence=prom)
        lambda_guess = np.mean(np.diff(x[idx]))
        k_guess = 2*np.pi/lambda_guess
        phase_guess = (- k_guess * x[0])%(2*np.pi)
        # phase_guess = 1
        
        return amplitude_guess, y_offset_guess, k_guess, phase_guess
    
    def _find_idx(self,x0,x):
        return np.argmin(np.abs(x-x0))