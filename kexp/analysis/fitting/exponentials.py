from kexp.analysis.fitting.fit import Fit
import numpy as np
from scipy.optimize import curve_fit

class ExponentialDecayFit(Fit):
    def __init__(self,xdata,ydata):
        super().__init__(xdata,ydata,savgol_window=20)
        self.popt = self._fit(self.xdata,self.ydata)
        self.coefficient = self.popt[0]
        self.time_constant = self.popt[1]
        self.y_offset = self.popt[2]
        self.y_fitdata = self._fit_func(self.xdata,*self.popt)

    def _fit_func(self,x,coefficient,time_constant,y_offset):
        return y_offset + coefficient * np.exp(-x/time_constant)
    
    def _fit(self,x,y):
        coefficient_guess = np.max(y)
        y_offset_guess = np.min(y)
        time_constant_guess = np.ptp(x)/10
        popt, pcov = curve_fit(self._fit_func, x, y,
                               p0=[coefficient_guess,time_constant_guess,y_offset_guess],
                               bounds=((0,0,-np.inf),(np.inf,np.inf,np.inf)))
        return popt