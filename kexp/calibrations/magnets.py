from artiq.experiment import portable, TFloat
import numpy as np

# obtain calibration by running
# kexp/experiments/measurements/measure_i_pid_per_i_outer.py
# analyze with
# k-jam/analysis/measurements/i_pid_per_i_outer.ipynb

slope_i_pid_per_i_outer = 1.0168583974549856
offset_i_pid_per_i_outer = 0.6553740218059771

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
    return (i_pid - offset_i_pid_per_i_outer) / slope_i_pid_per_i_outer

@portable
def outer_supply_setpoint_to_pid_current(i_sup) -> TFloat:
    """For a given supply setpoint current (i_sup), returns the corresponding
    actual output current.

    Args:
        i_sup (float): The supply set point in amps.

    Returns:
        TFloat: the actual current that the magnets will see in amps.
    """    
    return slope_i_pid_per_i_outer * i_sup + offset_i_pid_per_i_outer

@portable
def i_outer_to_magnetic_field(i_outer) -> TFloat:
    """For a given real current (measured by PID transducer), gives the magnetic
    field in Gauss produced by the outer coils.

    Args:
        i_outer (float): the current in A.

    Returns:
        TFloat: The magnetic field produced in Gauss (G).
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