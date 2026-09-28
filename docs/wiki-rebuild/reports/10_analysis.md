# Agent 10 report: Analysis (waxa atomdata / vault / ROI / OD / fitting / plotting / units / cross section / analysis subpackages / climate / browser; kexp/analysis map)

Scope read (all at wax HEAD acc4621, k-exp HEAD c8faf77): `waxa/atomdata.py` (346), `waxa/atomdata_base.py` (3082), `waxa/atomdata_vault.py` (2927), `waxa/roi.py` (2196), `waxa/units.py`, `waxa/plotting/*`, `waxa/fitting/*`, `waxa/image_processing/*`, `waxa/calibrations/cross_section.py`, `waxa/analysis/{rabi,lightshift,readout}`, `waxa/helper/*`, `waxa/climate/*`, `waxa/browser/*` (skimmed the 3956-line window for actions/labels), `waxa/base/dealer.py`, `waxa/data/{server_talk,data_saver,load_atomdata,run_info}.py` (the load-side parts), `kexp/analysis/*` (mapped), `kexp/config/live_od.py`, `kexp/config/ip.py`, all 15 waxa tests plus `k-exp/tests/test_{apd_state_mapping,rabi_posterior_cli}.py`, and the six wiki pages in the brief (plus the analysis claims on Scan-loop, Repositories, LiveOD, DataVault pages where they touch this area).

History caveat: both clones are shallow (wax: 53 commits from 2026-09-24; k-exp: 66). Dates older than that come from dated code comments and are cited as such.

## 1. operator_summary

- After a run finishes, its data is one HDF5 file on the data drive (`%data%\YYYY-MM-DD\0083120_<date>_<time>_<ExperimentClass>.hdf5`). You look at it in a Jupyter notebook with `from waxa import atomdata; ad = atomdata(83120)` (a positive number is a run ID; `0` is the newest finished run, `-1` the one before). `waxa/atomdata_base.py:586-597`, `waxa/data/server_talk.py:60-126`. **confirmed**
- Loading does the standard analysis for you: it sorts the camera frames into atoms / light / dark images, asks you for a region of interest (ROI) the first time, computes the optical density (OD) inside that box, fits a Gaussian to the cloud profile along x and y, and computes an atom number per shot. Everything comes back as arrays with one axis per scanned variable (`ad.od`, `ad.atom_number`, `ad.fit_sd_x`, `ad.data.<key>`, `ad.params.<name>`). `waxa/atomdata.py:173-295`. **confirmed**
- Repeats are averaged for you: `ad.avg`, `ad.std` and `ad.sem` are copies of the dataset collapsed over repeats (`ad.avg.atom_number` with error bars `ad.sem.atom_number`). The old `avg_repeats=True` / `ad.avg_repeats()` does nothing any more. `waxa/atomdata_base.py:2043-2057, 2336-2352`. **confirmed**
- Several runs can be glued into one dataset with `AtomdataVault([83100, 83101, ...])`; the Data Browser (`kexp\_bat\data_browser.bat`) is a window that lists runs, their scanned variables, tags and lite copies. `waxa/atomdata_vault.py:140`, `kexp/_bat/data_browser.bat`. **confirmed**
- Two `!!` banners matter when you load: `!! RUN <id> IS INCOMPLETE ...` (camera frames were missing; per-shot images are not to be trusted) and `!! run <id>: camera settings differ from ad.camera_params ...` (the camera applied a different gain/exposure than the run asked for; `ad.camera_params` is the request, `ad.camera_overrides` is what was applied). `waxa/atomdata_base.py:471-513, 2768-2780`. **confirmed**

## 2. mental_model

Everyday comparison: an `atomdata` is like a photo album that a lab assistant assembles for you from a shoebox of loose prints. The HDF5 file is the shoebox (all frames in the order the camera sent them, plus the parameter sheet). `atomdata(83120)` is the assistant: it finds the box (server_talk), sorts the prints into pages by the scanned variable (the Dealer), asks you once which part of each print matters (the ROI), then writes captions (OD, fits, atom number) under every photo. `ad.avg` is the same album with all duplicate photos of the same setting stacked and averaged. An `AtomdataVault` is a binder holding several albums with their pages merged in order.

```mermaid
flowchart LR
  A["run file<br/>%data%/date/0083120_...hdf5"] -->|server_talk.get_data_file| B[_load_data]
  B --> C["params / camera_params / run_info<br/>(unpack_group)"]
  B --> D["images, image_timestamps"]
  B --> E["data/* (DataVault) + scope_data"]
  B --> F["banners: data_complete / camera_overrides"]
  D -->|Dealer.deal_data_ndarray| G["img_atoms / img_light / img_dark<br/>(*xvardims, H, W)"]
  G -->|ROI.crop then compute_OD| H["ad.od (*xvardims, py, px)"]
  H --> I["sum_od_x / sum_od_y"]
  I -->|GaussianFit per shot| J["cloudfit_x/y, fit_sd_x, fit_center_x, fit_area_x"]
  H -->|cross_section_for_run(data.i_outer_imaging)| K["atom_number, atom_cross_section_source"]
  J --> L["ad.avg / ad.std / ad.sem<br/>(repeat siblings)"]
  K --> L
```

## 3. how_to

### 3.1 Worked example: from run ID to a fitted, unit-labelled plot (the thing a newcomer needs)

