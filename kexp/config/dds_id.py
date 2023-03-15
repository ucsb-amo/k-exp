def dds_id(uru_idx,ch_idx):
    ids = define_dds_id()
    name = ids["name"][uru_idx][ch_idx]
    aom_order = ids["aom_order"][uru_idx][ch_idx]
    return name, aom_order
    
def define_dds_id():
    dds_ids = dict()
    names = []
    names.append([
        "push",
        "d2_2d_r",
        "d2_2d_c",
        "d2_3d_r"
        ])
    names.append([
        "d2_3d_c",
        "imaging",
        "d1_3d_r",
        "d1_3d_c",
        ])
    orders = []
    orders.append([1,1,-1,1])
    orders.append([-1,1,1,-1])
    dds_ids["name"] = names
    dds_ids["aom_order"] = orders
    return dds_ids

