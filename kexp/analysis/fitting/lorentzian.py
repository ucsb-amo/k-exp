import numpy as np
from scipy.optimize import curve_fit
import kamo.constants as c
from kexp.analysis.fitting.fit import Fit

class LorentzianFit(Fit):
    def __init__(self,xdata,ydata,
                 force_zero_offset=False,
                 include_idx = [0,-1],
                 exclude_idx = []):
        super().__init__(xdata,ydata,
                         include_idx=include_idx,exclude_idx=exclude_idx,
                         savgol_window=20)
        
        super().__init__(xdata,ydata,savgol_window=20)

        self.force_zero_offset = force_zero_offset

        try:
            popt = self._fit(self.xdata,self.ydata)
        except Exception as e:
            print(e)
            popt = [np.NaN]*4
            self.y_fitdata = np.zeros(self.ydata.shape); self.y_fitdata.fill(np.NaN)

        self.popt = popt
        amplitude, gamma, x_center, y_offset = popt
        self.amplitude = amplitude
        self.gamma = gamma
        self.x_center = x_center
        self.y_offset = y_offset

        self.y_fitdata = self._fit_func(self.xdata,*popt)

        self.area = amplitude

    def _fit_func(self, x, amplitude, gamma, x_center, y_offset):
        if self.force_zero_offset:
            return amplitude * gamma / ( (x-x_center)**2 + (gamma/2)**2 )
        else:
            return y_offset + amplitude * gamma / ( (x-x_center)**2 + (gamma/2)**2 )

    def _fit(self, x, y):
        '''
        Returns the Lorentzian fit parameters for y(x).

        Fit equation: y_offset + amplitude * gamma / ( (x-x_center)**2 + (gamma/2)**2 )

        Parameters
        ----------
        x: ArrayLike
        y: ArrayLike

        Returns
        -------
        amplitude: float
        gamma: float
        x0: float
        offset: float
        '''
        fit_success = False
        N = 1
        while fit_success == False:
            amplitude_guess = np.max(y) - np.min(y)
            x_center_guess = x[np.argmax(y)]
            gamma_guess = np.abs((x[-1] - x[0]))/N
            y_offset_guess = np.min(y)
            
            bounds_min = (0,0,-np.inf,-np.inf)
            bounds_max = (np.inf,np.inf,np.inf,np.inf)

            guesses = [amplitude_guess, gamma_guess, x_center_guess, y_offset_guess]
            # print(f'guesses: {guesses}')

            try:
                popt, pcov = curve_fit(self._fit_func, x, y,
                                        p0=guesses,
                                        bounds=(bounds_min,bounds_max))
                fit_success = True
            except:
                N += 1
            
            if N == 10:
                break
        return popt