Prerequisites on the analysis PC (see section 10 and PC-Setup): the `%data%` environment variable points at the data drive (`B:\_K\PotassiumData\` on lab PCs, `kexp/config/ip.py:8`, PC-Setup table), and the notebook's kernel is the workspace venv (`%code%\.venv`, PC-Setup "VS Code" note). Set `%data%` **before** starting Jupyter: it is read once, when `waxa` is imported (`waxa/data/server_talk.py:17` is a default argument evaluated at import). **confirmed**

Where notebooks live: lab convention is `k-jam/analysis/...` (for example `k-jam\analysis\measurements\imaging_frequency_vs_iouter.ipynb`, cited in `kexp/calibrations/imaging.py:4`; `k-jam/analysis/artisinal/apd_pulse_analysis_interpolate.ipynb`, cited in `waxa/analysis/readout/__init__.py`; experiment files point at their notebook, e.g. `kexp/experiments/calibration/measure_i_transducer_per_i_supply.py:13`). **inferred** from those references (k-jam is not in this container; folder layout needs a human).

Example run: a detuning scan like `kexp/experiments/default_experiments/find_hf_tweezer_imaging_detuning_direct.py` (Andor, absorption, `self.xvar('frequency_detuned_imaging', f_scan_array)` about -457 MHz +/- 5 MHz, line 42).

```python
import numpy as np
import matplotlib.pyplot as plt
from waxa import atomdata
from waxa.fitting import GaussianFit
from waxa.units import detect_unit

ad = atomdata(83120)        # positive = run ID; 0 = newest finished run, -1 = the one before
# First load of a fresh run: the "ROI Selector" window opens (with an auto-suggested box).
# Drag a box (left mouse), press Enter / click Accept.  Then keep it, so the next load does not ask:
ad.save_roi_h5()            # writes roix/roiy into this run's HDF5 file

print(ad.run_id_title, ad.xvarnames, ad.xvardims)    # e.g. 'run id 83120' ['frequency_detuned_imaging'] [4]
print(np.unique(ad.atom_cross_section_source))        # 'high-field' / 'low-field-uncalibrated' / 'fallback-no-record'

x  = ad.avg.xvars[0]        # unique xvar values, SI (Hz here); works with or without repeats
N  = ad.avg.atom_number     # mean over repeats
dN = ad.sem.atom_number     # std over repeats / sqrt(N_repeats); zeros when there are no repeats

fit = GaussianFit(x, N)     # peak only: amplitude and sigma are bounded >= 0
unit, mult, name = detect_unit(ad, xvar_idx=0)        # ('MHz', 1e-06, 'frequency_detuned_imaging')

fig, ax = plt.subplots()
ax.errorbar(x * mult, N, yerr=dN, fmt='o', label='data')
xs, ys = fit.get_fitplot_arrays()
ax.plot(xs * mult, ys, '--', label=f'center {fit.x_center*mult:.3f} {unit}')
ax.set_xlabel(f"{name} ({unit})"); ax.set_ylabel("atom number"); ax.set_title(ad.run_id_title)
ax.legend()
```

Notes on each line (all **confirmed** unless marked):
- `atomdata(83120)` prints, in order: the bare run id, `[atomdata timing] load ...`, the ROI messages (`No ROI saved in run 83120 (cached).`, `Specify the new ROI.`), the analysis timing lines (`waxa/atomdata_base.py:2745, 2918-2931`; `waxa/atomdata.py:210-222, 284-295`; `waxa/roi.py:462-477, 564`). Timing printouts are hard-wired on (`atomdata_base.py:631`).
- ROI: with no saved ROI, the dialog opens (`roi.py:474-477`), pre-drawn with an auto-detected box (`suggest_auto_roi=not lite`). Nothing is saved unless you call `ad.save_roi_h5()` (writes `roix`/`roiy` root attrs, `roi.py:503-511`) or `ad.save_roi_excel("mykey")` (a row in `%data%\roi.xlsx`, `roi.py:513-524, 676-702`). liveOD never writes an ROI into run files (grep of `waxx/util/live_od` for `roix`/`save_roi_h5`: none).
- `ad.avg` / `ad.sem` exist on every load. With no repeat axis, `ad.avg` is a pass-through to `ad` and `ad.sem` returns zeros (`atomdata_base.py:2043-2052`, proxies at 136-172).
- `GaussianFit` fits `y_offset + amplitude*exp(-(x-x_center)^2/(2 sigma^2))` with `amplitude, sigma >= 0` (`waxa/fitting/gaussian.py:52-53, 106-112`), so it fits a peak; for a dip fit `-N` or use `LorentzianFit`/your own. It fits only a window of about +/-4 guessed widths around the most prominent peak (`gaussian.py:169-177`) and expects `x` sorted (the window is by index).
- `detect_unit` on a loaded atomdata is effectively name-plus-magnitude guessing (see 5.9): `frequency_...` with max |value| >= 1e6 gives MHz (`waxa/units.py:183-192`).
- One-liner alternative: `from waxa.plotting import errorplot; errorplot(ad, mean=ad.avg.atom_number, yerr=ad.sem.atom_number, y=ad.atom_number)` (unit-aware x label; y label is the attribute name only when `y` is an attribute of `ad` itself, `waxa/plotting/plotting_1d.py:24-51`).
- Quick visual check of the frames: `from waxa.plotting import plot_mixOD; plot_mixOD(ad)` (1-D scans; one OD tile per shot with the xvar value as tick label, `plotting_1d.py:54-211`); 2-D scans: `plot_image_grid(ad)` (`plotting_2d.py:15`).

### 3.2 Load the newest run / a run from last week / by file path
1. Newest finished run: `ad = atomdata(0)`; the one before: `atomdata(-1)` (`server_talk.py:84-116`). "Finished" is defined in 5.2.
2. By run ID: `atomdata(83120)`. The file is found by walking date folders newest-first (`server_talk.py:348-393`); no completion check is applied for a positive run ID (`server_talk.py:117-118`).
3. By path: `atomdata(path=r"B:\_K\PotassiumData\2026-09-27\0083120_2026-09-27_14-03-22_hf_bec.hdf5")` (must end in `.hdf5`, `server_talk.py:119-121`).
4. Lite (pre-cropped, small) copy: `atomdata(83120, lite=True)`; if no lite copy exists it is made for you (full load, ROI, write `%data%\_lite\<date>\0083120_lite_...hdf5`, reload) (`atomdata_base.py:2634-2716`; path `waxa/data/data_saver.py:334-346`). A lite copy ignores `roi_id` (`atomdata_base.py:625-626`).
5. Skip images entirely (APD/scope-only analysis, fastest): `atomdata(83120, ignore_images=True)` (`atomdata_base.py:2761-2762`).
6. Thin scope traces: `atomdata(83120, decimate_scope_data=10)` (block-average by default; `smooth_decimate=False` for stride) (`atomdata_base.py:303-332, 615-623`).
7. Point at another data folder in a notebook: `from waxa.data.server_talk import server_talk; st = server_talk(data_dir=r"D:\copy_of_data"); ad = atomdata(83120, server_talk=st)` (`atomdata.py:79`). Setting `os.environ['data']` after import has no effect (5.1). `AtomdataVault` cannot take a server_talk (5.15).

### 3.3 Choose / change the ROI
- Accept the saved one (default): `atomdata(rid)`.
- Force a new one: `atomdata(rid, skip_saved_roi=True)` or later `ad.recrop()` (opens the dialog; `use_saved=False` default) (`atomdata_base.py:743-776`).
- Reuse the ROI saved in another run: `atomdata(rid, roi_id=83000)` (int = run ID whose file holds `roix/roiy`; if that run has none, the dialog opens) (`roi.py:480-487`).
- Named ROI from the spreadsheet `%data%\roi.xlsx`: `atomdata(rid, roi_id="andor_all")` (string = row key; if the key is missing, the dialog opens and a new row is written) (`roi.py:489-495`). liveOD's own live-OD analyzer starts from rows `andor_all` / `basler_all` (`kexp/config/live_od.py:26-32`, used at `waxx/util/live_od/gui/main_window.py:1294-1298`).
- Headless (no dialog, for scripts): `atomdata(rid, roi_id='auto')` uses the auto-detector's box if it is valid, else the whole frame (`roi.py:444-459`). `'auto'` ignores any ROI saved in the run.
- Dialog controls (window title "ROI Selector", `roi.py:896`; instructions box, `roi.py:1157-1204`): left-drag = box; middle-drag = zoom; right-click = zoom out / clear; wheel = zoom out; Left/Right arrows = previous/next frame; Up/Down = brighter/dimmer; `A` = apply auto box; `[` / `]` = tighter / more generous auto box; Enter or "Accept" = accept; Escape or "Cancel" = cancel (then the whole frame is used, 5.5). Buttons: "Auto ROI" (`roi.py:1011`), "Zoom Out", "Clear ROI", "Instructions", "Accept", "Cancel", a preset dropdown (roi.xlsx rows plus "auto (suggested)" and "saved (this run)"), and an "Auto ROI box: tight ... generous" slider (`roi.py:1022-1110`, `60-61`).

### 3.4 Repeats, slicing, reordering
- Mean/std/sem over repeats: `ad.avg.<attr>`, `ad.std.<attr>`, `ad.sem.<attr>`, including `ad.avg.data.<key>` and quantities you add later (`ad.data.sz = ...; ad.avg.data.sz` works, `atomdata_base.py:55-103`).
- For an array you computed yourself: `y_avg, y_std, y_sem = ad.avg_array(y)`; `ad.std_array(y)`, `ad.sem_array(y)` (`atomdata_base.py:2131-2195`).
- Take a sub-scan: `ad2 = ad.slice_atomdata(which_xvar_idx=0, xvar_value=20e-3)` (see 5.8 for the rules and traps).
- Put shots back into acquisition order: `ad.reshuffle()`; back to sorted: `ad.unshuffle()` (`atomdata_base.py:2557-2580`).
- Move repeats to another axis (2-D scans): `ad.reassign_repeats(1)` (`atomdata_base.py:2251-2334`).
- Swap the two axes of a 2-D scan: `ad.transpose_data()` (method; the constructor argument `transpose_idx` is broken, 15).

### 3.5 Several runs as one dataset (AtomdataVault)
1. `from waxa import AtomdataVault; v = AtomdataVault([83100, 83101, 83102])` (1-D runs of the same xvar are concatenated and sorted; multi-axis runs are stacked along one differing scalar param `promote_xvar`) (`atomdata_vault.py:1-51, 234-559`).
2. Check what differed: `v.param_report()` (per-run disagreements), `v.camera_param_disagreements`, `v.camera_overrides_by_run` (`atomdata_vault.py:1173-1275, 2751-2776`).
3. Per-shot provenance: `v.shot_run_id`, `v.shots_from_run(83101)`, `v.drop_runs([83101])`, `v.atomdata(83101)` (`atomdata_vault.py:2659-2736`).
4. Relabel an axis: `v.remap_xvar(0, lambda V: P0*V/0.444, 'p_tweezer')` or from a recorded container `v.data_container_to_xvar('f_det', 'f_meas')` (`atomdata_vault.py:1945-2073`; tests `test_vault_remap_xvar.py`).
5. Builder ranges: `AtomdataVault.from_run_range(83100, 83140, experiment_name='hf_bec')` / `from_builder(...)` (`atomdata_vault.py:2789-2863`) (traps in 5.15).
6. More than 8 run IDs switch to lite automatically unless `auto_lite_threshold=None` (`atomdata_vault.py:337-352`).

### 3.6 Physics-analysis helpers (waxa.analysis)
- Rabi pi time: `from waxa.analysis.rabi import rabi; fit = rabi(83092); fit.t_pi, fit.t_pi_err; fit.plot()`; command line from the kpy terminal: `python -m waxa.analysis.rabi 83092 [83091 ...] --compare t_raman_pi_pulse --plot rabi.png` (`waxa/analysis/rabi/__init__.py`, `__main__.py:1-83`). Default `--roi auto` (headless; ignores a saved ROI) and `--signal atom_number`.
- Light shift from a Ramsey fringe: `from waxa.analysis.lightshift import ramsey_light_shift; ls = ramsey_light_shift(atomdata(0)); ls.plot()` (`waxa/analysis/lightshift/__init__.py`).
- Readout calibration: `from waxa.analysis.readout import calibrate_readout` (arrays in; K-machine wrapper below) (`waxa/analysis/readout/__init__.py`).
- Temperature from a TOF scan (`t_tof` xvar): `from waxa.plotting import TOF; T = TOF(ad, 'x').T` (fits sigma^2 = kB T/m t^2 + sigma0^2; `waxa/plotting/standard_experiments.py:57-112`, `waxa/fitting/gaussian.py:517-562`).
- Lab climate per shot: `from waxa.climate import climate_for_run; clim = climate_for_run(ad)` (needs the Broida VPN) (`waxa/climate/attach.py:140-165`).

### 3.7 kexp/analysis entry points (map)
| Module | What it is for | Entry point | Inputs | Outputs / writes |
|---|---|---|---|---|
| `kexp/analysis/apd_state_mapping.py` (387) | APD volts to spin state: the feedback readout calibration from `apd_voltage_vs_state_2.py` runs; wraps `waxa.analysis.readout.calibrate_readout` | `python -m kexp.analysis.apd_state_mapping 83148 83149 83150 --out <dir>`; `apd_state_mapping([..]).report()` | run IDs (read-only load), scope trace `scope_data['PD']`, `ad.data.apd` | proposed params block (`v_apd_all_up/down`, `feedback_measurement_midpoint_fraction`, `n_photons_per_shot`, `std_n_photons_per_shot`); writes only under `C:\lab\skynet_log\outputs` (`apd_state_mapping.py:69-70, 319-328`) |
| `kexp/analysis/rabi_posterior.py` (2493) | Bayesian posterior over Rabi frequency from a feedback pulse train (inverse of `Feedback.generate_posterior`); `RabiPosterior`, `RabiJointPosterior`, `RabiCalibration`, `simulate_pulse_train_apd` | Python classes | APD pulse-train runs | posterior objects/plots; long docstring records the run-76245 inverted-readout failure (flat SLM mask, fixed 2026-08-25) (`rabi_posterior.py:1-80`) |
| `kexp/analysis/rabi_posterior_cli.py` (1621) | every Rabi estimator on one run with pre-registered gates; three verdicts (`t_pi`, `nuisances`, `fixed_cal`) | `python -m kexp.analysis.rabi_posterior_cli 83150 --out <dir>` | positive run IDs only (`0`/`-1` refused, lines 1590-1592); loads `atomdata(rid, roi_id='auto', lite=False, ignore_images=True)` (163-166) | `results.json` + PNGs; only inside `C:\lab\skynet_log\outputs` (1410-1424) |
| `kexp/analysis/feedback.py` (6341) | replay/optimizer engine for the monitored-Rabi feedback: `FeedbackReplayCore(Feedback)`, `FeedbackReplay`, `FeedbackReplayOptimizer`, `...Sweep`, `...ConvergenceOptimizer`, `...PosteriorPeakOptimizer` | Python classes (notebooks) | atomdata of feedback runs | replay results/plots; subclasses the kernel-side `kexp.base.feedback.Feedback` (line 16) |

Importing anything under `kexp.analysis` runs `kexp/analysis/__init__.py`, which imports `feedback.py`, which imports `kexp.base.feedback`, which imports `artiq.experiment` (`kexp/base/feedback.py:1`). So these need ARTIQ installed. **confirmed** (import chain); consistent with PC-Setup's "analysis-only computers need the machine-control list too".

### 3.8 Data Browser
1. Launch: double-click `kexp\_bat\data_browser.bat` (runs `call %kpy%`, `cd /d %code%\k-exp`, `python kexp\util\data_browser\data_browser.py` which calls `waxa.browser.launch(DATA_DIR)`; the console waits on `pause`) (`kexp/_bat/data_browser.bat`, `kexp/util/data_browser/data_browser.py`). Window title "Data Browser" (`browser_window.py:1044`).
2. The table columns: `run_id, datetime, experiment, xvardims, N_r, xvarnames, data containers, scope, lite, tags` (`browser_window.py:1182-1196`); filters "xvarname search", "by run ID" + "Go", "experiment search", "tag search", From/To dates, "Refresh", auto-refresh; a detail pane with an xvar table (`xvarname, min, max, unit, preview, N`, line 676).
3. Right-click a run: "Create Lite Dataset", "Copy Run ID", "Copy Lite Arg" (copies `83120, lite=True`), "Open H5 File", "Search Params…", "Add Tag" submenu, "Edit Comment…", "Select ROI…", and a view-files submenu (the saved experiment source texts) (`browser_window.py:2716-2793`).
4. Lite creation from the browser picks one ROI on the GUI thread (on the oldest selected run, pre-drawn with its saved ROI) and applies it to all selected runs; the "Cancel lite" button stops it (`browser_window.py:3384-3450`). **"Select ROI…" is broken** (15).
5. Tags and comments are written into the run's raw HDF5 file as root attrs `browser_tags` (JSON) / `browser_comment` (`waxa/browser/scanner.py:1158-1185`). A metadata cache lives at `%data%\.waxa_browser_cache.json` (`waxa/browser/cache.py:19-24`).

## 4. reference_facts

### 4.1 atomdata constructor (`waxa/atomdata.py:67-93`; docstring `atomdata_base.py:578-611`)
| Arg | Default | Meaning | Conf. |
|---|---|---|---|
| `idx` | `0` | >0 run ID; 0 newest finished run; <0 steps back through finished runs | confirmed `server_talk.py:84-118` |
| `roi_id` | `None` | None: saved ROI in file else dialog; int: ROI saved in that run's file; str: `roi.xlsx` key; `'auto'`: headless auto box | confirmed `roi.py:419-501` |
| `path` | `""` | full path to an `.hdf5` | confirmed |
| `lite` | `False` | load `%data%\_lite\...` copy (auto-created if missing); forces `roi_id=None` | confirmed `atomdata_base.py:625-626, 2688-2716` |
| `skip_saved_roi` | `False` | ignore `roix/roiy` saved in the file | confirmed |
| `transpose_idx` | `[]` | **broken when non-empty** (TypeError) | confirmed 15 |
| `avg_repeats` | `False` | deprecated no-op; `True` gives a FutureWarning | confirmed `atomdata_base.py:2336-2352` |
| `ignore_images` | `False` | skip images, ROI, OD, fits | confirmed |
| `decimate_scope_data` | `None` | int N: keep every Nth scope sample (0/None: all); negative raises | confirmed `atomdata_base.py:615-623` |
| `smooth_decimate` | `True` | block-average when decimating | confirmed |
| `server_talk` | `st()` built at import | which data dir to use | confirmed `atomdata.py:79` |

### 4.2 Public attributes after a normal absorption load
| Attribute | Shape / type | Notes | Conf. |
|---|---|---|---|
| `params` (= `p`) | `waxa.config.expt_params.ExptParams` filled from `params/` | xvar keys hold the scanned arrays (sorted order); `N_repeats` normalised to int | confirmed `atomdata_base.py:2729-2743` |
| `camera_params` | dummy `CameraParams` filled from `camera_params/` | the **request** | confirmed |
| `camera_overrides` | dict (`{}` if none) | liveOD's record of applied != requested | confirmed `atomdata_base.py:1384-1396` |
| `run_info` | `RunInfo` from `run_info/`; plus `data_complete`, `incomplete_reason` | `run_info.run_datetime` is the **load time** on liveOD-era files (5.12) | confirmed |
| `xvarnames`, `xvars`, `xvardims`, `Nvars` | lists/arrays | `xvars[i]` includes repeated values | confirmed `atomdata_base.py:2521-2543` |
| `images`, `image_timestamps` | `(N_img, H, W)`, `(N_img,)` raw | as on disk | confirmed |
| `img_atoms/img_light/img_dark` | `(*xvardims, H, W)` (or `(*xvardims, N_pwa, H, W)` when `N_pwa_per_shot>1`) | views, light/dark shared | confirmed `atomdata.py:334-360`, `dealer.py:177-198` |
| `img_timestamp_atoms` etc. | `(*xvardims,)` | camera-PC `time.time()` per frame | confirmed; `climate/attach.py:40-44` |
| `od` | `(*xvardims, py, px)` cropped | for non-absorption imaging it is `(pwa-dark)/(pwoa-dark)`, not an OD | confirmed `atomdata_base.py:1163-1189`, `compute_ODs.py:75-83` |
| `od_raw` | full-frame OD, computed on first read and cached | property | confirmed `atomdata_base.py:2944-2973` |
| `sum_od_x`, `sum_od_y` | `(*xvardims, px)`, `(*xvardims, py)` | sums over y rows / x columns | confirmed |
| `axis_x`, `axis_y` | metres at the atoms, from the ROI's left/top edge | `pixel_size_m/magnification * index` | confirmed `atomdata_base.py:1200-1207` |
| `cloudfit_x/y` | object arrays of `GaussianFit` | | confirmed |
| `fit_sd_x/y`, `fit_center_x/y`, `fit_amp_x/y`, `fit_offset_x/y`, `fit_area_x/y` | `(*xvardims)` | metres (centers relative to ROI origin) | confirmed `atomdata_base.py:2488-2506` |
| `atom_number` | `(*xvardims)` | **absorption only**; missing attribute for other imaging types | confirmed `atomdata.py:277-278` |
| `atom_number_density`, `atom_number_fit_area_x/y` | | | confirmed |
| `atom_cross_section`, `atom_cross_section_source` | `(*xvardims)` m^2 and str tag | per shot, from `data.i_outer_imaging` | confirmed `atomdata_base.py:1275-1301` |
| `integrated_od` | `(*xvardims)` | sum of `od` | confirmed |
| `atom_number_apd` | object with `n_up, n_down, n_total, frac_up, frac_down` | only if `data.post_shot_absorption` exists and is non-zero; `frac_down` is wrong (15) | confirmed `atomdata.py:297-318` |
| `data` | DataVault stand-in; `data.keys` list | trailing size-1 axes dropped at load | confirmed `atomdata_base.py:2810-2831` |
| `scope_data` | `{scope_key: {ch: ScopeTraceArray(t, v)}}` | shared time axis as read-only broadcast view | confirmed `atomdata_base.py:367-431` |
| `timestamp_shot_end` | `(*xvardims)` server-side time per shot | unshuffled at save | confirmed |
| `sort_idx`, `sort_N` | padded int arrays | acquisition permutation record | confirmed `atomdata_base.py:2888-2894` |
| `experiment_code` | `.experiment, .params, .cooling, .imaging, .control, .base_files` | source texts saved with the run | confirmed `atomdata_base.py:2839-2886` |
| `avg`, `std`, `sem` | sibling atomdata or proxies | population std (ddof=0); sem = std/sqrt(n) | confirmed |
| `roi` | `waxa.roi.ROI` (`roix=[x0,x1]`, `roiy=[y0,y1]`) | None with `ignore_images` | confirmed |
| `run_id`, `run_id_title` | sorted unique int array; `'run id 83120'` / `'run id 1234 to 1240, 1250'` | | confirmed `atomdata_base.py:714-741` |

### 4.3 Public methods
`recrop(roi_id=None, use_saved=False)`, `regenerate_lite_copy`, `save_roi_excel(key)`, `save_roi_h5()`, `save_lite_copy(...)`/`create_lite_copy(...)`, `analyze()`, `analyze_ods()`, `compute_raw_ods()`, `compute_atom_number()`, `compute_apd_atom_number()`, `apd_to_sz(v)`, `apd_std_to_sz(v)`, `unshuffle()`, `reshuffle()`, `slice_atomdata(...)`, `reassign_repeats(i)`, `avg_array/std_array/sem_array`, `transpose_data(new_xvar_idx)`, `avg_repeats()` (no-op), `revert_repeats()` (legacy). `waxa/atomdata.py:95-170`; `atomdata_base.py:743-2486`. **confirmed**

### 4.4 Run-file layout read by atomdata (liveOD-era files)
| Where | What | Conf. |
|---|---|---|
| root attrs | `xvarnames`, `has_images`, `run_complete`, `run_finalized`, `data_complete`, `incomplete_reason`, `images_expected`, `images_received`, `camera_overrides` (JSON, only when non-empty), `unshuffle_applied`, `unshuffle_in_progress`, `roix`/`roiy` (only after someone saves an ROI), `expt_file`, `params_file`, `base_class_<module>`, `experiment_filepath`, `browser_tags`, `browser_comment`, `lite_source_roix/roiy` (lite copies from server_talk) | confirmed `data_saver.py:476-548, 773-870`; `server_talk.py:597-605`; `browser/scanner.py:1176-1180` |
| `params/` | final params written at END_RUN (xvar arrays unshuffled); INIT_RUN snapshot until then (xvars scalar) | confirmed `data_saver.py:553-559, 735-747` |
| `camera_params/` | the request | confirmed |
| `run_info/` | `run_id, run_date_str, run_datetime_str, expt_class, imaging_type, save_data, save_on_underflow, filepath (empty), xvarnames, experiment_filepath` — **no `run_datetime`** | confirmed `data_saver.py:486-499, 933-945` |
| `data/` | `images`, `image_timestamps`, DataVault keys, `sort_idx`, `sort_N`, `scope_data/`, `timestamp_shot_end` | confirmed |

### 4.5 Where files are
| Thing | Location | Conf. |
|---|---|---|
| Run file | `%data%\YYYY-MM-DD\<run_id:07d>_<YYYY-MM-DD_HH-MM-SS>_<ExptClass>.hdf5` | confirmed `data_saver.py:334-346` |
| Lite file | `%data%\_lite\YYYY-MM-DD\<run_id:07d>_lite_<datetime>_<ExptClass>.hdf5` | confirmed |
| ROI spreadsheet | `%data%\roi.xlsx`, columns `key, roix0, roix1, roiy0, roiy1` (first column is the key; the writer assumes this order) | confirmed `server_talk.py:25`, `roi.py:603-608, 690-697` |
| Browser cache | `%data%\.waxa_browser_cache.json` | confirmed |
| Run ID counter | `%data%\run_id.py` | confirmed `server_talk.py:24` |
| Drive re-map script (notebook path, Windows) | `"G:\Shared drives\Weld Lab Shared Drive\Infrastructure\map_network_drives.bat"` | confirmed `server_talk.py:11, 146-156` |

### 4.6 Cross-section rule (`waxa/calibrations/cross_section.py`)
| Case | sigma (m^2) | tag | Conf. |
|---|---|---|---|
| `data.i_outer_imaging >= 1.0 A` | `2.80668e-13` (closed sigma- D2 at 520.583 G, from kamo `K39_D2_CLOSED_HIGH_FIELD_M2`) | `'high-field'` | confirmed lines 48, 64, 68, 99-108 |
| `< 1.0 A` (including 0) | `5.878324268151581e-13` (= lambda^2, placeholder) | `'low-field-uncalibrated'` | confirmed |
| no record / NaN / shape mismatch | high-field value | `'fallback-no-record'` | confirmed lines 71, 93-95, 142-154; test `test_shape_mismatch_falls_back` |
| legacy constant (pre-2026-09-16, unused) | `2.8316243e-13` | — | confirmed line 66, 70 |
`i_outer_imaging` is recorded per shot at the first camera trigger as the **commanded** current (`outer_coil.current_now()` = PID set point or supply set point), not a measurement (`kexp/base/image.py:63-79`, `kexp/control/big_coil.py:136-145`; container `kexp/config/data_vault.py:18`). Atom number: `sum(od) * (pixel_size_m/magnification)^2 / sigma` per shot, no saturation correction (`atomdata_base.py:1291-1301`). **confirmed**

### 4.7 Fit classes (`waxa/fitting/*`, exported names from `waxa/fitting/__init__.py:1-8`)
| Class (import) | Model | Result attributes | Guesses / bounds | Failure behaviour | Conf. |
|---|---|---|---|---|---|
| `GaussianFit` (`waxa.fitting`) | `y_offset + amplitude*exp(-(x-x_center)^2/2sigma^2)` | `amplitude, sigma, x_center, y_offset, area (=amp*sqrt(2pi)sigma), popt, y_fitdata` | peak finding on boxcar-smoothed, normalised y; width from 30%-height crossing; fit window +/-4 widths; `amplitude,sigma >= 0`; options `which_peak, px_boxcar_smoothing=3, fractional_peak_height_at_width=0.3, fractional_peak_prominence=0.01, use_peak_bases_for_amplitude, force_zero_offset, print_errors=True, debug_plotting` | NaN params, prints the error (unless `print_errors=False`) | confirmed `gaussian.py:8-230` |
| `MultiGaussianFit(x, y, N_peaks)` | offset + sum of N Gaussians | arrays `amplitude, sigma, x_center` (left to right), scalar `y_offset`, `area`, `popt_single`, `y_fitdata_single` | per-peak guesses, `find_peaks(distance=peak_distance_px)` | **raises** on failure; also runs a (mis-argued) single-Gaussian fit first | confirmed `gaussian.py:232-436` |
| `GaussianTemperatureFit(t, sigma)` (`waxa.fitting`) | `sigma^2 = kB*T/m_K * t^2 + sigma0^2` (internally x1e6 scaled) | `T` (K), `err_T`, `sigma0` (m), `y_fitdata` | `T0=1 mK`, bounds `0 <= T <= 1 K` | **raises** on failure; `popt` stays `[]` so `plot_fit()` fails | confirmed `gaussian.py:517-562` |
| `BECFit` (`waxa.fitting.gaussian`, not exported) | Gaussian + `-c(x-x0)^2 + offset` (an unclipped inverted parabola, not a true Thomas-Fermi profile) | `g_amp, g_sigma, g_center, tf_trap_coeff, tf_center, tf_offset` | trap coeff from 500 Hz | NaN | confirmed `gaussian.py:437-515` |
| `LorentzianFit` | `y_offset + amplitude*gamma/((x-x_center)^2+(gamma/2)^2)` | `amplitude, gamma (FWHM), x_center, y_offset, area` (**area = amplitude; true area is 2*pi*amplitude**) | up to 9 retries with gamma = span/N | NaN; message on total failure is an UnboundLocalError text; `include_idx/exclude_idx` ignored (15) | confirmed `lorentzian.py:6-85` |
| `Sine` | `y_offset + amplitude*sin(k x + phase)` | `amplitude, y_offset, k, phase, pcov` | `amplitude,k >= 0`, `0 <= phase <= 2pi` | intended NaN, but uses `np.NaN` (15) | confirmed `sine.py` |
| `SineEnvelope` | Gaussian x (1 + contrast*cos(k(x-x0)+phase)) + offset ("fringes") | `amplitude, sigma, x_center, y_offset, contrast, k, phase, gfit` | from a GaussianFit of the raw data | intended NaN, uses `np.NaN` | confirmed `fringes.py` |
| `LinearFit` | `slope*x + offset` | `slope, offset` | endpoints | NaN intended; `np.NaN` in the handler | confirmed `linear.py` |
| `QuadraticFit`, `KinematicFit` (`from .parabolic import *`) | `a0+a1 x+a2 x^2`; `x0+v0 t+a t^2/2` | `a0,a1,a2,pcov`; `x0,v0,a,pcov` | trivial | **crash** on failure (`pcov` unbound; Quadratic also `np.NaN`) | confirmed `parabolic.py` |
| `ExponentialDecayFit(x, y, allow_offset=True)` | `y_offset + coefficient*exp(-x/time_constant)` | `coefficient, time_constant, y_offset` | `max(y)`, `ptp(x)/10`, `min(y)` | **raises** (no try) | confirmed `exponentials.py` |
| `polynomial.py` | duplicate of parabolic.py (BOM, `np.NaN`) | — | not imported anywhere | dead code | confirmed `grep` |
Base class `Fit(xdata, ydata, include_idx=[0,-1], exclude_idx=[], savgol_window=5, savgol_degree=3)`: crops by index, drops NaN/inf pairs, `ydata_smoothed` (Savitzky-Golay, falls back to raw), `get_fitplot_arrays(Ninterp)`, `plot_fit()` (`fit.py:14-83`). `include_idx=[a,-1]` means "to the end inclusive"; a positive end is exclusive; negative ends other than -1 are inclusive (`datasmith.py:226-257`). **confirmed**

### 4.8 Unit detection (`waxa/units.py`)
| Function | Used by | Rule | Conf. |
|---|---|---|---|
| `detect_unit(ad, xvar_idx)` -> `(unit, mult, name)` | plot labels (`errorplot`, `plot_mixOD`, ...) | 1 explicit `xvarunit/xvarmult`; 2 `get_param` comment on the params class source; 3 `guess_unit` | confirmed lines 239-291 |
| `get_param(params_obj, name)` | detect_unit | first `self.<name> = ... # <comment>` in the class source, **substring** match against `UNIT_MAP_FROM_COMMENT` keys in order `ns, us, µs, ms, s, MHz, kHz, Hz, Gamma, V, A, amplitude, fraction, rad, unitless` | confirmed 52-68, 93-117 |
| `unit_from_comment` | Adjust panel (`unit_for_param`) | live line only, comment must *start* with the unit token | confirmed 120-150; test `test_only_a_comment_that_names_a_unit_is_believed` |
| `guess_unit(name, values)` | fallback | `t_`/`time`/`_t` -> s/ms/µs/ns by max |v|; `freq`/`frequency`/`_detuning`/`f_` -> GHz/MHz/kHz/Hz; `detune_`/`detun_` -> Γ; `v_`/`volt` -> V; `i_`/`current` -> A; `amp_`/`pfrac_`/`fraction` -> label `"amp"`; `power_` -> W/mW/µW/nW; `phase_` -> π (mult 1/π); `dimension_` -> m/mm/µm/nm; else `(None, 1.0)` | confirmed 153-236 |
| `UNIT_FAMILIES` | Adjust panel dropdown | time, frequency, length, power, angle | confirmed 74-80 |
| `format_si(2e-5,'µs')` -> `"20.e-6"` | Adjust panel copy | | confirmed; tests |
`waxa.plotting.units` is a re-export shim since 2026-09-20 (`waxa/plotting/units.py:1-6`). **confirmed**

### 4.9 Misc defaults
| Fact | Value | Where | Conf. |
|---|---|---|---|
| `slice_atomdata` `xvar_tolerance` | `0.05` (fraction of robust mean spacing) | `atomdata.py:139`, `atomdata_base.py:1303` | confirmed |
| Lazy repeat-stat threshold | arrays >= 32 MiB reduced on first access | `atomdata_base.py:43` | confirmed |
| Parallel Gaussian fits | only above 2000 fits (loky pool) | `compute_gaussian_cloud_params.py:94, 137-151` | confirmed |
| Pre-sorted-save cutoff | runs before 2024-10-02 are unshuffled at load | `atomdata_base.py:2582-2589` | confirmed |
| Scope-format epoch | runs before 2026-01-16 00:00 use the old scope layout | `atomdata_base.py:2900-2901` | confirmed |
| Auto-ROI cache | last 8 runs' detections kept in memory | `roi.py:54-56` | confirmed |
| Vault auto-lite threshold | 8 run IDs | `atomdata_vault.py:244, 337-352` | confirmed |
| Vault defaults | `sort=True, merge_overlap=True, uniform_roi=True, scope_merge='pad_nan', structure='auto', xvar_mode='pad', skip_missing=True` | `atomdata_vault.py:234-253` | confirmed |
| Climate defaults | host `K`, °C, guest login, `http://weldlabaio1.physics.ucsb.edu/api_jsonrpc.php`, `max_gap_s=180`, `pad_s=600` | `climate/client.py:45, 250`; `zabbix.py:19, 48`; `attach.py:140-143` | confirmed |

## 5. expert_nuances

5.1 **The data directory is frozen at import.** `server_talk.__init__(data_dir=os.getenv("data"), ...)` evaluates `os.getenv` when the class body is executed, i.e. at `import waxa.data.server_talk` (`waxa/data/server_talk.py:16-17`), and `atomdata(..., server_talk=st())` builds its default instance when `waxa.atomdata` is imported (`waxa/atomdata.py:79`, `atomdata_base.py:576`). Changing `%data%` (or `os.environ['data']`) afterwards has no effect until the kernel restarts; pass `server_talk=server_talk(data_dir=...)` instead. With `%data%` unset, nothing fails at import; the first lookup fails (6.1). **confirmed**

5.2 **What `atomdata(0)` / `atomdata(-n)` considers "finished"** (`server_talk.py:84-116, 187-296`):
- date folders are listed once and walked newest first; folder names must parse as `YYYY-MM-DD`, be on/after 2023-06-22 and **not later than `datetime.today()` on the analysis PC** (`server_talk.py:192-212`);
- inside a folder, `*.hdf5` files are ordered by the integer before the first `_` (run ID), descending (`server_talk.py:214-231`);
- every candidate is opened (`RECENT_COMPLETED_TRUST_WINDOW = 0`, line 12) with `locking=False` and accepted when `run_complete` is true; when `run_complete` is false it is accepted only if `run_finalized` is true (a finalized-but-incomplete run is "finished" and loads with the `!!` banner); files without `run_complete` fall back to "every xvar in `params/` is an array"; any exception (torn/locked file) means "not finished" (`server_talk.py:237-296`). Until 2026-09-24 the fast path never fired because h5py returns `numpy.bool_` and the code used `is True` (comment, `server_talk.py:252-254`). Test: `waxa-src/tests/test_incomplete_run_attrs.py::test_run_lookup_treats_a_finalized_incomplete_run_as_finished`.
- `lite=True` with `idx<=0` picks the newest finished **regular** run and then wants its lite file (`server_talk.py:86-105`). **confirmed**

5.3 **Positive run IDs skip the completion check** and return `matches[0]` of the **first (newest) date folder** that contains `0083120_*` (`server_talk.py:348-393`). The duplicate warning prints only when two files with the same ID are in the same folder; the search stops early at a folder whose largest run ID is below the target (`server_talk.py:389-390`), and it retries once only if no date folder could be listed at all (`server_talk.py:399-406`). **confirmed**

5.4 **Shuffled scans are unshuffled on disk, not at load.** At END_RUN, the liveOD server's `DataSaver.save_data_from_payload` unshuffles, using `sort_idx`/`sort_N`, every numeric array param except the protected scan keys, every DataVault array, the images and image timestamps, `timestamp_shot_end` and the scope traces, then sets `unshuffle_applied=True`; the in-place image rewrite is bracketed by `unshuffle_in_progress` (`waxa/data/data_saver.py:570-622, 692-771, 827-853`). `sort_idx`/`sort_N` stay in the file as the record of acquisition order. `atomdata` therefore starts with `_analysis_tags.xvars_shuffled = False` (`atomdata_base.py:518-524`) and only unshuffles files from before 2024-10-02 (`atomdata_base.py:2582-2589`). `ad.reshuffle()` puts shots back into acquisition order; `ad.unshuffle()` undoes it. Nobody reads `unshuffle_in_progress` / `unshuffle_applied` on the load side (grep: only `data_saver.py`) (7.4). **confirmed**
- With `shuffle=True` (default, `waxx/base/expt.py:138`, `kexp/base/base.py:95`), the Dealer **sorts each xvar ascending before shuffling** (`sort_preshuffle=True`, `waxa/base/dealer.py:77-100`): the order you wrote in `self.xvar(...)` is not kept; after load every xvar is ascending. Repeats are made with `np.repeat` before the shuffle (`waxx/base/scanner.py:697-700`), so after unshuffling repeats sit next to each other. Two xvars of equal length receive the **same** permutation (`dealer.py:105-111`). The shuffle is a nested loop over independently permuted axes, not a random order over grid cells. **confirmed**
- `np.sort` on a 2-D xvar (a list of arrays per shot) sorts **within** each row, not the rows (`dealer.py:99-100`). **inferred** (numpy semantics; not seen in use).

5.5 **ROI resolution order and side effects** (`waxa/roi.py:419-501`):
1. `roi_id == 'auto'` is handled first and never looks at a saved ROI; lite data ignores it (prints `roi_id='auto' does not apply to lite data (already cropped).`).
2. The ROI saved in this run (`roix/roiy` root attrs, read during the load and handed to ROI as a cache) is used when `roi_id is None` and `skip_saved_roi` is false.
3. `int` = read `roix/roiy` from that run's file (an int of `0` or below means "newest"/"relative", because it goes through `get_data_file`, `roi.py:577-579`).
4. `str` = row of `%data%\roi.xlsx`; a missing key opens the dialog and appends a row (`roi.py:489-495, 676-702`). The spreadsheet is re-read only when its mtime changes (`roi.py:28-46`) and is rewritten whole by pandas.
5. Nothing chosen (all `-1`) means the whole frame (`roi.py:496-501`).
The dialog's choice lives only in memory. It is saved only by `ad.save_roi_h5()` (opens the **raw run file** `r+`) or `ad.save_roi_excel(key)`. **confirmed**

5.6 **OD arithmetic** (`waxa/image_processing/compute_ODs.py:34-83`): frames are cast to int32 (int16 for uint8), `atoms-dark` and `light-dark` negatives are set to 0, the ratio is 0 wherever `light-dark` is 0, `OD = -ln(ratio)` only where the ratio is non-zero (else 0), and negative OD is set to 0. Consequences: a pixel whose atoms frame is at or below the dark frame (probe fully absorbed) reads **OD 0, not large** (a hole in a dense cloud; atom number too low), and the clip at 0 biases the noise floor positive (a large ROI adds positive "atoms"). OD is computed on the ROI crop only; `od_raw` (full frame) is computed the first time it is read (`atomdata_base.py:1163-1189, 2944-2973`). For fluorescence/dispersive/polmod imaging `ad.od` is `(pwa-dark)/(pwoa-dark)`, and no `atom_number` is computed (`atomdata.py:277-278`). **confirmed**

5.7 **Cloud fits** (`compute_gaussian_cloud_params.py:97-159`, `atomdata_base.py:1191-1218`): one `GaussianFit` per shot on `sum_od_x` (sum over rows) and `sum_od_y`, x axis `pixel_size_m/magnification * arange(n)` metres **from the ROI's left/top edge** (so `fit_center_x` moves when you recrop). The worker passes `print_errors=False`, and `GaussianFit` turns a failed fit into NaNs itself, so ordinary failures are silent; `"{n}/{total} fits failed"` counts only unexpected exceptions (7.6). A pool is used only at >= 2000 fits (a fresh loky pool costs ~4 s on Windows, comment lines 89-94). `pixel_size_m` and `magnification` come from the file's `camera_params` (the configuration from `kexp/config/camera_id.py`), so every length and atom number scales with them. **confirmed**

5.8 **`slice_atomdata`** (`atomdata.py:137-146`, `atomdata_base.py:1303-1634`):
- Positional order differs: on `atomdata` it is `(which_xvar_idx, xvar_value, which_shot_idx, ...)`; on `atomdata_base`/`AtomdataVault` it is `(which_shot_idx, which_xvar_idx, ...)`. `ad.slice_atomdata(2)` means "axis 2" on an atomdata and "index 2" on a vault. Always use keywords. **confirmed**
- `xvar_value` scalar = nearest value, **no tolerance**, `UserWarning` if the match is the first/last point; tuple `(min, max)` = every index in range +/- tol, `ValueError` if none; list/array = nearest per value within tol, else `ValueError`. tol = `xvar_tolerance` x robust mean spacing of `ad.xvars[i]`, which includes repeated values, so with repeats the mean spacing (and tol) shrinks by about `N_repeats` (`atomdata_base.py:1323-1382`). **confirmed** (the shrink is arithmetic on the code, **inferred** in effect)
- `which_shot_idx` indexes `ad.xvars[i]` as stored (with repeats). On a multi-axis scan whose sliced axis carries the repeats, the indices are divided by `n_repeats` and the repeats are first moved to the next axis with `reassign_repeats` on the copy, which re-runs the image analysis of the whole copy (`atomdata_base.py:1461-1471, 2330-2332`). On a 1-axis scan all repeats of the chosen values are returned unless `ignore_repeats=True`.
- Passing both `xvar_value` and a non-zero `which_shot_idx` raises; `which_shot_idx=0` with `xvar_value` is silently ignored. A NumPy integer index (e.g. from `np.argmax`) raises `TypeError` in `ensure_ndarray` (`helper/datasmith.py:281-297`) (15).
- Not sliced (copied by reference, so wrong length afterwards): raw `images`/`image_timestamps`, `timestamp_shot_end`, a vault's `shot_run_id` and `stack_mask`, and any params array other than the sliced xvar (`_copy_self_for_slice` fallback, `atomdata_base.py:1762-1770`). Analysis arrays are sliced, not recomputed (`atomdata_base.py:1590-1612`). **confirmed**

5.9 **Automatic units on loaded data are name-based only.** `detect_unit(ad)` calls `get_param(ad.params, name)`, which reads the source of `ad.params.__class__` with `inspect.getsource` (`waxa/units.py:93-117`). For a loaded run that class is `waxa.config.expt_params.ExptParams` (18 lines, three params, no unit comments; `atomdata_base.py:18, 2729`; `waxa/config/expt_params.py`), so the comment step never matches and `guess_unit` decides. Unit comments in `kexp/config/expt_params.py` only matter if you pass `params_obj=kexp ExptParams()` yourself, or in the liveOD Adjust panel (which uses the strict `unit_from_comment`). If you do pass the kexp class to `get_param`, its substring matching misreads prose: a comment `# unitless` matches `s` before `unitless` (dict order, `units.py:52-68`); `# affects APD absorption calibration` on `t_tof_apd_abs` (`kexp/config/expt_params.py:28`) gives `s`. `amp_`/`pfrac_`/`fraction` names get the literal label `amp` in plot axes (`units.py:207-209`). Override with `detect_unit(ad, 0, xvarunit='µs', xvarmult=1e6)` or pass `xvarunit`/`xvarmult` to the plot helper. **confirmed**

5.10 **Repeat detection ignores `N_repeats`.** `_get_repeat_axis_info` looks for an xvar whose values repeat; exactly one axis may repeat, with one common count, and the repeats must be consecutive (`atomdata_base.py:2059-2088`). Any violation (two repeated axes, an xvar with an accidental duplicate, unequal counts) is swallowed: `ad.avg` becomes a pass-through and `ad.std`/`ad.sem` return zeros, with no message (`atomdata_base.py:2043-2052`). `std` is the population std (ddof=0) and `sem = std/sqrt(n)` (`atomdata_base.py:1890-1914, 2025-2032, 2171-2195`), about 18% smaller than the textbook `s/sqrt(n)` at n=3 (arithmetic). The vault groups by unique xvar value and divides each point by its own count (`atomdata_vault.py:2297-2347`). **confirmed**

5.11 **Incomplete runs.** liveOD finalizes a run that lost frames with `run_finalized=True, data_complete=False, run_complete=False` and the reason and counts (`data_saver.py:855-870`). Frames are stored by arrival index, so after a missing frame every later frame is one shot early and the last slots are empty; the banner says so only when `images_received < images_expected` (`atomdata_base.py:471-496`; tests `test_incomplete_banner.py`). Such a run **is** returned by `atomdata(0)` (5.2). A lite copy made by `ad.save_lite_copy()` is stamped `run_complete=True` but keeps the copied `data_complete=False` attr (`atomdata_base.py:1003-1017`), so its banner still prints. **confirmed**

5.12 **`ad.run_info.run_datetime` is the time you loaded the file**, not the run time, for liveOD-era files: liveOD's run_info proxy has no `run_datetime` (`data_saver.py:486-499`), so the `RunInfo()` default `time.localtime()` survives the load (`waxa/data/run_info.py:19`). Use `run_info.run_datetime_str`, the file name, or `ad.img_timestamp_atoms`. The two epoch checks that read it (`_unshuffle_old_data` 2024-10-02, scope format 2026-01-16) therefore always choose "new" for such files (`atomdata_base.py:2587, 2900-2901`). `waxa/climate/attach.py:72-99` avoids it deliberately. **confirmed** (the wiki's "files after 2026-05-18" date is not visible in code; needs a human)

5.13 **`camera_overrides`** (`atomdata_base.py:450-513, 1384-1396, 2774-2780`; liveOD side `waxx/util/live_od/live_od_server.py:373-458`): `camera_params/` is the request and is also what the kernel's timing used (`kexp/base/image.py:115-132, 423-425` read `camera_params.exposure_time`, `exposure_delay`, `t_camera_trigger`). The applied values are only in the root attr `camera_overrides` (JSON `{"schema":1, "camera_key", "persist_since", "fields": {name: {requested, applied, origin}}}`), written at END_RUN and only when non-empty. Field names are the driver's: `gain` and `exposure_time` (`waxx/control/cameras/andor.py:392, 403`; `basler_usb.py:210, 219`); Andor gain is the EM gain factor, Basler gain is dB, exposure is seconds. A run that never reached END_RUN has no record. An unparseable record comes back as `{"unreadable": ..., "raw": ...}` with its own banner. `AtomdataVault` keeps the first run's `camera_params` and `camera_overrides` for all runs and warns (`atomdata_vault.py:1173-1224`). **confirmed**

5.14 **Cross section per shot** (4.6): the current is the commanded one; `>= 1 A` is high field. A shot with `i_outer_imaging == 0` (outer coil off, or a shot that never triggered the camera, which leaves the default 0, `kexp/base/image.py:72-73`) gets the lambda^2 placeholder and so **2.09x fewer atoms** than the same OD at high field (`cross_section.py:26-31`). If `data.i_outer_imaging` does not have the scan shape (e.g. after you reshaped `ad.data` yourself, or an extra `idx_pwa` axis) every shot silently falls back to the high-field value; only the tag says so (`cross_section.py:142-154`; test `test_shape_mismatch_falls_back`). Check `np.unique(ad.atom_cross_section_source)`. The value itself comes from `kamo.imaging.cross_sections`, with a built-in copy and a warning when kamo is older than 2026-09-18 (`cross_section.py:53-66`). **confirmed**

5.15 **AtomdataVault traps**:
- Defaults `structure='auto'` and `xvar_mode='pad'` (`atomdata_vault.py:249-250`): when exactly one scalar fixed param differs across 1-D image runs, the constructor calls `set_xvar(key, xvar_mode='pad')`, which raises `NotImplementedError` unless `ignore_images=True` (`atomdata_vault.py:571-613, 1773-1778`) (6.10). Pass `structure='manual'` or `xvar_mode='rectangular'`. **confirmed** (code path; how often runs differ in exactly one scalar param needs a human)
- `_is_missing_run_error` treats any exception whose text contains `missing`, `not found`, `no such file`, `could not find`, `run id`, `run_id` or `data file` as a missing run and skips it with one summary warning (`atomdata_vault.py:704-718`); `from_run_range` skips **any** exception (`atomdata_vault.py:2813-2818`). **confirmed**
- `from_run_range` loads each run itself with `atomdata(rid, roi_id=anchor, lite=lite)`, default `lite=True`; a lite load forces `roi_id=None` (`atomdata_base.py:625-626`), so for runs with neither a lite copy nor a saved ROI the ROI dialog can open once per run, contrary to its docstring (`atomdata_vault.py:2790-2830`). **best explanation, still needs checking**
- Building a vault writes: the anchor ROI into the first run's raw file (`atomdata_vault.py:652-653, 738-739, 759, 2823`) and lite copies into `%data%\_lite` (`_load_lite_with_anchor`, 778-806). More than 8 run IDs switch to lite automatically (337-352).
- The vault loads through the import-time default server_talk (it takes no `server_talk` argument; `atomdata_vault.py:267, 630-633`).
- `unshuffle/reshuffle/reassign_repeats/transpose_data` raise `NotImplementedError` on a vault (`atomdata_vault.py:2904-2927`). **confirmed**

5.16 **"Loading" writes to the data drive in these cases** (useful when someone asks for read-only analysis): `ad.save_roi_h5()`, `ad.save_roi_excel()`, a string `roi_id` not yet in `roi.xlsx` (appends a row), `lite=True` without a lite copy (creates one), `ad.recrop()` on lite data (writes the ROI into the raw file and rebuilds the lite file, `atomdata_base.py:778-819`), vault construction (5.15), Data Browser tags/comments (`browser/scanner.py:1158-1185`). `kexp/analysis/rabi_posterior_cli.py:163-166` loads with `lite=False, roi_id='auto'` for exactly this reason. **confirmed**

5.17 **Multi-frame runs (`N_pwa_per_shot > 1`)** add an `idx_pwa` axis to `xvarnames`/`xvars`/`xvardims` in `_sort_images` (`atomdata.py:345-352`). The matching `np.append(self.sort_idx, ...)`/`np.append(self.sort_N, ...)` results are thrown away (no-op), so a later `_init_dealer`/unshuffle on a shuffled run cannot find a permutation for that axis, and `_unpack_xvars` looks up `params.idx_pwa`, which does not exist (15). Absorption imaging forces `N_pwa_per_shot = 1` at run time (`waxx/base/scanner.py:684-688`). **confirmed** (code reading; not exercised)

5.18 **Performance knobs**: repeat siblings reduce arrays under 32 MiB eagerly and larger ones (raw frames, `od_raw`, scope traces) on first access (`atomdata_base.py:36-46, 1953-2023`); auto-ROI detection starts on a thread during the load when a dialog is likely (`atomdata_base.py:2789-2805`); the dialog prefetches neighbouring ODs (`roi.py:1770-2050`). Timing lines print on every load (`atomdata_base.py:631`). **confirmed**

5.19 **Rabi fits, old vs new**: `waxa.plotting.rabi_oscillation` (kept for old notebooks) reports `t_pi = pi/Omega` and prints a railed-bound warning (`standard_experiments.py:12-55, 130-398`); `waxa.analysis.rabi` reports `t_pi = t_dead + pi/omega` (the commanded length to write into a config) separately from `t_pi_rate = pi/omega`, groups repeats by pulse length (works on shuffled or ragged data), chooses the decay model by AICc and fits runs jointly (`waxa/analysis/rabi/rabi_fit.py:1-45`). Its `rabi(run_id)` loads with `roi_id='auto'` by default (ignores the saved ROI) (`rabi_fit.py:587-605`). **confirmed**

5.20 **Climate lining-up** (`waxa/climate/attach.py`): per-shot clock preference `img_timestamp_atoms` > `timestamp_shot_end` > run start from the file name / `run_datetime_str`; values not > 1e9 (unset) become NaN; nearest sample within 180 s, else NaN; sensors sample once a minute; Zabbix keeps 90 days of raw history and a year of hourly trends (`climate/client.py:1-9`); read-only, guest login, needs the Broida VPN (`climate/__init__.py:11`). `ad.climate` is in memory only. **confirmed** (retention figures are from the docstring: **needs a human** to confirm server config)

5.21 **Units of everything returned** (for the 2 a.m. reader): all lengths in metres at the atoms (`fit_sd_x`, `fit_center_x`, `axis_x`), atom numbers are counts, `ad.params.*` SI as in `ExptParams`, cross sections m^2, timestamps unix seconds (camera PC clock for `img_timestamp_*`, liveOD PC clock for `timestamp_shot_end`), `GaussianTemperatureFit.T` kelvin. **confirmed** (by the formulas cited above)

## 6. loud_failures

6.1 `%data%` not set on this PC (`server_talk.py:17, 158`; Python 3.11 text):
```
TypeError: stat: path should be string, bytes, os.PathLike or integer, not NoneType
```
Cause: `server_talk.data_dir` is `None`, `os.path.exists(None)` raises in `check_for_mapped_data_dir`. Fix: set the `data` environment variable (PC-Setup step 4) and restart the Jupyter kernel, or pass `server_talk=server_talk(data_dir=...)`. **confirmed** (message verified with `python3 -c "os.path.exists(None)"` here; Windows text **inferred** to be the same)

6.2 Nothing finished found (`server_talk.py:97, 114`):
```
ValueError: No completed data files were found.
```
Cause: the data drive is not reachable (see the preceding print, 6.3), every file in reach is unfinished, or you are on a PC whose clock is behind the date folders (5.2). Fix: check the drive (`B:`), then load by run ID.

6.3 Data drive missing (printed, then the lookup continues and usually ends in 6.2 or 6.4) (`server_talk.py:149, 153, 156, 159`):
```
Data dir (B:\_K\PotassiumData\) not found. Attempting to re-map network drives.
Data dir still not found. Are you connected to the physics network?
Network drives successfully mapped.
Data dir (/mnt/data) not found. Are you connected to the network?
```
Template: `f"Data dir ({self.data_dir}) not found. ..."`. The Windows branch runs `"G:\Shared drives\Weld Lab Shared Drive\Infrastructure\map_network_drives.bat"`; on a PC without that Google Drive path, `subprocess.run` of a missing program is expected to raise `FileNotFoundError: [WinError 2] The system cannot find the file specified` (**inferred**, Windows only). Under the dashboards the shared `data_dir_guard` handles this instead (`server_talk.py:134-145`).

6.4 Run ID not on the drive (`server_talk.py:105, 406`):
```
ValueError: Data file with run ID 83120 was not found.
```
Template `f"Data file with run ID {run_id:1.0f} was not found."`. Causes: typo, the run was aborted and its file deleted, drive not mapped, or the file sits in a date folder after a folder whose largest run ID is lower (early stop, 5.3).

6.5 Bad path (`server_talk.py:121`):
```
ValueError: The provided path is not a hdf5 file.
```

6.6 Loading an unfinished run by ID (run still going, or the experiment died before END_RUN) (`atomdata_base.py:2538`):
```
ValueError: Run 83120 did not have a scanned parameter.
```
Cause: until END_RUN the file's `params/` is the INIT_RUN snapshot, where each xvar holds one number (`plug_in_xvars`, `waxa/base/dealer.py:28-34`; arrays are written only by `cleanup_scanned` in `end_wax`, `waxx/base/expt.py:385-395`, `waxx/base/scanner.py:659-671`). Fix: wait for the run to end; for a dead run the per-shot images may exist but the file will not load with atomdata (read it with h5py). A run with no frame written yet fails earlier with h5py's `KeyError` for `data/images` (`atomdata_base.py:2781-2783`; exact h5py text **inferred**). **confirmed** (reasoning over the code path)

6.7 `transpose_idx` in the constructor (`atomdata.py:188-190` calling `transpose_data(transpose_idx=False, ...)`):
```
TypeError: atomdata.transpose_data() got an unexpected keyword argument 'transpose_idx'
```
Fix: load normally, then `ad.transpose_data()` (2 xvars) or `ad.transpose_data([0,2,1])`. Also reached through `load_atomdata(..., avg_repeats=True)` (15). **confirmed** (Python 3.10+ wording)

6.8 `slice_atomdata` errors (`atomdata_base.py:1344-1380, 1440-1443`):
```
ValueError: slice_atomdata: specify either 'xvar_value' or 'which_shot_idx', not both.
ValueError: slice_atomdata: xvar_value tuple must have exactly 2 elements (min, max); got 3.
ValueError: slice_atomdata: no xvar values found in range (0.001, 0.002) ± 5e-05 on axis 0. Axis range: [0.003, 0.02].
ValueError: slice_atomdata: no xvar value matched 0.0125 within tolerance 5e-05 on axis 0. Closest is 0.012 (distance 0.0005).
UserWarning: slice_atomdata: xvar_value=0.05 matched the edge of xvars[0] (index 9, value 0.02). Axis range: [0.002, 0.02].
TypeError: Input must be float, int, list, or ndarray
```
The last one: `which_shot_idx` was a NumPy integer (`np.argmax(...)`); wrap it in `int(...)` (`helper/datasmith.py:294`).

6.9 Repeat helpers (`atomdata_base.py:2115-2117, 2262, 2559, 2102`):
```
ValueError: avg_array expects a scan-shaped numeric array whose leading dimensions are (10,); got shape (30,).
ValueError: Repeat reassignment only supports unshuffled atomdata. Call unshuffle() first.
ValueError: Cannot reshuffle after repeats have been reassigned.
ValueError: Number of repeats per value of an xvar must be the same for all values.
```
(the last only when you pass `xvar_idx=` explicitly; otherwise the same condition is silent, 7.2). Transpose: `There is only one variable -- no dimensions to permute.`, `For more than two variables, you must specify the new xvar order.`, `You must specify a list of axis indices that match the number of xvars.` (2419-2426).

6.10 Vault construction (`atomdata_vault.py:364-366, 846-903, 1773-1778, 1831-1836, 2682-2686, 2836-2840`):
```
NotImplementedError: AtomdataVault.set_xvar(..., xvar_mode='pad') currently requires ignore_images=True. Rebuild the vault with ignore_images=True or use xvar_mode='rectangular'.
ValueError: xvarname mismatch: run 83101 has 't_tof' but first input has 'frequency_detuned_imaging'. Pass xvarname_override=True to override.
ValueError: Image shape mismatch: run 83101 has per-shot shape (512, 512) but first input has (1024, 1024).
ValueError: imaging_type mismatch on run 83101.
ValueError: AtomdataVault: no loadable inputs remain after skipping missing run-ids.
ValueError: Cannot promote 'amp_imaging' to an xvar because its values do not form a rectangular grid with the existing xvar 't_tof'. Pass xvar_mode='pad' or choose a different param.
KeyError: "Run ID 83105 is not part of this AtomdataVault. Available run IDs: [83100, 83101]."
ValueError: No loadable runs found in range [83100, 83140] matching experiment_name='hf_bec'.
```
Plus warnings: `AtomdataVault: loading 12 run-ids; switching to lite datasets to limit memory (auto_lite_threshold=8). Pass auto_lite_threshold=None to disable, or lite=True to silence.`; `AtomdataVault: fixed parameters disagree across input runs (using values from the first run): amp_imaging, t_tof_extra. Call vault.param_report() for a per-run breakdown.`; `AtomdataVault: the runs' camera_params differ (the vault uses the first run's): gain. See vault.camera_param_disagreements.`; `AtomdataVault: in run(s) 83101 the camera applied settings other than camera_params (gain). See vault.camera_overrides_by_run.`; `AtomdataVault: reusing the ROI baked into the existing lite data for run 83101; it is trusted as-is and may differ from the anchor ROI (run 83100). Delete the lite file to regenerate it cropped to the anchor ROI.`

6.11 ROI (`roi.py:275-279, 513-518, 600-601, 2158-2169`):
```
RuntimeError: The ROI selector must be opened from the Qt main thread. Resolve the ROI first (waxa.roi.pick_roi) and pass explicit bounds to the background work.
RuntimeError: pick_roi must be called from the Qt main thread.
ImportError: PyQt6 is required for the ROI selector. Install it with: pip install PyQt6
ValueError: You must specify a key to save the ROI to the spreadsheet.
ValueError: The specified key must be a string.
ValueError: ROI key must be a non-empty string.
```
The first is what the Data Browser's "Select ROI…" shows in an "ROI Error" message box (15). `roi.xlsx` open in Excel while `_update_excel` writes is expected to raise a `PermissionError` from pandas (**inferred**, Windows file locking).

6.12 Lite copies (`atomdata_base.py:878-892`; `server_talk.py:529-530, 616-618`):
```
RuntimeError: save_lite_copy: this atomdata was loaded from a lite file (already cropped); nothing to do.
RuntimeError: save_lite_copy: cannot save while the in-memory data has been transformed (averaged / transposed / repeats reassigned). Reload the run fresh or pass force_reread=True.
ValueError: Pass both roix and roiy, or neither.
ValueError: ROI roix=[0, 900], roiy=[0, 400] does not fit images of shape (512, 512).
```
Prints: `[atomdata] Existing lite file is not readable HDF5; regenerating: <path>`, `Lite version of run 83120 saved at <path>.`, `Lite creation for run 83120 cancelled.`

6.13 Missing theory package (`waxa/fitting/gaussian.py:5`, also lorentzian/parabolic/polynomial):
```
ModuleNotFoundError: No module named 'kamo'
```
`waxa.fitting` needs k-amo, and `atomdata` imports it through `compute_gaussian_cloud_params` (`waxa/atomdata.py:38`); `setup.py` does not list it. Also needed at import: `cv2`, `pandas`, `joblib` (`roi.py:1-6`, `compute_gaussian_cloud_params.py:3`). Fix: the full workspace (`uv sync`, PC-Setup). An old kamo gives the warning `kamo.imaging.cross_sections not found: update k-amo. Using waxa's built-in copy of the absorption cross sections (same values).` (`cross_section.py:61-63`). **confirmed**

6.14 Deprecation (`atomdata_base.py:2345-2352`):
```
FutureWarning: atomdata.avg_repeats() is deprecated and no longer does anything. Repeat statistics are always available on the sibling atomdata objects ad.avg, ad.std, and ad.sem — e.g. use ad.avg.atom_number with error bars from ad.sem.atom_number.
```

6.15 Banners printed by the load (`atomdata_base.py:471-513, 2769-2780`), example values:
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!! RUN 83120 IS INCOMPLETE: 60/63 images received; camera timed out
!! 60 of 63 images arrived. Images are stored in arrival order,
!! so after the first missing frame the shot assignment is shifted and
!! the last slots are empty. Do not trust per-shot image data from this run.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

!! run 83102: camera settings differ from ad.camera_params (the request): gain 300.0 -> 30.0 (clamped)
```
Template: `f"!! run {run_id}: camera settings differ from ad.camera_params (the request): " + ", ".join(f"{key} {requested} -> {applied} ({origin})")`. Unreadable record: `!! run 83102: the file's camera_overrides record could not be read (JSONDecodeError: ...); the camera's settings may differ from ad.camera_params (the request)`. Other incomplete variants: `!! All 63 images arrived, but the run was flagged (reason above): do not` / `!! trust per-shot image data from this run until the reason is understood.` and `!! The file does not record how many images arrived. Do not trust` / `!! per-shot image data from this run until the reason is understood.`

6.16 Run-start banner in the **experiment terminal** (liveOD client, `waxx/util/live_od/live_od_client.py:198-215`, printed on the INIT_RUN and camera-ready replies, lines 273, 314):
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!! CAMERA SETTINGS DIFFER FROM camera_params (andor):
!!   gain: requested 300.0 -> applied 30.0 (clamped)
!! The run file records this in its root attribute camera_overrides;
!! camera_params/ in the file is the request, not what the camera ran.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```
liveOD's own log: `CAMERA OVERRIDE: run 83102 on andor: gain requested 300.0 -> applied 30.0 (clamped); camera_params in the file stay the request` (`live_od_server.py:397-399`).

6.17 Command-line tools: `run ids must be positive (relative indices like 0 / -1 are not accepted: say which run you mean)` (`rabi_posterior_cli.py:1590-1592`); `--out must be inside C:\lab\skynet_log\outputs: <path>` (`rabi_posterior_cli.py:1421`, `apd_state_mapping.py:327`); `python -m waxa.analysis.rabi` prints `  (cannot compare: t_raman_pi_pulse not in the run's params)` (`__main__.py:63`) and exits with code 1 when a fit is not ok (`__main__.py:57`).

6.18 Rabi (legacy) railing warning (`standard_experiments.py:47-55`):
```
[rabi_oscillation] WARNING: fitted Omega = 6.28319e+06 is railed at its UPPER bound (6.28319e+06). This is the bound, not a measurement -- widen it (see fit_max_frequency) and re-fit.
```

## 7. demon_candidates

7.1 **Error bars silently zero.** Pattern: `_refresh_repeat_statistics` wraps the repeat-axis detection in `try/except Exception` and falls back to `ad.avg` = pass-through, `ad.std`/`ad.sem` = zeros, with no message (`waxa/atomdata_base.py:2043-2052`). Triggers: repeats on two axes, an xvar with one accidental duplicate value, unequal repeat counts, non-consecutive repeats (`atomdata_base.py:2059-2088`). The plot looks fine: points with zero-length error bars. Also: a hand-written xvar list with duplicates (e.g. `[1,0,1,0]`) is sorted to `[0,0,1,1]` by the default shuffle (`dealer.py:99-100`) and then *is* treated as a repeat axis. *Seen and confirmed* in code; no date (shallow history).

7.2 **Cloud-fit failures are NaN without a word.** `fit_gaussian_sum_dist` builds each fit with `print_errors=False` (`compute_gaussian_cloud_params.py:97-102`), and `GaussianFit` converts a failure into NaN parameters itself (`gaussian.py:25-33`), so `error_count` stays 0 and `"N/M fits failed"` is not printed for ordinary failures (`compute_gaussian_cloud_params.py:156-157`). Users see NaN holes in `fit_sd_x` / `fit_center_x` (and NaN `atom_number_fit_area_x`) while `atom_number` (pixel sum) is fine. *Seen and confirmed.*

7.3 **`atomdata(0)` is not the file you think.** Silent skips (`server_talk.py:187-296`): the newest run is still being written (no `run_finalized`), the experiment died before END_RUN, the file is momentarily unreadable (any exception = "not finished"), or the date folder is named later than the analysis PC's `datetime.today()` (folders "in the future" are ignored, line 199; a laptop with a wrong clock or date, or a notebook running just after midnight while the experiment PC is still on yesterday). The load prints the run ID it chose as a bare number (`atomdata_base.py:2745`), which is easy to miss. Before 2026-09-24 the completion fast path was dead (comment `server_talk.py:252-254`). *Best explanation, still needs checking* for the clock case; the in-flight case is *confirmed*.

7.4 **A torn unshuffle is not surfaced on load.** If liveOD died during the in-place image rewrite, the file keeps `unshuffle_in_progress=True` and the saver only prints a WARNING at save time (`data_saver.py:677-683, 836-853`). `atomdata` never reads `unshuffle_in_progress` or `unshuffle_applied` (grep: no readers outside data_saver.py), loads with `xvars_shuffled=False`, and so pairs params with images in an unknown mix of orders. *Confirmed* in code; occurrence *needs checking*.

7.5 **Run-ID collisions across days are silent.** `_scan_for_run_id` returns the first date folder with a match and warns only about duplicates inside that folder (`server_talk.py:375-388`). Two files `0083120_*` in different date folders: you always get the newer folder's file, no warning. *Confirmed.*

7.6 **`ad.run_info.run_datetime` is "now".** liveOD's run_info lacks `run_datetime`, so the RunInfo default (load time) survives (`data_saver.py:486-499`, `run_info.py:19`). Anything that plots or sorts runs by `run_datetime` sees the analysis time. *Confirmed*; the climate module documents it (`climate/attach.py:75-78`).

7.7 **Atom number silently 2.09x low (or right for the wrong reason).** The cross section is chosen from the *commanded* outer-coil current at the first camera trigger (`kexp/base/image.py:63-79`, `big_coil.py:136-145`). A shot at 0 A gets the uncalibrated lambda^2 placeholder (`cross_section.py:26-31, 69`), so low-field atom numbers are 2.09x lower than the closed-line value would give. A scan-shape mismatch sends every shot to the high-field fallback (`cross_section.py:142-154`). The only trace is `ad.atom_cross_section_source`. Since 2026-09-16 (docstring, `cross_section.py:6, 33`). *Confirmed.*

7.8 **Saturated pixels read OD 0.** `compute_OD` sets OD to 0 where `atoms-dark <= 0` (ratio 0) and clips negative OD to 0 (`compute_ODs.py:68-79`). A dense cloud shows a hole in the middle and a low atom number; a large ROI accumulates positive noise. *Confirmed* (arithmetic).

7.9 **Plot units come from the name, not from ExptParams comments.** `detect_unit(ad)` inspects `waxa.config.expt_params.ExptParams`, which has no unit comments, so every label is a name-and-magnitude guess (`units.py:93-117, 153-236`; `atomdata_base.py:2729`). A `t_` param that is not a time, or a frequency param without `freq`/`f_` in its name, gets a wrong or empty unit; `amp_*` shows `(amp)`. *Confirmed.*

7.10 **Slices keep some unsliced arrays.** `_copy_self_for_slice` copies every remaining attribute by reference (`atomdata_base.py:1762-1770`); `timestamp_shot_end`, raw `images`/`image_timestamps`, a vault's `shot_run_id`/`stack_mask` keep the full length. Code that reads them from a slice gets the wrong shots: `shot_times()` on an image-less slice (falls back to `timestamp_shot_end`, `climate/attach.py:122-125`), `shots_from_run()` / `drop_runs()` on a sliced vault. *Confirmed* in code.

7.11 **`slice_atomdata(3)` means different things.** Positional argument 1 is `which_xvar_idx` on `atomdata` (`atomdata.py:137`) but `which_shot_idx` on `atomdata_base`/`AtomdataVault` (`atomdata_base.py:1398`). *Confirmed.*

7.12 **Vaults drop runs on unrelated errors.** `_is_missing_run_error` matches substrings like `not found`, `run id`, `data file` in *any* exception (`atomdata_vault.py:704-718`), and `from_run_range` skips every exception (`atomdata_vault.py:2813-2818`); one `UserWarning` line summarises. A run that fails for a real reason (ROI error, reshape error mentioning "run id") quietly disappears from the vault. *Confirmed* (heuristic in code).

7.13 **`load_atomdata` shifts its arguments.** `load_atomdata(idx, roi_id, path, skip_saved_roi, transpose_idx, avg_repeats)` passes them positionally into `atomdata(idx, roi_id, path, lite, skip_saved_roi, transpose_idx, ...)` (`waxa/data/load_atomdata.py:43-47`): `skip_saved_roi=True` loads the **lite** file, `transpose_idx=[...]` becomes `skip_saved_roi`, `avg_repeats=True` becomes `transpose_idx` (TypeError, 6.7). The default call behaves correctly, which is why nobody noticed. *Confirmed.*

7.14 **"ROI not selected, aborting." does not abort.** Cancelling the dialog prints that line and then `ROI was not specified. Defaulting to whole image.` and the load continues on the full frame (`roi.py:671-674, 496-501`). A whole-frame ROI gives a large, noise-biased atom number (7.8). Nothing is saved, so the next load asks again. *Confirmed.*

7.15 **The data folder is whatever `%data%` was at import.** (5.1) A notebook started before the variable was set, or with a different value, reads another tree without complaint. *Confirmed.*

7.16 **Fit windows and index ranges.** `LorentzianFit` calls `Fit.__init__` twice, the second time without `include_idx/exclude_idx`, so both are ignored (`lorentzian.py:11-15`). `crop_array_by_index` compares `indices + start` against `exclude_idx`, so with `include_idx[0] != 0` the wrong points are excluded (`helper/datasmith.py:249-256`). Both return a normal-looking fit. *Confirmed.*

7.17 **Camera settings of old runs.** The `camera_overrides` record exists only since commit d772b3c (2026-09-26); before that, and for any run that never reached END_RUN, `ad.camera_params` may differ from what the camera did with no trace (`live_od_server.py:432-458`). *Confirmed* (commit message, code).

7.18 **`ad.atom_number_apd.frac_down` equals `frac_up`** (`atomdata_base.py:531-532`). *Confirmed.*

7.19 **`rabi(run_id)` ignores your saved ROI** (`roi_id='auto'` default, `rabi_fit.py:594-605`; `roi.py:444-459`): atom numbers from the CLI and from a notebook using the saved ROI can differ. *Confirmed.*

7.20 **Fit centres depend on the ROI.** `axis_x` starts at the ROI's left edge (`atomdata_base.py:1200-1207`); comparing `fit_center_x` between runs cropped differently (or before/after `recrop`) compares different origins. *Confirmed.*

7.21 **Browser tags edit the raw run files.** `AnnotationWriteWorker` opens each run file in append mode to write `browser_tags`/`browser_comment` (`browser/scanner.py:1172-1185`); tagging a run that liveOD is still writing is a concurrent writer on the same HDF5 file. *Best explanation, still needs checking* (whether liveOD holds the file open between frames).

## 8. symptoms

8.1 *Notebook cell, first `atomdata(...)` on a new PC:* traceback ending `TypeError: stat: path should be string, bytes, os.PathLike or integer, not NoneType`. Expected: a run loads. Cause: `%data%` unset (6.1). Misleading: the message never mentions the data folder or an environment variable.

8.2 *Notebook:* `Data dir (B:\_K\PotassiumData\) not found. Attempting to re-map network drives.` then `Data dir still not found. Are you connected to the physics network?` then `ValueError: No completed data files were found.` Expected: a run. The ValueError sounds like "there is no data" when the drive is simply not mapped (6.2-6.3).

8.3 *Notebook, run you just started or that crashed:* `ValueError: Run 83120 did not have a scanned parameter.` Expected: partial data. Misleading: the run *did* scan; the file just has not been finalized (6.6).

8.4 *Notebook, `atomdata(0)` right after a run:* the bare number printed at the top is 83119, not 83120; plots look like the previous run. No error (7.3). Where to look: the first line of the cell output; liveOD Server window / status strip for whether END_RUN has been processed.

8.5 *Notebook:* a dark "ROI Selector" window appears on every load of the same run. Expected: asked once. Cause: the chosen box was never saved (`ad.save_roi_h5()`), 3.3/5.5.

8.6 *Notebook:* after closing the ROI window with Escape: `ROI not selected, aborting.` followed by `ROI was not specified. Defaulting to whole image.`; the load finishes and atom numbers are large and noisy. Misleading: "aborting" (7.14).

8.7 *Notebook:* error bars in `plt.errorbar(ad.avg.xvars[0], ad.avg.atom_number, ad.sem.atom_number)` are all zero although `N_repeats = 3`; no warning (7.1).

8.8 *Notebook:* `ad.fit_sd_x` has `nan` entries; no message; `ad.atom_number` for the same shots looks normal (7.2).

8.9 *Notebook:* `!! run 83102: camera settings differ from ad.camera_params (the request): gain 300.0 -> 30.0 (clamped)` right after the run number. Meaning: the Andor ran with EM gain 30, the file's `camera_params/gain` still says 300 and the kernel timing used the requested values; use `ad.camera_overrides['fields']['gain']['applied']` for the applied value (5.13). *Experiment terminal* showed the matching `!! CAMERA SETTINGS DIFFER FROM camera_params (andor):` banner at run start (6.16).

8.10 *Notebook:* 72 `!` characters, `!! RUN 83120 IS INCOMPLETE: 60/63 images received; camera timed out`, `!! 60 of 63 images arrived. ...`. Meaning: after the first missing frame each image belongs to the next shot; the last 3 slots are empty (zeros, OD 0). The load still succeeds and everything computes; nothing else warns (5.11, 6.15).

8.11 *Notebook:* atom numbers from a low-field run are about half what you expect, or a high-field run shows `'fallback-no-record'` in `np.unique(ad.atom_cross_section_source)` (7.7).

8.12 *Notebook, dense BEC:* the OD image has a dark (zero) spot in the densest part; atom number is low (7.8).

8.13 *Notebook plot:* x axis reads `amp_imaging (amp)` or a time-like name shows the wrong unit; no warning (7.9).

8.14 *Notebook:* `TypeError: atomdata.transpose_data() got an unexpected keyword argument 'transpose_idx'` from `atomdata(rid, transpose_idx=[1,0])` or `load_atomdata(rid, avg_repeats=True)` (6.7, 7.13).

8.15 *Notebook:* `load_atomdata(83120, skip_saved_roi=True)` loads the small cropped lite file (or creates it), not a fresh ROI on the full frames (7.13).

8.16 *Notebook:* `AtomdataVault([...])` with images ends in `NotImplementedError: AtomdataVault.set_xvar(..., xvar_mode='pad') currently requires ignore_images=True. ...` although you never asked for `set_xvar` (5.15, 6.10).

8.17 *Notebook:* a vault built from 10 runs reports `v.source_run_ids` with 8; the only hint is one `UserWarning: AtomdataVault: skipped 2 missing run-id(s) while loading inputs (83105, 83107).` (7.12).

8.18 *Data Browser window:* right-click a run → "Select ROI…" → status "Selecting ROI…", then an "ROI Error" message box: `The ROI selector must be opened from the Qt main thread. Resolve the ROI first (waxa.roi.pick_roi) and pass explicit bounds to the background work.` (15). Workaround: "Create Lite Dataset" (its ROI dialog works) or `atomdata(rid).save_roi_h5()` in a notebook.

8.19 *Notebook:* `ad2 = ad.slice_atomdata(np.argmax(ad.atom_number))` fails with `TypeError: Input must be float, int, list, or ndarray` (6.8); `ad.slice_atomdata(2)` returns a slice along axis 2 or raises IndexError instead of selecting shot 2 (7.11).

8.20 *Notebook:* `ModuleNotFoundError: No module named 'kamo'` on `from waxa import atomdata` (analysis laptop without k-amo) (6.13).

8.21 *Notebook:* `ad.atom_number` raises `AttributeError: 'atomdata' object has no attribute 'atom_number'` for a fluorescence or dispersive run (atom number is computed only for absorption, `atomdata.py:277-278`; message from `atomdata_base.py:2984-2986`).

8.22 *Notebook:* each load prints four or more `[atomdata timing] ...` lines. Normal (hard-wired, `atomdata_base.py:631`); not an error.
