def crop_OD(OD,crop_type='mot'):

    if crop_type == 'mot':
        roix = [850,1450]
        roiy = [250,1200]
    elif crop_type == 'gm':
        roix = [850,1450]
        roiy = [250,1200]
    else:
        roix = [0,np.shape(OD)[1]-1]
        roiy = [0,np.shape(OD)[0]-1]

    cropOD = OD[ roiy[0]:roiy[1], roix[0]:roix[1] ]
    return cropOD