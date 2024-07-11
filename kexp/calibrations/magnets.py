def i_outer_to_magnetic_field(i_outer):
    # k-jam\analysis\measurements\magnetometry_high_field.ipynb
    # run ID 10575
    slope_G_per_A, y_intercept_G = [2.84103112, 1.33805367]
    return slope_G_per_A * i_outer + y_intercept_G