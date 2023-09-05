import numpy as np

def als_power_to_voltage(power_watts):
    voltage_divider_factor_als_to_dac = 3.7/10

    v_remote_in_data = [0,1,2,3,4,4.88,5]
    p_data = [0.4,9.3,18.3,27.4,36.8,45.0,46.3]

    v_remote_wanted = np.interp(power_watts,p_data,v_remote_in_data)

    v_dac = v_remote_wanted / voltage_divider_factor_als_to_dac

    if v_dac > 9.99:
        raise ValueError("The voltage required to reach this power exceeds the maximum DAC voltage.")

    return v_dac

def als_voltage_to_power(voltage):

    voltage_divider_factor_als_to_dac = 3.7/10

    v_remote_in_data = [0,1,2,3,4,4.88,5]
    p_data = [0.4,9.3,18.3,27.4,36.8,45.0,46.3]

    voltage_als = voltage * voltage_divider_factor_als_to_dac

    power = np.interp(voltage_als,v_remote_in_data,p_data)

    return power