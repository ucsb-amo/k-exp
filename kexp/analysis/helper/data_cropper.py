import numpy as np

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