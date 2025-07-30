import numpy as np
from kexp.analysis.fitting import GaussianFit

def fit_gaussian_sum_dist(sum_dist: np.ndarray, camera_params) -> list[GaussianFit]:
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

    xaxis = camera_params.pixel_size_m / camera_params.magnification * np.arange(sum_dist.shape[-1])
    
    # reshape to effectively a list of sumODs:
    sum_dist_list = sum_dist.reshape(-1, sum_dist.shape[-1])
    # prep a fit array of len == # sum ODs
    fits = np.empty(sum_dist_list.shape[:-1], dtype=GaussianFit)
    error_count = 0
    total = sum_dist_list.shape[0]
    # iterate over sumODs, fit each and store in fits
    for i in range(total):
        this_sum_dist = sum_dist_list[i]
        try:
            fits[i] = GaussianFit(xaxis, this_sum_dist, print_errors=False)
        except Exception:
            error_count += 1
            fits[i] = None
    # reshape back to the n-dim'nal sumOD shape
    fits = fits.reshape(sum_dist.shape[:-1])

    if error_count > 0:
        print(f"{error_count}/{total} fits failed")

    return fits