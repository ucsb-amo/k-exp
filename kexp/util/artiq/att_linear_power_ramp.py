import numpy as np

def att_list_for_linear_power_ramp(att_i, att_f, N):
    p_i = 10**(- att_i)
    p_f = 10**(- att_f)
    dp = (p_f - p_i)/N
    if dp < 0: dp = -dp
    if att_i > att_f:
        # if att_i > att_f, less power initially than at the end (increasing ramp)
        p = np.arange(p_i,p_f+dp,dp)
    elif att_f > att_i:
        # if att_f > att_i, more power initially (decreasing ramp)
        p = np.flip( np.arange( p_f, p_i+dp, dp ) )
    att = -np.log10(p)
    return att,p