import numpy as np

def normalize(array,map_minimum_to_zero=False):
    x = np.asarray(array)
    if map_minimum_to_zero:
        x = (x-np.min(x))/(np.max(x)-np.min(x))
    else:
        x = (x)/(np.max(x))
    return x

def rm_outliers(array,
                outlier_method='mean',
                center_method='mean',
                outlier_threshold=0.3,
                return_outlier_mask = True,
                return_outlier_idx = False,
                return_good_data = False,
                return_good_data_idx = False):
    
    x = array
    
    if outlier_method == 'mean':
        mask = np.abs(x/np.mean(x) - 1) < outlier_threshold
    elif outlier_method == 'std':
        mask = np.abs(x - np.mean(x)) < (np.std(x) * outlier_threshold)
    else:
        raise ValueError("`outlier_method` must be either 'mean' or 'std'")
    
    out = ()
    if return_outlier_mask:
        out += (mask,)
    if return_outlier_idx:
        outlier_idx = np.arange(len())[~mask].astype(int)
        out += (outlier_idx,)
    if return_good_data:
        out += (x[mask],)
    if return_good_data_idx:
        good_idx = np.arange(len())[mask].astype(int)
        out += (good_idx,)

    if len(out) == 1:
        out = out[0]

    return out

def rms(x):
    return np.sqrt(np.sum(x**2)/len(x))

