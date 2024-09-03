import numpy as np
from scipy.signal import savgol_filter
import matplotlib.pyplot as plt
import copy

class Fit():
    def __init__(self,xdata,ydata,savgol_window=5,savgol_degree=3):
        '''
        Arguments
        ----------
        xdata: Array
            The independent variable.
        ydata: Array
            The dependent variable.
        savgol_window: int
            The width of the smoothing window (Savitzky-Golay filter) used to
            compute a smoothed ydata (for fit guess purposes).
        savgol_degree: int
            The width of the smoothing polynomial (Savitzky-Golay filter) used
            to compute a smoothed ydata (for fit guess purposes).

        Attributes:
        -----------
        xdata
        ydata
        y_fitdata
        ydata_smoothed
        '''
        xdata = np.asarray(xdata)
        ydata = np.asarray(ydata)

        xdata, ydata = self.remove_infnan(xdata,ydata)
        self.xdata = xdata
        self.ydata = ydata

        self.y_fitdata = []
        
        try:
            self.ydata_smoothed = savgol_filter(self.ydata,savgol_window,savgol_degree)
        except:
            self.ydata_smoothed = copy.deepcopy(self.ydata)

    def _fit_func(self,x):
        pass

    def _fit(self,x,y):
        pass

    def plot_fit(self):
        fig = plt.figure()
        plt.plot(self.xdata,self.ydata,'.',markersize=4)
        plt.plot(self.xdata,self.y_fitdata,'--')
        plt.legend(["Data","Fit"])

    def remove_infnan(self,xdata,ydata):
        bools = ~np.isnan(xdata) & ~np.isinf(xdata) & ~np.isnan(ydata) & ~np.isinf(ydata)
        return xdata[bools], ydata[bools]

