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
        roix = [500,1250]
        roiy = [200,1000]
    elif crop_type == 'magtrap':
        roix = [500,1300]
        roiy = [500,1200]
    elif crop_type == 'lightsheet':
        roix = [870,960]
        roiy = [500,800]
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
        roix = [170,261]
        roiy = [237,305]
    elif crop_type == 'andor_lightsheet':
        roix = [110,360]
        roiy = [180,400]
    elif crop_type == 'andor_lightsheet_tight':
        roix = [140,330]
        roiy = [200,370]
    elif crop_type == 'andor_tweezer_smol':
        roix = [212,238]
        roiy = [249,275]
    elif crop_type == 'andor_single_tweezer':
        # roix = [255,325]
        # roiy = [245,320]
        roix = [180,255]
        roiy = [280,330]
    else:
        print('no matching roi found, defaulting to whole image')
        roix = [0,np.shape(OD)[len(np.shape(OD))-1]]
        roiy = [0,np.shape(OD)[len(np.shape(OD))-2]]

    # cropOD = "OD[" + ", ".join(":" for _ in range(Nvars)) + ", " + \
    #             f"{roiy[0]}:{roiy[1]}, {roix[0]}:{roix[1]}" + "]"

    if Nvars == 1:
        cropOD = OD[:, roiy[0]:roiy[1], roix[0]:roix[1] ]
    if Nvars == 2:
        cropOD = OD[:, :, roiy[0]:roiy[1], roix[0]:roix[1] ]
    if Nvars == 3:
        cropOD = OD[:, :, :, roiy[0]:roiy[1], roix[0]:roix[1] ]
    if Nvars == 4:
        cropOD = OD[:, :, :, :, roiy[0]:roiy[1], roix[0]:roix[1] ]
    if Nvars == 5:
        cropOD = OD[:, :, :, :, :, roiy[0]:roiy[1], roix[0]:roix[1] ]
    if Nvars == 6:
        cropOD = OD[:, :, :, :, :, :, roiy[0]:roiy[1], roix[0]:roix[1] ]

    #cropOD = np.take(OD, roiy[0]:roiy[1], roix[0]:roix[1] )

    #cropOD = OD["".join(":" for _ in range(Nvars)) + ", ", roiy[0]:roiy[1], roix[0]:roix[1] ]
    return cropOD