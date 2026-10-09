"""The K machine's calibration config (waxx.calibration.CalibrationConfig).

``kexp.Base`` hands ``CALIBRATION_CONFIG`` to every experiment
(``self.calibration_config``), so ``self.calibrates(key, analysis=...)`` works
in any K experiment. The ``kcal`` CLI finds it through the environment::

    set WAXX_CALIBRATION_CONFIG=kexp.config.calibration:CALIBRATION_CONFIG
    kcal show t_raman_pi_pulse

or per call: ``kcal --config kexp.config.calibration:CALIBRATION_CONFIG show ...``
(also ``python -m waxx.calibration ...``).

- ledger: ``<data root>\\calibrations`` -- ``calibrations.jsonl`` plus
  ``<key>\\<run_id>.json`` / ``.png``. The data root is taken the way
  ``kexp.config.live_od`` takes it (``kexp.config.ip.PATHS``), and only when the
  ledger is first used: importing this module touches nothing.
- policy: ``kexp.calibrations.writeback_policy.POLICY`` (empty = no hard checks).
- analyses: ``kexp.analysis.calibrations.<name>.calibrate``.
- params: ``kexp.config.expt_params.ExptParams`` when a ledger record names no
  class (a run records the class it used, e.g. a project's subclass).
- runs load read-only, never lite, with kexp's server_talk: ``atomdata(run_id,
  roi_id='auto', lite=False)`` when an analysis needs the images, else with
  ``ignore_images=True``. A full load still reads every DataVault container,
  diagnostic stream frames included (waxa has no option to leave them out of
  a full load); the load runs under ``load_budget_s`` (60 s).
"""

import os

from waxx.calibration.config import CalibrationConfig


def _ledger_dir():
    from kexp.config.ip import PATHS
    data_root = PATHS[0]
    if not data_root:
        raise RuntimeError("the data root (%data%) is not set on this machine: there is no "
                           "calibration ledger to write")
    return os.path.join(data_root, "calibrations")


def _load_run(run_id, needs_images=False):
    """Read-only, never lite (a lite load can write a lite copy beside the
    data). Without images (no analysis of the run asked for them) the camera
    frames, OD and ROI are skipped; with them, the ROI is found headless
    (roi_id='auto', never a dialog)."""
    from waxa import atomdata
    from kexp.config.ip import server_talk
    return atomdata(int(run_id), roi_id="auto" if needs_images else None, lite=False,
                    ignore_images=not needs_images, server_talk=server_talk)


CALIBRATION_CONFIG = CalibrationConfig(
    ledger_dir=_ledger_dir,
    policy="kexp.calibrations.writeback_policy",
    registry_modules=("kexp.analysis.calibrations",),
    params_class="kexp.config.expt_params:ExptParams",
    loader=_load_run,
)
