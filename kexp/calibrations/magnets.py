from artiq.experiment import portable, TFloat
import numpy as np

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