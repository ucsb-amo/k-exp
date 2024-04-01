import numpy as np
import kexp.analysis.image_processing.roi_select as roi

def compute_ODs(img_atoms,img_light,img_dark,crop_type='mot',Nvars=1):
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

    crop_type: str
        Picks what crop settings to use for the ODs. Default: 'mot'. Allowed
        options: 'mot', 'cmot', 'gm', 'odt'.

    Returns
    -------
    ODsraw: ArrayLike
        The uncropped ODs
    ODs: ArrayLike
        The cropped ODs
    summedODx: ArrayLike
    summedODy: ArrayLike
    '''

    ODsraw = compute_OD(img_atoms,img_light,img_dark)
    ODs = roi.crop_OD(ODsraw,crop_type,Nvars)

    sum_od_y = np.sum(ODs,Nvars+1)
    sum_od_x = np.sum(ODs,Nvars)

    return ODsraw, ODs, sum_od_x, sum_od_y

def compute_OD(atoms,light,dark):
    
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
                    where= light_only!=0)
    
    OD = -np.log(It_over_I0,
                    out=np.zeros(atoms_only.shape, dtype=float), 
                    where= It_over_I0!=0)
    
    OD[OD<0] = 0

    return OD  