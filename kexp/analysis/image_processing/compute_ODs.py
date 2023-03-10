import numpy as np
import kexp.analysis.image_processing.roi_select as roi

def analyze_and_save_absorption_images(images,timestamps_ns,expt,crop_type='mot'):
    '''
    Saves the images, image timestamps (in ns), computes ODs, and saves them to
    the dataset of the current experiment (expt)

    Parameters
    ----------
    images: list 
        An n x px x py list of images of n images, px x py pixels, ordered as
        atoms, light, dark.

    timestamps_ns: list
        A list of timestamps for the images in `images`, in nanoseconds.

    expt: EnvExperiment
        The experiment object, called to save datasets.

    crop_type: str
        Picks what crop settings to use for the ODs. Default: 'mot'. Allowed
        options: 'mot', 'cmot', 'gm', 'odt'.
    '''

    ODraw, ODs, summedODx, summedODy, \
        img_atoms, img_light, img_dark, \
        img_atoms_tstamp_ns, img_light_tstamp_ns, img_dark_tstamp_ns \
         = compute_ODs(images,crop_type)
    # expt.set_dataset('img_all',images)
    # expt.set_dataset('img_timestamps_ns',timestamps_ns)
    expt.set_dataset('img_atoms_tstamp_ns',img_atoms_tstamp_ns)
    expt.set_dataset('img_light_tstamp_ns',img_light_tstamp_ns)
    expt.set_dataset('img_dark_tstamp_ns',img_dark_tstamp_ns)
    expt.set_dataset('img_atoms', img_atoms)
    expt.set_dataset('img_light', img_light)
    expt.set_dataset('img_dark', img_dark)
    expt.set_dataset('ODraw', ODraw)
    expt.set_dataset('OD',ODs)
    expt.set_dataset('summedODx',summedODx)
    expt.set_dataset('summedODy',summedODy)

    return ODs, summedODx, summedODy

def compute_ODs(images,crop_type='mot'):
    '''
    From a list of images (length 3*n, where n is the number of runs), computes
    OD. Crops to a preset ROI based on in what stage of cooling the images were
    taken.

    Parameters
    ----------
    images: list 
        An n x px x py list of images of n images, px x py pixels, ordered as
        atoms, light, dark.

    crop_type: str
        Picks what crop settings to use for the ODs. Default: 'mot'. Allowed
        options: 'mot', 'cmot', 'gm', 'odt'.
    '''
    atom_img_idx = 0
    light_img_idx = 1
    dark_img_idx = 2

    ODsraw = []
    ODs = []
    summedODx = []
    summedODy = []

    img_atoms = images[atom_img_idx::3]
    img_light = images[light_img_idx::3]
    img_dark = images[dark_img_idx::3]

    for idx in range(len(img_atoms)):
        atoms = img_atoms[idx]
        light = img_light[idx]
        dark = img_dark[idx]

        OD = cmopute_OD(atoms,light,dark)
        ODsraw.append(OD)

        OD = roi.crop_OD(OD)
        ODs.append(OD)

        this_summedODx, this_summedODy = compute_summedOD(OD)
        summedODx.append(this_summedODx)
        summedODy.append(this_summedODy)

    return ODsraw, ODs, summedODx, summedODy

def cmopute_OD(atoms,light,dark):

    atoms_only = atoms - dark
    light_only = light - dark

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
    
def compute_summedOD(OD):
    summedODy = np.sum(OD,1)
    summedODx = np.sum(OD,0)
    return summedODx, summedODy

    

        
        
        

    

        