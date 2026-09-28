# Words You'll See — draft, groups 1–4 (editor-in-chief; groups 5–6 come from the research reports)

## 1. Basic code ideas

### One real line, labelled

From `kexp/experiments/default_experiments/mot_tof.py`, inside `scan_kernel`:

```python
self.dds.imaging.set_dds(amplitude=self.camera_params.amp_imaging)
```

Read it right to left, then left to right:

| Piece | What it is | Plain words |
|---|---|---|
| `self` | the object this code belongs to: **the experiment** | "me, this experiment" |
| `.dds` | an **attribute** of the experiment: the DDS frame, which holds every DDS channel | "my collection of DDS channels" |
| `.imaging` | an attribute of the frame: one **object** of the `DDS` class, the channel driving the imaging AOM | "the imaging channel" |
| `.set_dds(...)` | a **method**: a function that belongs to that object | "set it" |
| `amplitude=` | a **keyword argument**: a named input to the method | "the amplitude I want is..." |
| `self.camera_params.amp_imaging` | the **value** passed in: attribute `amp_imaging` of the `camera_params` object (a number between 0 and 1) | "...the imaging amplitude this camera wants" |

Every other snippet on this wiki is made of these same pieces.

### Entries

**file, folder, path** — A file holds text or data; a folder holds files and other folders. A path is the address of a file, written as the folders on the way to it: `k-exp/kexp/config/expt_params.py` means the file `expt_params.py` inside folder `config`, inside `kexp`, inside `k-exp`. Windows writes paths with backslashes (`C:\Users\scientist\code`), the code and this wiki mostly with forward slashes. *Ours:* every parameter default lives in one file, `kexp/config/expt_params.py`.

**program, process** — A program is a file of code you can run. A process is one running copy of it. Two windows of liveOD would be two processes of one program. *Ours:* the LiveOD Server, the monitor server and each experiment run are separate processes, and they talk to each other over the network even on one PC.

**script** — A short program you run directly, top to bottom. *Ours:* the `.bat` files in `kexp/_bat/` are scripts; `mot_observe.py` is run as a script by `ar`.

**module, package, import** — A module is one `.py` file; a package is a folder of modules with an `__init__.py` file in it. `import` brings a module's names into your file. *Ours:* `from kexp import Base` takes the name `Base` out of the package `kexp`. `kexp`, `waxx` and `waxa` are packages.

**variable, value, type** — A variable is a name for a value. The value has a type: a whole number (`int`, `3`), a decimal number (`float`, `0.05e-3`), text (`str`, `'t_tof'`), true/false (`bool`). Comparison: a labelled jar (variable) with something in it (value); the type says whether it holds coins or sand. *Ours:* `t_tof = 0.05e-3` is a float, and ARTIQ insists a parameter keep its type (a float stays a float; see **compile**).

**list, array** — An ordered row of values. A Python list is written `[1., 5., 10.]`. A numpy array (`np.array`, `np.linspace(...)`) is a list built for maths: you can multiply the whole thing at once. *Ours:* `np.linspace(0.03, 1.2, 10)*1.e-3` makes ten evenly spaced times and converts them all from ms to seconds.

**dictionary** — Values looked up by a name (a key) instead of a position: `{"frequency": 110e6, "amplitude": 0.3}`. Comparison: a phone book. *Ours:* the device-state JSON file the Monitor reads is a dictionary of dictionaries.

**function, argument, keyword argument, default value, return value** — A function is a named block of code you can run by writing its name with parentheses. What you put in the parentheses are its arguments. A keyword argument is passed by name, `set_dds(amplitude=0.1)`, so order does not matter. A default value is what an argument takes when you leave it out. The return value is what the function hands back. *Ours:* `Base.__init__(self, camera_select=cameras.xy_basler, save_data=True)` passes two keyword arguments and leaves the rest at their defaults.

