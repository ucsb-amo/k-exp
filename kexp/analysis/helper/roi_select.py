def crop_OD(OD,roi_type='mot'):
    if roi_type == 'full':
        roix = [0,np.shape(OD)[1]-1]
        roiy = [0,np.shape(OD)[0]-1]
    if roi_type == 'mot':
        roix = [850,1450]
        roiy = [250,1200]
    elif roi_type == 'gm':
        roix = [850,1450]
        roiy = [250,1200]

    cropOD = OD[ roiy[0]:roiy[1], roix[0]:roix[1] ]
    return cropOD