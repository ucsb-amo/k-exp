from kexp.analysis.fitting import Fit
from scipy.optimize import curve_fit
import numpy as np

class LinearFit(Fit):
    def __init__(self,xdata,ydata,
                 include_idx = [0,-1],
                 exclude_idx = []):
        super().__init__(xdata,ydata,
                         include_idx=include_idx,exclude_idx=exclude_idx)
        try:
            popt = self._fit(self.xdata,self.ydata)
        except Exception as e:
            print(e)
            popt = [np.NaN] * 2
            self.y_fitdata = np.zeros(self.ydata.shape); self.y_fitdata.fill(np.NaN)
        self.popt = popt
        self.slope = popt[0]
        self.offset = popt[1]
        self.y_fitdata = self._fit_func(self.xdata,*popt)

    def _fit_func(self, x, slope, offset):
        return slope * x + offset
    
    def _fit(self, x, y):
        guess = self._linear_guesses(x,y)
        popt, pcov = curve_fit(self._fit_func, x, y,
                               p0 = [*guess])
        return popt

    def _linear_guesses(self,x,y):
        slope_guess = (y[-1] - y[0])/(x[-1] - x[0])
        offset_guess = y[np.argmin(np.abs(x))]
        return slope_guess, offset_guess