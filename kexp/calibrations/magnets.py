from artiq.experiment import portable, TFloat
import numpy as np

from kexp.calibrations.imaging import \
    slope_imaging_frequency_per_iouter_current_pid, slope_imaging_frequency_per_iouter_current_supply, \
    yintercept_imaging_frequency_per_iouter_current_pid, yintercept_imaging_frequency_per_iouter_current_supply

@portable
def pid_current_to_outer_supply_setpoint(i_pid) -> TFloat:
    """For a given actual current i_pid (as read by a transducer), returns the
    current set point which should be fed to the supply so that it actually
    supplies the desired current.

    Args:
        i_pid (float): The desired actual current in amps.

    Returns:
        TFloat: the current the supply should be set to to get the actual
        desired current.
    """    
    m_pid = slope_imaging_frequency_per_iouter_current_pid
    m_sup = slope_imaging_frequency_per_iouter_current_supply
    b_pid = yintercept_imaging_frequency_per_iouter_current_pid
    b_sup = yintercept_imaging_frequency_per_iouter_current_supply
    return (m_pid * i_pid + b_pid - b_sup) / m_sup

### Note that these need to be updated to be in terms of the transducer-measured current.
@portable
def i_outer_to_magnetic_field(i_outer) -> TFloat:
    # k-jam\analysis\measurements\magnetometry_high_field.ipynb
    # run ID 10575
    i = np.asarray(i_outer)
    slope_G_per_A, y_intercept_G = [2.84103112, 1.33805367]
    return slope_G_per_A * i + y_intercept_G

def magnetic_field_to_i_outer(b) -> TFloat:
    # k-jam\analysis\measurements\magnetometry_high_field.ipynb
    # run ID 10575
    b = np.asarray(b)
    slope_G_per_A, y_intercept_G = [2.84103112, 1.33805367]
    return (b - y_intercept_G) / slope_G_per_A