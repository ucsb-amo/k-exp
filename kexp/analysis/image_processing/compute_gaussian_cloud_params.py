import numpy as np
import kexp.config.camera_params as cam
import kexp.analysis.fitting.gaussian as gfit

def fit_gaussian_sum_OD(sum_od):
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
    sh = sum_od.shape[:-1:]
    fits = np.empty(sh,dtype=gfit.GaussianFit)

    xaxis = cam.pixel_size_m / cam.magnification * np.arange(sum_od.shape[len(sh)])

    if len(sh) == 1:
        for i in range(sum_od.shape[0]):
            try:
                fit = gfit.GaussianFit(xaxis, sum_od[i])
                fits[i] = fit
            except:
                pass
    elif len(sh) == 2:
        for ix in range(sum_od.shape[0]):
            for iy in range(sum_od.shape[1]):
                try:
                    fit = gfit.GaussianFit(xaxis, sum_od[ix][iy])
                    fits[ix][iy] = fit
                except:
                    pass
    else:
        print("The data is more than 2D -- update everthing to support 3D.")

    return fits



