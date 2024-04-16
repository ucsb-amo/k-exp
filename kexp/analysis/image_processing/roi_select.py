import numpy as np

def crop_OD(OD,crop_type='',Nvars=1):

    if len(np.shape(OD)) <= 2:
        OD = np.array([OD])

    if crop_type == 'bigmot':
        roix = [500, 1500]
        roiy = [100, 1200]
    elif crop_type == 'mot':
        roix = [350, 1550]
        roiy = [100, 1050]
    elif crop_type == 'cmot':
        roix = [750, 1400]
        roiy = [400, 700]
    elif crop_type == 'gm':
        roix = [600,1460]
        roiy = [150,1000]
    elif crop_type == 'gm2':
        roix = [500,1300]
        roiy = [500,1200]
    elif crop_type == 'fluor_gm':
        roix = [500, 1450]
        roiy = [200, 950]
    elif crop_type == 'lightsheet':
        roix = [1000,1080]
        roiy = [470,880]
    elif crop_type == 'lightsheet_zaxis':
        roix = [750,970]
        roiy = [500,780]
    elif crop_type == 'lightsheet_short':
        roix = [1020,1050]
        roiy = [600,680]
    elif crop_type == 'xy_tweezer':
        roix = [950,1150]
        roiy = [630,700]
    elif crop_type == 'andor_tweezer':
        roix = [220,320]
        roiy = [230,330]
    else:
        roix = [0,np.shape(OD)[len(np.shape(OD))-1]]
        roiy = [0,np.shape(OD)[len(np.shape(OD))-2]]

    if Nvars == 1:
        cropOD = OD[:, roiy[0]:roiy[1], roix[0]:roix[1] ]
    if Nvars == 2:
        cropOD = OD[:, :, roiy[0]:roiy[1], roix[0]:roix[1] ]
    if Nvars == 3:
        cropOD = OD[:, :, :, roiy[0]:roiy[1], roix[0]:roix[1] ]

    return cropOD