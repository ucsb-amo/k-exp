"""When a person hold on the K machine lapses by itself.

A person hold (liveOD's Reset, the Hold buttons, ``kq hold``) makes agents'
runs wait.  So that a forgotten hold does not block the machine all night, a
hold whose expiry is the default ("policy") lapses once no person activity has
been seen for a while (waxx.util.device_state.person_hold.ExpiryPolicy):

* a hold set by a Reset in liveOD: one hour after the last person activity,
  at any hour (a Reset is usually just aborting a run);
* any hold: in quiet hours -- 19:00 to 07:00, and all of Saturday and Sunday
  -- once an hour has passed with no person activity (a hold that went idle
  during the day lapses at 19:00).

Person activity: a hold request while it is on, a Reset in liveOD, a person's
queue / loop request, a Device Control change, a composite op, a run
announcing itself; a person's queued job running or about to run keeps the hold
on.  A hold put on with "never" (``kq hold --never``, the Hold dialogs) or a set
time (``--for`` / ``--until``) ignores this.  Every lapse is journaled
(``run_queue_hold_lapsed``).  Read by the monitor server at start: a change
takes effect when the monitor server restarts.
"""
from waxx.util.device_state.person_hold import ExpiryPolicy

HOLD_POLICY = ExpiryPolicy(
    idle_s={"live_od_reset": 3600.0},
    quiet_idle_s=3600.0,
    quiet_start_h=19.0,
    quiet_end_h=7.0,
    quiet_weekends=True,
)
