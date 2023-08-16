import numpy as np

def crop_OD(OD,crop_type='',Nvars=1):

    if len(np.shape(OD)) <= 2:
        OD = [OD]

    if crop_type == 'bigmot':
        roix = [500, 1500]
        roiy = [100, 1200]
    elif crop_type == 'mot':
        roix = [400, 1800]
        roiy = [100, 1300]
    elif crop_type == 'cmot':
        roix = [750, 1250]
        roiy = [400, 700]
    elif crop_type == 'gm':
        roix = [600, 1450]
        roiy = [400, 1050] 
    elif crop_type == 'gm2':
        roix = [800, 1300]
        roiy = [550, 950]
    else:
        roix = [0,np.shape(OD)[len(np.shape(OD))-1]-1]
        roiy = [0,np.shape(OD)[len(np.shape(OD))-2]-1]

    if Nvars == 1:
        cropOD = OD[:, roiy[0]:roiy[1], roix[0]:roix[1] ]
    if Nvars == 2:
        cropOD = OD[:, :, roiy[0]:roiy[1], roix[0]:roix[1] ]

    return cropOD