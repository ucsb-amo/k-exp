import numpy as np

from kexp.config.camera_id import img_types as img

def process_ODs(raw_ODs,roi):
    '''
    From an ndarray of ODs (dimensions n1 x n2 x ... x nN x px x py, where ni is
    the length of the ith xvar, and px and py are the dimensions in pixels of
    the images), crops to a preset ROI based on in what stage of cooling the
    images were taken. Then computes transverse-integrated "sum_od" for each
    axis.

    Parameters
    ----------
    raw_ODs: ndarray 
        An n1 x n2 x ... x nN x px x py ndarray of uncropped ODs.

    roi: kexp.analysis.ROI
        The ROI object to use for the crop.

    Returns
    -------
    ODs: ArrayLike
        The cropped ODs
    summedODx: ArrayLike summedODy: ArrayLike
    summedODy: ArrayLike
    '''
    ODs = roi.crop(raw_ODs)
    ODs: np.ndarray
    sum_od_y = np.sum(ODs,ODs.ndim-1)
    sum_od_x = np.sum(ODs,ODs.ndim-2)

    return ODs, sum_od_x, sum_od_y

def compute_OD(atoms,light,dark,imaging_type=img.ABSORPTION):
    '''
    From a list of images (length 3*n, where n is the number of runs), computes
    OD. Crops to a preset ROI based on in what stage of cooling the images were
    taken.

    Parameters
    ----------
    img_atoms: list 
        An n x px x py list of images of n images, px x py pixels. Images with atoms+light.

    img_light: list 
        An n x px x py list of images of n images, px x py pixels. Images with only light.

    img_dark: list 
        An n x px x py list of images of n images, px x py pixels. Images with no light, no atoms.

    Returns
    -------
    ODsraw: ArrayLike
        The uncropped ODs
    '''
    
    dtype = atoms.dtype
    if dtype == np.dtype('uint8'):
        new_dtype = np.int16
    elif dtype == np.dtype('uint16'):
        new_dtype = np.int32
    else:
        new_dtype = np.int32

    atoms_only = atoms.astype(new_dtype) - dark.astype(new_dtype)
    light_only = light.astype(new_dtype) - dark.astype(new_dtype)

    atoms_only[atoms_only < 0] = 0
    light_only[light_only < 0] = 0

    It_over_I0 = np.divide(atoms_only, light_only, 
                out=np.zeros(atoms_only.shape, dtype=float), 
                where=light_only!=0)

    if imaging_type == img.ABSORPTION:
        OD = -np.log(It_over_I0,
                        out=np.zeros(atoms_only.shape, dtype=float), 
                        where= It_over_I0!=0)
        OD[OD<0] = 0
    else:
        OD = It_over_I0

    return OD