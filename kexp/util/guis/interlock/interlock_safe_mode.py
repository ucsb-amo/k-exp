"""Interlock safe-mode reference.

This module documents and centralizes the constants and contract for the
interlock's "safe mode" — entered when the server cannot trust its own
inputs (configuration mismatch per IT15 in the plan).  Nothing enters it at
present; ``InterlockService.enter_safe_mode`` keeps the contract below.

A relay that does not answer (at startup or later) is **not** a safe-mode
reason (since 2026-11-16): the server keeps running -- PLC monitoring, the
trip path, the panel -- and reports ``state="relay_down"`` with the relay's
address and since when.  Enable is refused while the relay is down; a trip
keeps retrying the kill until the relay answers.  When the relay answers
again, the server returns to normal and leaves the magnet relay as it is
(as a normal startup does), except that a startup kill owed because the
COM port was missing is done then.  It used to enter safe mode, whose
watchdog then killed the process about a minute after start (the panel
only ever saw "server unreachable").

**Safety-critical behavior in safe mode**

1. On entering safe mode, the server immediately attempts to call
   ``EthernetRelay.kill_magnets()`` once (best-effort).  If the relay is
   reachable this is the *only* defense against running magnets with no
   monitoring.
2. While in safe mode, ``reset_interlock()`` RPCs are refused with an
   explicit reason.
3. ``enable_magnets()`` RPC is refused with an explicit reason.
4. The status snapshot reports ``state="safe_mode"`` and ``message=<reason>``
   so the dashboard surfaces the condition prominently.
5. Safe mode is **terminal**: exit requires restarting the server with the
   underlying configuration problem fixed.

A COM port that does not enumerate at startup is no longer a safe-mode
reason: the magnets are killed once the same way, the server keeps running
and its COM link keeps retrying the port, and Enable stays refused until a
good PLC frame arrives (``InterlockService.start``).  ``REASON_BAD_COM_PORT``
names that condition in the log and the status message.

The hardware PLC interlock remains the primary safety system at all times.
Safe mode is the software backstop against silent failure of the software
monitoring path.
"""

from __future__ import annotations

# Status string values used in the snapshot returned to clients.
STATE_OK = "ok"
STATE_TRIPPED = "tripped"
STATE_WARMUP = "warmup"
STATE_SAFE_MODE = "safe_mode"
STATE_UNKNOWN = "unknown"
# Reported in the snapshot (not an internal state) while the interlock would
# otherwise read ok / warmup / unknown but the relay does not answer.
STATE_RELAY_DOWN = "relay_down"

# Reasons used both as log tags and as the ``message`` field in the snapshot.
REASON_BAD_COM_PORT = "configured COM port does not enumerate"
REASON_WATCHDOG_FORCED = "main poll loop frozen (watchdog trip)"

# Exit codes from interlock_server.py main():
EXIT_NORMAL = 0
EXIT_BAD_CONFIG = 1
EXIT_WATCHDOG = 2
EXIT_ALREADY_RUNNING = 3


__all__ = [
    "STATE_OK", "STATE_TRIPPED", "STATE_WARMUP", "STATE_SAFE_MODE", "STATE_UNKNOWN",
    "STATE_RELAY_DOWN",
    "REASON_BAD_COM_PORT", "REASON_WATCHDOG_FORCED",
    "EXIT_NORMAL", "EXIT_BAD_CONFIG", "EXIT_WATCHDOG", "EXIT_ALREADY_RUNNING",
]
