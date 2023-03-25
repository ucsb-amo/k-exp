import numpy as np
import kexp.config.camera_params as cam
import kexp.analysis.fitting.gaussian as gfit

def fit_gaussian_sum_OD(sum_od) -> gfit.GaussianFit:
    '''
    Performs a guassian fit on each summedOD in the input list.

    Returns a GaussianFit object which contains the fit parameters.

    Length fit parameters are returned in units of meters. Amplitude and offset
    are in raw summedOD units.

    Parameters
    ----------
    summedODs: ArrayLike
        A list of summedODs.

    Returns
    -------
    fits: ArrayLike
        An array of GaussianFit objects.
    '''
    fits = []
    for sOD in sum_od:
        xaxis = cam.pixel_size_m / cam.magnification * np.arange(len(sOD))
        try:
            fit = gfit.GaussianFit(xaxis, sOD)
        except:
            fit = []
        fits.append(fit)
    return fits