**class, object (instance), attribute, method, `self`** — A class is a blueprint; an object is one thing built from it. Attributes are the values an object carries (`dds.frequency`); methods are the functions it can do (`dds.on()`). Inside a class's own code, `self` means "the object this code is running on". *Ours:* `DDS` is a class in `waxx/control/artiq/DDS.py`; `self.dds.imaging` is one `DDS` object; `.set_dds()` is a method; `.frequency` is an attribute.

**constructor (`__init__`)** — The method that runs when an object is built; it sets up the attributes. *Ours:* every experiment calls `Base.__init__(self, ...)` in `prepare`, which builds the device frames, the parameters and the network clients.

**inheritance, parent class, mixin** — A class can be built on another and get all its attributes and methods; the one it builds on is its parent. A mixin is a parent class that adds one bundle of methods and is meant to be combined with others. *Ours:* `class gm_tof(EnvExperiment, Base)` inherits from ARTIQ's `EnvExperiment` and from our `Base`. `Base` itself is `Base(Expt, Devices, Cooling, Image, Cameras, Control, Clients)`: seven mixins, so `self.mot(...)` (from `Cooling`) and `self.abs_image()` (from `Image`) are both available in your experiment.

**decorator** — A line starting with `@` just above a function that changes how it runs. *Ours:* `@kernel` above `scan_kernel` means "compile this and run it on the ARTIQ hardware", not on the PC. `@rpc` means the opposite.

**exception, traceback** — An exception is an error raised while the program runs; if nothing catches it, the program stops and prints a traceback: the chain of calls that led there, newest last, with the error message on the final line. *Ours:* `RuntimeError: [LiveOD] Could not connect to LiveOD server` is the last line of a traceback you will see when liveOD is not running. The Error Message Index is organised by these last lines.

**try / except** — Code that runs something and catches the exception if it fails, so the program can go on. It can hide problems: a caught error that is only printed leaves the system running but wrong. Several Demons are exactly this.

**thread** — One program doing two things at once: a second line of execution inside one process. A thread can die while the rest of the program carries on. *Ours:* liveOD runs one thread per camera; the SLM server's pattern-writing thread can stop while its command listener keeps answering (a Demon).

**log** — A running record of what a program did, one line per event, with a time and a level (INFO, WARNING, ERROR). Not the same as the terminal: logs are often written to a file too. *Ours:* liveOD writes `~/.waxx/logs/live_od.log` on its PC; the monitor server writes an ops journal under `%data%\_logs`.

**string, f-string** — Text, in quotes. An f-string `f"Run ID: {rid}"` fills in values. Error messages on this wiki are shown as their template and as one filled-in example.

**boolean flag** — A true/false argument that switches a behaviour on or off. *Ours:* `save_data=True`, `setup_camera=False`, `suppress_live_od=True`.

**None** — Python's "nothing here" value. *Ours:* `override_apd_stage=None` means "decide from the camera".

**index, 0-based** — The position of an item in a list, counted from 0. *Ours:* `xvar.values[0]` is the first scan value; the Urukul DDS channels are numbered 0 to 3, top to bottom.

**docstring** — The text in triple quotes at the top of a file, class or function that says what it is for. *Ours:* the docstring of `tools/mot_observe.py` is what the Device Control GUI shows before it runs it.

**stdout / terminal output** — What a program prints. The `ar` window shows the experiment's prints; liveOD's window shows liveOD's.

## 2. Working with the code

**repository (repo), clone, branch, commit, pull, push** — A repository is a folder whose whole history git records. Cloning copies it to your PC. A commit is one saved change with a message; a branch is a named line of commits; pulling fetches others' commits, pushing sends yours. *Ours:* `k-exp`, `wax`, `code`, `k-amo`, `k-jam`, `beacon` are repos cloned side by side in `%code%`; the wiki is its own repo (`k-exp.wiki`).

**default branch (`main`)** — The branch everyone's work is merged into. The wiki describes the code as it is on `main` of `k-exp` and `wax`.

**editable install, uv workspace, venv** — Normally installing a Python package copies it somewhere hidden. An editable install points Python at your cloned folder instead, so editing a file changes what runs. The venv (`%code%\.venv`) is the private Python with every package installed; `uv` is the tool that builds it from `pyproject.toml` and `uv.lock` in the `code` repo, and `uv sync` makes it match. *Ours:* `import kexp` works from any folder because `kexp` is an editable install in the workspace venv.

