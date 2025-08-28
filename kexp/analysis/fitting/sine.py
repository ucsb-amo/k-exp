from kexp.analysis.fitting import Fit, GaussianFit
from kexp.analysis.helper import normalize

from scipy.signal import find_peaks
from scipy.optimize import curve_fit

import numpy as np

class Sine(Fit):
    def __init__(self,xdata,ydata,
                 include_idx = [0,-1],
                 exclude_idx = []):
        super().__init__(xdata,ydata,
                         include_idx=include_idx,exclude_idx=exclude_idx,
                         savgol_window=20)

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
        idx, _ = find_peaks(normalize(y), prominence=prom)
        if len(idx) > 1:
            lambda_guess = np.mean(np.diff(x[idx]))
        else:
            lambda_guess = abs(x[np.argmax(y)] - x[np.argmin(y)])
        k_guess = 2*np.pi/lambda_guess
        
        if y[0] - y_offset_guess < -amplitude_guess:
            phase_guess = np.pi
        elif y[0] - y_offset_guess > amplitude_guess:
            phase_guess = -np.pi
        else:
            phase_guess = 0.
        
        return amplitude_guess, y_offset_guess, k_guess, phase_guess
    
    def _find_idx(self,x0,x):
        return np.argmin(np.abs(x-x0))