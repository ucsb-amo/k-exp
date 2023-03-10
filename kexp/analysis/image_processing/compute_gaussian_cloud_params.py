import numpy as np
import kexp.config.camera_params as cam
import kexp.analysis.fitting.fit_gaussian as fit

def compute_gaussian_cloud_params(summedODx,summedODy):
    xfits = fit_gaussian_summedOD(summedODx)
    yfits = fit_gaussian_summedOD(summedODy)
    return xfits, yfits

def fit_gaussian_summedOD(summedODs):
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
    for sOD in summedODs:
        xaxis = cam.pixel_size_m * np.arange(len(sOD))
        fits.append(fit.gauss_fit(xaxis, sOD))
    return fits



