from artiq.experiment import portable, TFloat
import numpy as np

from kexp.calibrations.imaging import \
    slope_imaging_frequency_per_iouter_current_pid, slope_imaging_frequency_per_iouter_current_supply, \
    yintercept_imaging_frequency_per_iouter_current_pid, yintercept_imaging_frequency_per_iouter_current_supply

m_pid = slope_imaging_frequency_per_iouter_current_pid
m_sup = slope_imaging_frequency_per_iouter_current_supply
b_pid = yintercept_imaging_frequency_per_iouter_current_pid
b_sup = yintercept_imaging_frequency_per_iouter_current_supply

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
    return (m_pid * i_pid + b_pid - b_sup) / m_sup

@portable
def outer_supply_setpoint_to_pid_current(i_sup) -> TFloat:
    """For a given supply setpoint current (i_sup), returns the corresponding
    actual output current.

    Args:
        i_sup (float): The supply set point in amps.

    Returns:
        TFloat: the actual current that the magnets will see in amps.
    """    
    return (m_sup * i_sup + b_sup - b_pid) / m_pid

@portable
def i_outer_to_magnetic_field(i_outer) -> TFloat:
    """For a given real current (measured by PID transducer), gives the magnetic
    field produced by the outer coils.

    Args:
        i_outer (float): the current in A.

    Returns:
        TFloat: The magnetic field produced.
    """    
    # k-jam\analysis\measurements\magnetometry_high_field.ipynb
    # run ID 10575
    i = np.asarray(i_outer)
    i = pid_current_to_outer_supply_setpoint(i_outer)
    slope_G_per_A, y_intercept_G = [2.84103112, 1.33805367]
    return slope_G_per_A * i + y_intercept_G

@portable
def magnetic_field_to_i_outer(b) -> TFloat:
    """Finds the outer coil current which gives the specified magnetic field
    (G). Current is real current, as measured by the PID transducer.

    Args:
        b (float): the desired field in gauss.

    Returns:
        TFloat: The real current which gives the desired field.
    """    
    # k-jam\analysis\measurements\magnetometry_high_field.ipynb
    # run ID 10575
    b = np.asarray(b)
    slope_G_per_A, y_intercept_G = [2.84103112, 1.33805367]
    i = (b - y_intercept_G) / slope_G_per_A
    i = outer_supply_setpoint_to_pid_current(i)
    return i