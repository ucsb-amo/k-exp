import numpy as np

def crop_OD(OD,crop_type='',Nvars=1):

    if len(np.shape(OD)) <= 2:
        OD = np.array([OD])

    if crop_type == 'bigmot':
        roix = [500, 1500]
        roiy = [100, 1200]
    elif crop_type == 'mot':
        roix = [710,1000]
        roiy = [300,580]
    elif crop_type == 'cmot':
        roix = [600,1100]
        roiy = [300,800]
    elif crop_type == 'gm':
        roix = [500,1250]
        roiy = [200,1000]
    elif crop_type == 'gm_smol':
        roix = [600,1050]
        roiy = [350,800]
    elif crop_type == 'magtrap':
        roix = [500,1300]
        roiy = [500,1200]
    elif crop_type == 'lightsheet':
        roix = [840,980]
        roiy = [400,800]
    elif crop_type == 'lightsheet_zaxis':
        roix = [750,970]
        roiy = [500,780]
    elif crop_type == 'lightsheet_short':
        roix = [880,970]
        roiy = [610,750]
    elif crop_type == 'xy_tweezer':
        roix = [950,1150]
        roiy = [630,700]
    elif crop_type == 'andor_tweezer':
        roix = [210,271]
        roiy = [253,284]
    elif crop_type == 'andor_tweezer_wide_putin':
        roix = [180,260]
        roiy = [220,250]
    elif crop_type == 'andor_lightsheet':
        roix = [110,360]
        roiy = [180,400]
    elif crop_type == 'andor_lightsheet_tight':
        roix = [140,330]
        roiy = [200,370]
    elif crop_type == 'andor_tweezer_smol':
        roix = [200,220]
        roiy = [220,250]
    elif crop_type == 'andor_single_tweezer':
        roix = [170,240]
        roiy = [250,330]
    elif crop_type == 'xy2_lightsheet':
        roix = [1101,1300]
        roiy = [401,1200]
    elif crop_type == 'xy2_tweezer':
        roix = [660,770]
        roiy = [1050,1200]
    else:
        print('no matching roi found, defaulting to whole image')
        roix = [0,np.shape(OD)[len(np.shape(OD))-1]]
        roiy = [0,np.shape(OD)[len(np.shape(OD))-2]]

    if Nvars == 1:
        cropOD = OD[:, roiy[0]:roiy[1], roix[0]:roix[1] ]
    if Nvars == 2:
        cropOD = OD[:, :, roiy[0]:roiy[1], roix[0]:roix[1] ]
    if Nvars == 3:
        cropOD = OD[:, :, :, roiy[0]:roiy[1], roix[0]:roix[1] ]

    return cropOD
