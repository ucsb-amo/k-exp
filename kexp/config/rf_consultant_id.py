"""RF consultants (TPI signal generators) for K-machine experiments: ``self.rf_consultant``.

Nothing to edit here.  Serials, names, defaults and limits are assigned in
``beacon/beacon/tpi/rf_consultant_id.py``, the one file the TPI GUI, notebooks
and experiments all read.  Each assigned consultant appears in an experiment as
``self.rf_consultant.<key>``.

(A limit that should hold in experiments only could be tightened here after
``super().__init__``, e.g. ``self.<key>.limit(max_amplitude_dbm=-5.)``; it can never
be loosened.)
"""
from artiq.coredevice.core import Core

from waxx.config.rf_consultant_id import rf_consultant_frame as rf_consultant_frame_waxx


class rf_consultant_frame(rf_consultant_frame_waxx):
    def __init__(self, core=Core):
        super().__init__(core)
        # super().rf_consultant_980.limit(max_amplitude_dbm=-0.5, max_frequency=600.e6)
