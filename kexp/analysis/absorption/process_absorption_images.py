import numpy as np

def compute_OD(images):
    '''From a list of images (length 3*n, where n is the number of runs), computes OD.'''
    idx = 0
    ODs = []

    img_atoms = images[0::3]
    img_light = images[1::3]
    img_dark = images[2::3]

    for idx in range(len(img_atoms)):
        atoms = img_atoms[idx]
        light = img_light[idx]
        dark = img_dark[idx]

        atoms_only = atoms - dark
        light_only = light - dark

        atoms_only[atoms_only < 0] = 0
        light_only[light_only < 0] = 0

        It_over_I0 = np.divide(atoms_only, light_only, 
                       out=np.zeros(atoms_only.shape, dtype=float), 
                       where= light_only!=0)
        
        OD = -np.log10(It_over_I0,
                       out=np.zeros(atoms_only.shape, dtype=float), 
                       where= It_over_I0!=0)
        
        OD[OD<0] = 0

        ODs.append(OD)

    return ODs

        
        
        

    

        