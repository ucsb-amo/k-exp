import numpy as np

N_uru = 2
N_ch = 4
shape = (N_uru,N_ch)
dds_list = np.zeros(shape)

def dds_id(uru_idx,ch_idx):
    ids = dds_ids()
    name = ids[uru_idx][ch_idx]["name"]
    aom_order = ids[uru_idx][ch_idx]["aom_order"]
    return name, aom_order
    
def dds_ids():
    '''
    Record the dds variable names (to be called in artiq experiments) and the
    aom order that is used for each AOM here.
    '''

    dds_ids = [[{} for _ in range(N_ch)] for _ in range(N_uru)]

    dds_ids[0][0] = {"names": "push", "aom_order": 1}
    dds_ids[0][1] = {"names": "d2_2d_r", "aom_order": 1}
    dds_ids[0][2] = {"names": "d2_2d_c", "aom_order": -1}
    dds_ids[0][3] = {"names": "d2_3d_r", "aom_order": 1}
    dds_ids[1][0] = {"names": "d2_3d_c", "aom_order": -1}
    dds_ids[1][1] = {"names": "imaging", "aom_order": 1}
    dds_ids[1][2] = {"names": "d1_3d_r", "aom_order": 1}
    dds_ids[1][3] = {"names": "d1_3d_c", "aom_order": -1}

    return dds_ids

