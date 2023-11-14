from kexp.analysis.fitting.fit import Fit
import numpy as np
from scipy.optimize import curve_fit

class ExponentialDecayFit(Fit):
    def __init__(self,xdata,ydata):
        super().__init__(xdata,ydata,savgol_window=20)
        coefficient, decay_rate, y_offset = self._fit(xdata,ydata)
        self.coefficient = coefficient
        self.decay_rate = decay_rate
        self.y_offset = y_offset
        self.y_fitdata = self._fit_func(xdata,coefficient,decay_rate,y_offset)

    def _fit_func(self,x,coefficient,decay_rate,y_offset):
        return y_offset + coefficient * np.exp(-x/decay_rate)
    
    def _fit(self,x,y):
        coefficient_guess = np.max(y)
        y_offset_guess = np.min(y)
        decay_rate_guess = np.ptp(x)/10
        popt, pcov = curve_fit(self._fit_func, x, y,
                               p0=[coefficient_guess,decay_rate_guess,y_offset_guess],
                               bounds=((0,0,-np.inf),(np.inf,np.inf,np.inf)))
        return popt