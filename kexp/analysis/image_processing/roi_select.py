import numpy as np

def crop_OD(OD,crop_type=''):

    if crop_type == 'mot':
        roix = [700:1400]
        roiy = [200:900]
    else:
        roix = [0,np.shape(OD)[1]-1]
        roiy = [0,np.shape(OD)[0]-1]

    cropOD = OD[ roiy[0]:roiy[1], roix[0]:roix[1] ]
    return cropOD