"""Lab-specific dashboard glue for kexp.

The generic, reusable dashboard framework lives in
``waxx.util.dashboard``.  This package contains only the kexp-specific
pieces:

* :mod:`server_registry` / :mod:`client_registry` - the actual panels we
  want to show in the lab
* :mod:`server_dashboard_app` / :mod:`client_dashboard_app` - entry
  points that configure waxx for kexp (log dir, host autostart table,
  layout overrides, QSettings org) and launch the framework window.
"""
