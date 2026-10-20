"""K-machine calibration analyses (the registry ``kexp.config.calibration`` names).

Each module here defines ``calibrate(ad, key, **opts) -> CalResult`` (the
contract in ``waxx.calibration.analysis``) and is found by its module name:
``self.calibrates('t_raman_pi_pulse', analysis='rabi_pi_time')`` uses
``rabi_pi_time.calibrate``. ``kcal analyses`` lists them.

Generic fits stay in waxa (``waxa.fitting``, ``waxa.analysis``); a module here
picks the data, calls the fit, and reports the number with its uncertainty,
the shots it used and every shot it left out.
"""