**environment variable** — A named value the operating system gives to every program, such as `%data%` or `%code%`. Programs read them with `os.getenv("data")`. Set on Windows in "Edit the system environment variables"; every terminal must be reopened afterwards. *Ours:* `code`, `kpy`, `db`, `dbtest`, `bat`, `data`, `WAXA_DATA_UNC`.

**config file** — A file whose only job is to hold settings. *Ours:* `kexp/config/*.py` (parameters, channel assignments, IPs) and the device-state JSON the Monitor reads.

**terminal, command line, `kpy` terminal** — A window where you type commands. The `kpy` profile of Windows Terminal opens with the venv active, in `kexp/experiments`; that is where `ar mot_tof.py` is typed.

**`.bat` script, shortcut (`.lnk`)** — A `.bat` file is a Windows command script; the ones in `kexp/_bat/` start our programs. A `.lnk` is a Start-menu shortcut to one. *Ours:* `live_od.bat`, the "LiveOD Server" shortcut.

**`ar`, `art`** — `ar` runs an experiment file with ARTIQ (`artiq_run`) using our device database; `art` does the same and prints a startup timeline. Both live in `kexp/_bat/shortcuts`.

**F12 (go to definition)** — In VS Code, with the cursor on a name, jumps to where it is defined. The fastest way to see which parameters a cooling stage reads.

**`pytest`, test** — A test is code that checks other code and fails loudly if it is wrong. `pytest` runs them. *Ours:* `k-exp/tests/`, `wax/waxx-src/tests/`, `wax/waxa-src/tests/`; each usually exists because something once broke.

**PEP 562 lazy import** — `from kexp import Base` loads `Base` only when first used, so GUIs that import `kexp.config` stay fast. Side effect: `from kexp import *` does not pick up `Base`.

## 3. Networks and servers

**IP address** — A machine's number on the network, four numbers separated by dots. The lab LAN is `192.168.1.x`; kong is `192.168.1.76`.

**port** — A number that picks out one program on a machine, like a flat number in a building. *Ours:* the ethernet relay listens on port `2101`; discovery beacons go to UDP port `50099`.

**host** — The machine a program runs on. "Which host?" means "which PC?".

**server, client, "the server is up"** — A server is a program that waits for requests; a client is one that sends them. "The server is up" means the server process is running and answering. *Ours:* the LiveOD Server (in the liveOD window) and the experiment's `LiveODClient`; the monitor server and the Device Control GUI.

**beacon, discovery** — Our servers shout their name and port onto the LAN every half second (a UDP broadcast). Clients listen instead of being told an IP. *Ours:* liveOD is found by the beacon id `live_od`; the monitor server by `monitor:<hardware id>`.

**TCP, UDP, ZMQ** — Ways of sending bytes over the network. TCP is a reliable conversation; UDP is a shout with no reply guaranteed (beacons); ZMQ is a library on top that liveOD uses for request/reply.

**timeout** — How long a program waits for an answer before giving up and reporting an error. Many of our error messages name their timeout.

**firewall** — A filter on each PC that blocks incoming connections unless a rule allows them. Windows creates a hidden block rule for python.exe if you dismiss its pop-up; that hidden rule is behind many "cannot connect" problems.

**Remote Desktop vs sitting at the PC** — Windows Remote Desktop gives your login its own virtual screen; programs you start there cannot see the PC's real monitors. That breaks the SLM, which is a monitor. VNC-style tools show the real screen instead.

**network drive, UNC path** — A folder on another machine shown as a drive letter (`B:`). The UNC path is its real address, `\\bananastand.physics.ucsb.edu\anewstart`. If `B:` drops, `waxa` re-maps it from `%WAXA_DATA_UNC%`.

**COM port** — A serial connection (`COM6`, `COM20`) to an instrument over USB or RS-232; one program at a time can hold it.

## 4. ARTIQ and real-time control

