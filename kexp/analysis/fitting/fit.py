import numpy as np
from scipy.signal import savgol_filter
import matplotlib.pyplot as plt
import copy
from kexp.analysis.helper import crop_array_by_index, remove_infnan

class Fit():
    def __init__(self,xdata,ydata,
                 include_idx=[0,-1],exclude_idx=[],
                 savgol_window=5,savgol_degree=3):
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

        xdata = crop_array_by_index(xdata,include_idx,exclude_idx)
        ydata = crop_array_by_index(ydata,include_idx,exclude_idx)

        xdata, ydata = remove_infnan(xdata,ydata)
        self.xdata = xdata
        self.ydata = ydata

        self.popt = []
        self.y_fitdata = []
        
        try:
            self.ydata_smoothed = savgol_filter(self.ydata,savgol_window,savgol_degree)
        except:
            self.ydata_smoothed = copy.deepcopy(self.ydata)

    # def get_plot_fitdata(self):
    #     Nsample = len(self.xdata)*500
    #     xplot = np.linspace(self.xdata[0],self.xdata[-1],Nsample)
    #     yplot = self._fit_func(xplot,*self.popt)
    #     return (xplot, yplot)

    def _fit_func(self,x):
        pass

    def _fit(self,x,y):
        pass

    def plot_fit(self,N_interp=10000,legend=True):
        # plt.figure()
        plt.plot(self.xdata,self.ydata,'.',markersize=4)
        
        xsm = np.linspace(self.xdata[0],self.xdata[-1],N_interp)
        yfit_sm = self._fit_func(xsm,*self.popt)
        plt.plot(xsm,yfit_sm,'--')
        if legend:
            plt.legend(["Data","Fit"])

