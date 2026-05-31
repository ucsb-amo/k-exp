"""Interlock safe-mode reference.

This module documents and centralizes the constants and contract for the
interlock's "safe mode" — entered when the server cannot trust its own
inputs (bad COM port, unreachable relay at startup, configuration mismatch
per IT15 in the plan).

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

# Reasons we'd enter safe mode.  Strings used both as log tags and as the
# ``message`` field in the snapshot.
REASON_BAD_COM_PORT = "configured COM port does not enumerate"
REASON_RELAY_UNREACHABLE_AT_BOOT = "relay unreachable at startup"
REASON_WATCHDOG_FORCED = "main poll loop frozen (watchdog trip)"

# Exit codes from interlock_server.py main():
EXIT_NORMAL = 0
EXIT_BAD_CONFIG = 1
EXIT_WATCHDOG = 2
EXIT_ALREADY_RUNNING = 3


__all__ = [
    "STATE_OK", "STATE_TRIPPED", "STATE_WARMUP", "STATE_SAFE_MODE", "STATE_UNKNOWN",
    "REASON_BAD_COM_PORT", "REASON_RELAY_UNREACHABLE_AT_BOOT", "REASON_WATCHDOG_FORCED",
    "EXIT_NORMAL", "EXIT_BAD_CONFIG", "EXIT_WATCHDOG", "EXIT_ALREADY_RUNNING",
]
