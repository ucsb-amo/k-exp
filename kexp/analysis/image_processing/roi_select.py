import numpy as np

def crop_OD(OD,crop_type='',Nvars=1):

    if len(np.shape(OD)) <= 2:
        OD = [OD]

    if crop_type == 'mot':
        roix = [500, 1400]
        roiy = [250, 1200]
    elif crop_type == 'gm':
        roix = [550, 1400]
        roiy = [250, 1000]
    elif crop_type == 'gm2':
        roix = [800, 1150]
        roiy = [400, 700]
    else:
        roix = [0,np.shape(OD)[len(np.shape(OD))-1]-1]
        roiy = [0,np.shape(OD)[len(np.shape(OD))-2]-1]

    if Nvars == 1:
        cropOD = OD[:, roiy[0]:roiy[1], roix[0]:roix[1] ]
    if Nvars == 2:
        cropOD = OD[:, :, roiy[0]:roiy[1], roix[0]:roix[1] ]

    return cropOD