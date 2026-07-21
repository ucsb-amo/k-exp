"""RF consultant (TPI-1005-A signal generator) identity map.

RF consultants are identified by their firmware **serial number** — the ASCII
serial returned by ``TPI1005A.get_serial()`` (``waxx.control.misc.tpi``) and
surfaced by the TPI server/client as ``TpiDeviceClient.serial``.  The serial is
stable per physical unit and is what the server keys devices by, so it is the
natural primary identifier.

This module assigns a human-friendly *key* to each known serial so GUIs and
experiments can refer to a consultant by role (e.g. ``raman_rf``) instead of a
bare serial string.

Frame convention
----------------
Mirrors the other ``*_id.py`` frames in :mod:`kexp.config` (see
``dds_id.py`` / ``siglent_id.py``): assignment statements bind each device to a
frame attribute, and :meth:`rf_consultant_frame.cleanup` stamps the attribute
name onto the entry as its ``key`` (exactly as ``dds_frame`` does for DDS
objects).

To (re)assign a consultant: plug the device into the TPI GUI, read its serial
from the dock title, and add one line in ``rf_consultant_frame.__init__``::

    self.raman_rf = self.assign("299", name="Raman RF", notes="80 MHz arm")

The attribute name (``raman_rf``) becomes the consultant's key.

Live reload
-----------
Clients read the *latest* version of this file at runtime via
:func:`label_map` (which re-executes the module before building the frame), so
edits here are picked up by a running GUI on its next device rescan without a
process restart.
"""

from __future__ import annotations

import sys


class RfConsultantId:
    """Identity record for one RF consultant (one TPI-1005-A), keyed by serial.

    ``key`` is set by :meth:`rf_consultant_frame.cleanup` to the frame attribute
    the record was assigned to.  ``name``/``notes`` are optional human context.
    """

    def __init__(self, serial: str, name: str = "", notes: str = "") -> None:
        self.serial: str = str(serial)
        self.name: str = name
        self.notes: str = notes
        self.key: str = ""  # set by cleanup() -> the frame attribute name

    @property
    def display_name(self) -> str:
        """Best user-facing label: explicit name, else the assigned key, else serial."""
        return self.name or self.key or self.serial

    def __repr__(self) -> str:
        return (
            f"RfConsultantId(serial={self.serial!r}, key={self.key!r}, "
            f"name={self.name!r})"
        )


class rf_consultant_frame:
    """Maps RF-consultant serial numbers to human-friendly keys/names.

    Add one ``self.<key> = self.assign(<serial>, ...)`` line per known device in
    :meth:`__init__`.  The attribute name becomes the consultant's ``key``.
    """

    def __init__(self) -> None:
        self.setup()

        # ---- assignments: serial -> frame attribute (== key) -------------
        # self.raman_rf = self.assign("299", name="Raman RF")
        # self.antenna_rf = self.assign("301", name="Antenna RF")

        self.cleanup()

    # ------------------------------------------------------------------ #
    # Frame lifecycle (mirrors dds_id.py / siglent_id.py)
    # ------------------------------------------------------------------ #

    def setup(self) -> None:
        self._by_serial: dict[str, RfConsultantId] = {}

    def assign(self, serial: str, name: str = "", notes: str = "") -> RfConsultantId:
        """Register a consultant by serial and return its identity record.

        Assign the return value to a frame attribute; that attribute name is
        recorded as the consultant's ``key`` in :meth:`cleanup`.
        """
        serial = str(serial)
        if serial in self._by_serial:
            raise ValueError(
                f"RF consultant serial {serial!r} already assigned to "
                f"key {self._by_serial[serial].key or '<pending>'!r}"
            )
        rf = RfConsultantId(serial, name=name, notes=notes)
        self._by_serial[serial] = rf
        return rf

    def cleanup(self) -> None:
        """Stamp each assigned attribute name onto its record as ``key``."""
        for key, val in self.__dict__.items():
            if isinstance(val, RfConsultantId):
                val.key = key

    # ------------------------------------------------------------------ #
    # Lookups
    # ------------------------------------------------------------------ #

    def get(self, serial: str) -> RfConsultantId | None:
        return self._by_serial.get(str(serial))

    def key_for_serial(self, serial: str, default: str = "") -> str:
        rf = self.get(serial)
        return rf.key if rf is not None else default

    def display_name_for_serial(self, serial: str, default: str = "") -> str:
        rf = self.get(serial)
        return rf.display_name if rf is not None else default

    def serials(self) -> list[str]:
        return list(self._by_serial.keys())


# ---------------------------------------------------------------------------
# Fresh-read helpers — used by clients/GUIs to pick up file edits live
# ---------------------------------------------------------------------------

def load_frame(reload_module: bool = True) -> rf_consultant_frame:
    """Return a frame reflecting the current on-disk version of this file.

    With ``reload_module=True`` (default) the module is re-executed first so a
    running client sees edits to the assignment list without a restart.
    """
    if reload_module:
        import importlib  # noqa: PLC0415
        mod = importlib.reload(sys.modules[__name__])
        return mod.rf_consultant_frame()
    return rf_consultant_frame()


def label_map(serials=None, reload_module: bool = True) -> dict[str, str]:
    """Return ``{serial: display_name}`` for known consultants.

    If ``serials`` is given, only those serials that have an assigned identity
    are included (callers fall back to the raw serial for the rest).  Reads the
    freshest version of this file by default.
    """
    frame = load_frame(reload_module=reload_module)
    if serials is None:
        return {s: rf.display_name for s, rf in frame._by_serial.items()}
    out: dict[str, str] = {}
    for s in serials:
        rf = frame.get(s)
        if rf is not None:
            out[str(s)] = rf.display_name
    return out


__all__ = [
    "RfConsultantId",
    "rf_consultant_frame",
    "load_frame",
    "label_map",
]
