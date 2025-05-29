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

def crop_array_by_index(array,include_idx=[0,-1],exclude_idx=[]):
    """Crops an array to include data between bounding indices in `include_idx`,
    and excludes data at the indices specified as a list in `exclude_idx`.

    Args:
        array (_type_): The array to be cropped.
        include_idx (list, optional): The bounding indices of the data to be
        returned. Defaults to [0,-1], where -1 specifies including the last
        element in the list.
        exclude_idx (list, optional): Indices of the data to be removed,
        specified as indices in the original data array (not within the
        sub-array specified by `include_idx`). Defaults to [], meaning no
        indices will be excluded (other than those omitted in the range
        speficied as `include_idx`.)

    Returns:
        array: the array with the specified elements removed.
    """
    array = np.asarray(array)
    idx0 = int(include_idx[0])
    if include_idx[1] == -1:
        idxf = len(array)
        array = array[idx0:]
    else:
        idxf = int(include_idx[1])
        array = array[idx0:idxf]
    
    if exclude_idx:
        exclude_idx = np.array(exclude_idx) - idx0
        exclude_idx = np.intersect1d(exclude_idx,range(idxf-idx0)).astype(int)
        array = np.delete(array,exclude_idx)

    return array

def find_n_max_indices(arr, N):
    """Find the indices of the N maximum values in a numpy ndarray."""
    if N > arr.size:
        raise ValueError("N cannot be greater than the number of elements in the array.")
    
    # Get the indices of the top N values
    indices = np.argpartition(arr.flatten(), -N)[-N:]  # Unsorted top N indices
    sorted_indices = indices[np.argsort(-arr.flatten()[indices])]  # Sort indices by value
    
    # Convert back to multi-dimensional indices
    return [tuple(idx) for idx in np.array(np.unravel_index(sorted_indices, arr.shape)).T]

def get_repeat_std_error(array,N_repeats):
    if isinstance(N_repeats,np.ndarray):
        N_repeats = N_repeats[0]
        
    Nr = N_repeats
    means = np.mean(np.reshape(array,(-1,Nr)),axis=1)
    std_error = np.std(np.reshape(array,(-1,Nr)),axis=1)/np.sqrt(Nr)

    return means, std_error