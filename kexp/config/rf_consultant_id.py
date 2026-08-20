"""Compatibility shim — the RF consultant identity map now lives in beacon.

The canonical file is ``beacon/tpi/rf_consultant_id.py``.  Add/relabel
consultants THERE.  This module simply re-exports its public API so existing
``from kexp.config import rf_consultant_id`` call sites keep working, and the
live-reload (``reload_module=True``) still targets the beacon module.
"""
from beacon.tpi.rf_consultant_id import (  # noqa: F401
    RfConsultantId,
    default_map,
    label_map,
    load_frame,
    rf_consultant_frame,
)

__all__ = [
    "RfConsultantId",
    "rf_consultant_frame",
    "load_frame",
    "label_map",
    "default_map",
]
