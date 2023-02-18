import numpy as np

def compute_OD(images):
    '''From a list of images (length 3*n, where n is the number of runs), computes OD.'''
    idx = 0
    ODs = []

    for idx in range(len(images)/3):
        atom_img = images[3*idx + 0]
        light_img = images[3*idx + 1]
        dark_img = images[3*idx + 2]
        
        atoms = atom_img - dark_img
        light = light_img - dark_img

        this_OD = - np.log( np.divide(atoms,light) )
        ODs.append(this_OD)

    return ODs

    

        