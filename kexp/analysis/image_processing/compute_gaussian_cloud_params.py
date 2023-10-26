import numpy as np
from kexp.analysis.fitting import GaussianFit
from typing import List

def fit_gaussian_sum_dist(sum_dist,camera_params) -> List[GaussianFit]:
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
    sh = sum_dist.shape[:-1:]
    fits = np.empty(sh,dtype=GaussianFit)

    xaxis = camera_params.pixel_size_m / camera_params.magnification * np.arange(sum_dist.shape[len(sh)])

    if len(sh) == 1:
        for i in range(sum_dist.shape[0]):
            try:
                fit = GaussianFit(xaxis, sum_dist[i])
                fits[i] = fit
            except Exception as e:
                print(e)
                pass
    elif len(sh) == 2:
        for ix in range(sum_dist.shape[0]):
            for iy in range(sum_dist.shape[1]):
                try:
                    fit = GaussianFit(xaxis, sum_dist[ix][iy])
                    fits[ix][iy] = fit
                except Exception as e:
                    print(e)
                    pass
    else:
        print("The data is more than 2D -- update everthing to support 3D.")

    return fits



