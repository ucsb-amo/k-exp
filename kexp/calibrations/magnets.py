from artiq.experiment import portable, TFloat
import numpy as np

# obtain calibration by running
# kexp/experiments/measurements/measure_currents_vs_setpoint_pid_and_supply.py
# analyze with
# k-jam/analysis/measurements/current_vs_setpoint_pid_and_supply.ipynb

slope_i_transducer_per_v_setpoint_supply_outer = 50.84570263249882
offset_i_transducer_per_v_setpoint_supply_outer = 0.6609996609503291

slope_i_transducer_per_v_setpoint_pid_outer  = 40.01587069690042
offset_i_transducer_per_v_setpoint_pid_outer  = -0.3520810805908351

# @portable
# def transducer_current_to_outer_supply_dac_setpoint(i_transducer) -> TFloat:
#     return (i_transducer - offset_i_transducer_per_v_setpoint_supply_outer) / slope_i_transducer_per_v_setpoint_supply_outer

# @portable
# def outer_supply_dac_setpoint_to_transducer_current(v_setpoint) -> TFloat:
#     return slope_i_transducer_per_v_setpoint_supply_outer * v_setpoint + offset_i_transducer_per_v_setpoint_supply_outer

# @portable
# def transducer_current_to_outer_pid_setpoint(i_transducer) -> TFloat:
#     return (i_transducer - offset_i_transducer_per_v_setpoint_pid_outer) / slope_i_transducer_per_v_setpoint_pid_outer

# @portable
# def outer_pid_setpoint_to_transducer_current(v_setpoint) -> TFloat:
#     return slope_i_transducer_per_v_setpoint_pid_outer * v_setpoint + offset_i_transducer_per_v_setpoint_pid_outer

@portable
def compute_pid_overhead(i_pid) -> TFloat:
    """Computes current overhead such that shunt MOSFET gate voltage sits at
    a roughly fixed value (~6V).

    Numbers worked out by observing shunted current and real current over a
    range of set points, described in notes here:
    https://docs.google.com/document/d/11WCgrdBnUMHi8nWz7Vp8wVUJYQWNkQWty88WbOmQMoo/edit?tab=t.0#heading=h.b4wsdlxg4uov

    Args:
        i_pid (float): pid current (in A)

    Returns:
        float: the excess current (in A) that the keysight will run over the desired pid current
    """        
    keysight_overhead = i_pid * 0.3569422 - 0.04
    return keysight_overhead

####
# The data below data should be retaken! Very old calibration. Once retaken, the
# "transducer current" and "i_supply" thing should be eliminated, and instead
# just use the v_setpoint to transducer current calibration functions above to
# directly set the current to what we want

# obtain calibration by running
# kexp/experiments/measurements/measure_i_transducer_per_i_supply.py
# analyze with
# k-jam/analysis/measurements/i_transducer_per_i_supply.ipynb
slope_i_transducer_per_i_supply = 1.0168888389645203
offset_i_transducer_per_i_supply = 0.6426955097172109

@portable
def i_transducer_to_magnetic_field(i_transducer) -> TFloat:
    """For a given real current (measured by transducer), gives the magnetic
    field in Gauss produced by the outer coils.

    Args:
        i_supply (float): the current in A.

    Returns:
        TFloat: The magnetic field produced in Gauss (G).
    """    
    # k-jam\analysis\measurements\magnetometry_high_field.ipynb
    # run ID 10575
    i = np.asarray(i_transducer)
    i = (i - offset_i_transducer_per_i_supply ) / slope_i_transducer_per_i_supply
    slope_G_per_A, y_intercept_G = [2.84103112, 1.33805367]
    return slope_G_per_A * i + y_intercept_G

@portable
def magnetic_field_to_i_transducer(b) -> TFloat:
    """Finds the outer coil current which gives the specified magnetic field
    (G). Current is real current, as measured by the transducer.

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
    i = slope_i_transducer_per_i_supply * i + offset_i_transducer_per_i_supply
    return i
