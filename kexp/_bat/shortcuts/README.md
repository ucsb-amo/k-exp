# Shortcuts

`ar.lnk` runs `artiq_run --device-db %db%` directly. `kq.bat` is the run queue's command
line (`kq --help`); `ar_queue.bat` is `kq run`: it submits to the monitor server's queue and
prints the run's output as `artiq_run` would. To make `ar` submit to the queue, once the
monitor server runs the queue, replace `ar.lnk` with a copy of `ar_queue.bat` named `ar.bat`;
`artiq_run --device-db %db% <file>.py` stays the direct path, outside the queue.
