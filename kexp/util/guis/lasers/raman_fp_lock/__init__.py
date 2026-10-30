"""The Raman laser's FP-cavity peak-separation lock on the K machine: the waxx
FP lock server and panel (``waxx.util.guis.fp_lock``) with this machine's
port, id, log folder and sweep edges."""

#: Discovery id of the lock server.
SERVER_ID = "raman_fp_lock"
#: The cavity sweep (sawtooth) is 120 ms long: the second-peak warning fires
#: within EDGE_MARGIN_MS of it, the first-peak warning within EDGE_MARGIN_MS of 0.
RIGHT_EDGE_MS = 120.0
EDGE_MARGIN_MS = 10.0
