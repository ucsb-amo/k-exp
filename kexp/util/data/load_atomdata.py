import os
from kexp.analysis.atomdata import atomdata

def load_atomdata(idx=0, roi_id=None, path = "",
                  skip_saved_roi = False,
                  transpose_idx = [], avg_repeats = False) -> atomdata:
    '''
    Returns the atomdata stored in the `idx`th newest file at `path`.

    Parameters
    ----------
    idx: int
        If a positive value is specified, it is interpreted as a run_id (as
        stored in run_info.run_id), and that data is found and loaded. If zero
        or a negative number are given, data is loaded relative to the most
        recent dataset (idx=0).
    roi_id: None, int, or string
        Specifies which crop to use. If roi_id=None, defaults to the ROI saved in
        the data if it exists, otherwise prompts the user to select an ROI using
        the GUI. If an int, interpreted as an run ID, which will be checked for
        a saved ROI and that ROI will be used. If a string, interprets as a key
        in the roi.xlsx document in the PotassiumData folder.
    path: str
        The full path to the file to be loaded. If not specified, loads the file
        as dictated by `idx`.
    skip_saved_roi: bool
        If true, ignore saved ROI in the data file.
    transpose_idx: list(int)
        A list of indices of length equal to the number of xvars in the dataset.
        If specified, gives the new order of the axes of the data. For example,
        if given as [0 2 1 3], the second and third axes of the dataset will be
        switched.
    avg_repeats: bool
        If true, averages the OD for multiple shots which have the same value
        for all xvars.

    Returns
    -------
    ad: atomdata
    '''

    ad = atomdata(idx,roi_id,path,
                  skip_saved_roi,
                  transpose_idx,
                  avg_repeats)
    return ad