**ARTIQ** — The control system (hardware crates and software) that runs our sequences with nanosecond timing. The hardware is a Kasli core device with cards for TTL, DDS, DAC, sampler and shuttler.

**core device** — The processor in the crate that runs compiled experiment code. `self.core` in an experiment.

**kernel vs host code** — A kernel (`@kernel`) is compiled and runs on the core device with exact timing. Host code runs as ordinary Python on the PC. A kernel can call host code (an **RPC**, remote procedure call); the value it gets back must have a declared type. Comparison: the kernel is the conductor on stage; RPCs are notes passed to someone backstage.

**compile** — Before `run()` starts, ARTIQ translates every kernel into machine code. This is where type errors appear ("cannot unify"), before anything touches hardware. A run that fails to compile never takes the core and never gets a run ID.

**RTIO, the timeline, timeline cursor** — Real-time input/output. Kernel code does not "do" things; it schedules events at times on a timeline. `delay(t)` moves the cursor forward; an event is placed at the cursor.

**slack** — How far ahead of real time the cursor is. Positive slack means events are scheduled early enough. `core.break_realtime()` jumps the cursor ahead to recover slack; `core.wait_until_mu(now_mu())` waits for real time to catch up.

**underflow (`RTIOUnderflow`)** — An event was scheduled for a time that had already passed: the kernel fell behind. The most common ARTIQ error in our runs. `t_rtio` and `t_recover` are our slack parameters.

**collision, sequence error, `RTIOOverflow`** — Two events on one channel at the same time (collision); events on one channel out of order (sequence error); an input FIFO filled up (overflow, a TTL input toggling far too fast).

**`now_mu`, machine units (mu)** — Time on the core device counted in integer steps (mu); `now_mu()` is the cursor's time.

**dataset** — ARTIQ's own key/value store for results. We barely use it; our data goes through liveOD into HDF5.

**master, dashboard (ARTIQ's)** — ARTIQ's own scheduler and GUI (`artiq_master`, `artiq_dashboard`). Our workflow does not use them; we run experiments with `ar` directly. The `.bat` files under `_bat/dashboard/` are the legacy way in.

**device database (`device_db.py`)** — The file listing every channel in the crate with its key and driver class. Ours is `kexp/util/db/device_db.py`, pointed at by `%db%`. Its `core_addr` last octet is the **hardware id** that scopes the monitor server.

**TTL** — A digital line: about 0 V (off) or about 4 V (on). Used for triggers and switches. `TTL_OUT` sends; `TTL_IN` reads edges.

**DDS (direct digital synthesizer), Urukul, AD9910** — A radio-frequency tone generator with settable frequency, amplitude and phase. Our Urukul cards each carry four AD9910 DDS channels; most drive AOMs. `frequency` in Hz, `amplitude` 0 to 1.

**DAC (digital-to-analog converter), Zotino** — Outputs a steady voltage you set. Used for coil setpoints, VVAs, PID setpoints. `v` in volts, clamped by `max_v`.

**sampler** — An analog input card that reads voltages (photodiodes, APD).

**shuttler** — A card that plays arbitrary voltage waveforms.

**AOM, VVA, PID** — Not ARTIQ words but in every sentence about it: an AOM is an acousto-optic modulator, a crystal that deflects and frequency-shifts a beam when driven with RF; a VVA is a voltage-variable attenuator that sets RF power from a DAC voltage; a PID is a feedback controller holding a photodiode reading at a setpoint.

**`kernel_invariants`** — A declaration that an attribute never changes inside kernels, so the compiler need not copy it back. Assigning to one in a kernel is a compile error. Planned, not yet declared on our classes (`KERNEL_INVARIANTS_PLAN.md`).

**writeback** — When a kernel returns, ARTIQ copies its attribute values back to the host objects. A kernel that dies with an exception writes nothing back, which is why the host does not know what an aborted run left the hardware at.

**`kernel_from_string`** — Builds a kernel from a string of code at run time. Our Scanner uses it to make one tiny kernel per parameter so scanned values can be written into the kernel each shot.
