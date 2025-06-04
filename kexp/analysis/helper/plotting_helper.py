import numpy as np

def xlabels_1d(xvar0, xvarmult, xvarformat):
    xvarlabels = []
    for val in xvar0:
        label = ""
        if isinstance(val,np.ndarray) or isinstance(val,list):
            for i in range(len(val)):
                if i == 0:
                    label += "["
                if i != 0:
                    label += ", "
                label += f"{val[i]*xvarmult:{xvarformat}}"
                if i == (len(val)-1):
                    label += "]"
        else:
            label += f"{val*xvarmult:{xvarformat}}"
        xvarlabels.append(label)
    return xvarlabels