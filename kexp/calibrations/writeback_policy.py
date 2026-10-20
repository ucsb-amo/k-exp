"""Write-back policy for calibrated params (waxx.calibration).

``POLICY`` maps a params key (an ``ExptParams`` attribute) to the hard checks a
calibration of it must pass before it is written back into the params file::

    POLICY = {
        "<key>": {
            "max_frac_change": 0.05,  # |new - old| / |old| above this -> flagged
            "min": 1.e-6,             # value below this -> flagged
            "max": 2.e-5,             # value above this -> flagged
            "min_shots": 20,          # fewer shots used than this -> flagged
            "max_rel_unc": 0.02,      # unc / |value| above this -> flagged
            "unit": "s",              # shown in the [cal] line when the analysis gives none
        },
    }

Every field is optional; a field this schema does not know is refused (so a
typo cannot switch a check off). A key with NO entry has no hard checks: only
the rules that need no policy apply (the analysis failed, the value or its
uncertainty is not finite, there is no uncertainty). A flagged result is never
written back; it is recorded in the ledger and printed.

Thresholds are a lab decision. None is set here; the entry below is an example
of the form only, left commented on purpose.
"""

POLICY = {
    # "t_raman_pi_pulse": {
    #     "max_frac_change": ...,
    #     "min": ...,
    #     "max": ...,
    #     "min_shots": ...,
    #     "max_rel_unc": ...,
    #     "unit": "s",
    # },
}
