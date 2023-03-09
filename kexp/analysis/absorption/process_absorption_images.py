import numpy as np

def analyze_and_save_absorption_images(images,timestamps_ns,expt):
    '''
    Saves the images, image timestamps (in ns), computes ODs, and saves them to
    the dataset of the current experiment (expt)
    '''

    ODs, summedODx, summedODy = process_absorption_images(images)
    expt.set_dataset('img_all',images)
    expt.set_dataset('img_timestamps_ns',timestamps_ns)
    expt.set_dataset('img_atoms', images[0::3])
    expt.set_dataset('img_light', images[1::3])
    expt.set_dataset('img_dark', images[2::3])
    expt.set_dataset('OD',ODs)
    expt.set_dataset('summedODx',summedODx)
    expt.set_dataset('summedODy',summedODy)

def process_absorption_images(images):
    '''
    From a list of images (length 3*n, where n is the number of runs), computes
    OD. Crops to a preset ROI based on in what stage of cooling the images were
    taken.
    '''
    idx = 0
    ODs = []
    summedODx = []
    summedODy = []

    img_atoms = images[0::3]
    img_light = images[1::3]
    img_dark = images[2::3]

    for idx in range(len(img_atoms)):
        atoms = img_atoms[idx]
        light = img_light[idx]
        dark = img_dark[idx]

        OD = compute_OD(atoms,light,dark)
        ODs.append(OD)

        this_summedODx, this_summedODy = compute_summedOD(OD)
        summedODx.append(this_summedODx)
        summedODy.append(this_summedODy)

    return ODs, summedODx, summedODy

def compute_OD(atoms,light,dark):

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

    

        
        
        

    

        