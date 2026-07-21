import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from waxa.image_processing import compute_OD, process_ODs
from queue import Queue

# K-39 resonant absorption cross-section (m²) — D2 line, sigma+ polarisation
_K39_CROSS_SECTION = 5.878324268151581e-13


class Analyzer(QThread):
    analyzed = pyqtSignal()
    broadcast_signal = pyqtSignal(object)    # emits plot_data tuple for LiveODBroadcaster
    shot_scalars_signal = pyqtSignal(object) # emits dict per analyzed shot
    fk_tof_signal = pyqtSignal(object)       # emits per-shot FK TOF data (N_pwa > 1 only)

    def __init__(self, plotting_queue: Queue, viewer=None):
        super().__init__()
        self.imgs = []
        self.plotting_queue = plotting_queue
        self.roi = []
        self.viewer = viewer
        # Scalar computation state
        self.camera_params = None   # set via set_camera_params()
        self._server = None         # set via set_server()
        self._shot_idx = 0
        self._latest_xvar_values: dict = {}

    # ------------------------------------------------------------------
    # Configuration slots
    # ------------------------------------------------------------------

    def set_camera_params(self, camera_params_dict: dict):
        """Build a minimal CameraParams object from the payload dict."""
        if not camera_params_dict:
            self.camera_params = None
            return
        from waxa.dummy.camera_params import CameraParams
        cp = CameraParams()
        for k, v in camera_params_dict.items():
            try:
                setattr(cp, k, v)
            except Exception:
                pass
        self.camera_params = cp

    def set_server(self, server):
        """Store a reference to LiveODServer for metric subscription queries."""
        self._server = server

    def set_xvar_values(self, xvar_values: dict):
        """Slot — stores the latest xvar_values dict from SHOT_COMPLETE."""
        if xvar_values:
            self._latest_xvar_values = dict(xvar_values)

    def reset(self):
        """Reset shot counter and xvar state for a new run."""
        self._shot_idx = 0
        self._latest_xvar_values = {}

    # ------------------------------------------------------------------
    # Image pipeline
    # ------------------------------------------------------------------

    def get_img_number(self, N_img, N_shots, N_pwa_per_shot):
        self.N_img = N_img
        self.N_shots = N_shots
        self.N_pwa_per_shot = N_pwa_per_shot

    def get_analysis_type(self, imaging_type):
        self.imaging_type = imaging_type

    def got_img(self, img):
        self.imgs.append(np.asarray(img))
        if len(self.imgs) == (self.N_pwa_per_shot + 2):
            # Guard the OD computation: a malformed/short image set or a shape
            # mismatch must not kill the Analyzer thread (which would silently
            # stop live display for the rest of the run).  Skip the bad shot.
            try:
                self.analyze()
            except Exception:
                import traceback
                print("[Analyzer] analyze() failed — skipping this shot's OD:")
                traceback.print_exc()
            finally:
                self.imgs = []

    def analyze(self):
        self.img_atoms = self.imgs[0]
        self.img_light = self.imgs[self.N_pwa_per_shot]
        self.img_dark = self.imgs[self.N_pwa_per_shot + 1]
        self.od_raw = compute_OD(self.img_atoms, self.img_light, self.img_dark, imaging_type=self.imaging_type)
        self.od_raw = np.array([self.od_raw])
        self.od, self.sum_od_x, self.sum_od_y = process_ODs(self.od_raw, self.roi)
        self.od_raw = self.od_raw[0]
        self.od = self.od[0]

        # Crop the OD to the current view range for sum calculations
        cropped_od, x_slice, y_slice = self.crop_od_to_view_range(self.od)

        # Compute sums from the cropped OD
        cropped_sum_od_x = np.sum(cropped_od, axis=0)  # Sum along y-axis (rows)
        cropped_sum_od_y = np.sum(cropped_od, axis=1)  # Sum along x-axis (columns)

        # Use cropped sums instead of the original ones
        self.sum_od_x = cropped_sum_od_x
        self.sum_od_y = cropped_sum_od_y

        self.analyzed.emit()
        plot_data = (self.img_atoms, self.img_light, self.img_dark, self.od, self.sum_od_x, self.sum_od_y)
        self.plotting_queue.put(plot_data)
        self.broadcast_signal.emit(plot_data)

        # Compute and emit per-shot scalars if any subscriber is watching
        self._emit_scalars(cropped_od, self.sum_od_x, self.sum_od_y)
        # For FK TOF: compute per-PWA widths when multiple atom images exist
        self._emit_fk_tof()
        self._shot_idx += 1
        
    # ------------------------------------------------------------------
    # Scalar computation
    # ------------------------------------------------------------------

    def _emit_scalars(self, cropped_od, sum_od_x, sum_od_y):
        """Compute per-shot scalar quantities and emit shot_scalars_signal.

        Only runs if at least one subscriber (local or remote) has registered
        interest via the server's subscription counter.
        """
        requested = self._server.get_requested_metrics() if self._server is not None else set()
        if not requested:
            return

        nan = float('nan')
        scalars = {
            'shot_idx': self._shot_idx,
            'xvar_values': dict(self._latest_xvar_values),
            'atom_number': nan,
            'atom_number_fit_area_x': nan,
            'atom_number_fit_area_y': nan,
            'fit_sd_x': nan,
            'fit_sd_y': nan,
            'fit_amp_x': nan,
            'fit_amp_y': nan,
        }

        cp = self.camera_params
        try:
            if cp is not None:
                dx = cp.pixel_size_m / cp.magnification
                scalars['atom_number'] = float(np.sum(cropped_od)) * dx * dx / _K39_CROSS_SECTION
            else:
                # No physical calibration — use integrated OD as a relative proxy
                scalars['atom_number'] = float(np.sum(cropped_od))
        except Exception:
            pass

        if 'fits' in requested and sum_od_x.size > 4 and sum_od_y.size > 4:
            self._compute_fits(scalars, sum_od_x, sum_od_y, cp)

        self.shot_scalars_signal.emit(scalars)

    def _compute_fits(self, scalars, sum_od_x, sum_od_y, cp):
        """Gaussian fits on x and y projections; updates scalars dict in-place."""
        from waxa.fitting.gaussian import GaussianFit

        dx = cp.pixel_size_m / cp.magnification if cp is not None else 1.0
        xaxis_x = dx * np.arange(sum_od_x.size)
        xaxis_y = dx * np.arange(sum_od_y.size)

        try:
            gx = GaussianFit(xaxis_x, sum_od_x)
            scalars['fit_sd_x'] = float(gx.sigma)
            scalars['fit_amp_x'] = float(gx.amplitude)
            if cp is not None:
                scalars['atom_number_fit_area_x'] = float(gx.area) * dx / _K39_CROSS_SECTION
        except Exception:
            pass

        try:
            gy = GaussianFit(xaxis_y, sum_od_y)
            scalars['fit_sd_y'] = float(gy.sigma)
            scalars['fit_amp_y'] = float(gy.amplitude)
            if cp is not None:
                scalars['atom_number_fit_area_y'] = float(gy.area) * dx / _K39_CROSS_SECTION
        except Exception:
            pass

    def _emit_fk_tof(self):
        """Compute Gaussian sigma for each PWA image and emit fk_tof_signal.

        Only runs when N_pwa_per_shot > 1.  Each PWA image (self.imgs[i]) is
        paired with the shared reference light (self.img_light) and dark
        (self.img_dark) to compute an absorption OD, then a Gaussian is fitted
        to each projection to extract sigma_x and sigma_y.

        self.imgs still holds all images when this is called from analyze()
        because got_img() clears it only after analyze() returns.
        """
        if self.N_pwa_per_shot < 2:
            return

        cp = self.camera_params
        dx = (cp.pixel_size_m / cp.magnification) if cp is not None else 1.0

        sigma_x_list = []
        sigma_y_list = []

        try:
            from waxa.fitting.gaussian import GaussianFit
            for i in range(self.N_pwa_per_shot):
                od_i = compute_OD(
                    self.imgs[i], self.img_light, self.img_dark,
                    imaging_type=self.imaging_type,
                )
                cropped_i, _, _ = self.crop_od_to_view_range(od_i)
                sum_x_i = np.sum(cropped_i, axis=0)
                sum_y_i = np.sum(cropped_i, axis=1)
                xaxis_x = dx * np.arange(sum_x_i.size)
                xaxis_y = dx * np.arange(sum_y_i.size)
                try:
                    gx = GaussianFit(xaxis_x, sum_x_i)
                    sigma_x_list.append(float(gx.sigma))
                except Exception:
                    sigma_x_list.append(float('nan'))
                try:
                    gy = GaussianFit(xaxis_y, sum_y_i)
                    sigma_y_list.append(float(gy.sigma))
                except Exception:
                    sigma_y_list.append(float('nan'))
        except Exception:
            return

        self.fk_tof_signal.emit({
            'sigma_x': sigma_x_list,
            'sigma_y': sigma_y_list,
            'shot_idx': self._shot_idx,
            'N_pwa': self.N_pwa_per_shot,
        })

    # ------------------------------------------------------------------
    # OD crop helper
    # ------------------------------------------------------------------

    def crop_od_to_view_range(self, od):
        """
        Crop the OD array to the drawn ROI rect (if set) or the current view range.

        If the viewer has an active drawn rectangle (set via "Set ROI" button), that
        rectangle is used as the crop region.  Otherwise falls back to the OD plot's
        current zoom/pan view range so that zooming in still narrows the atom-number
        integration region.

        Args:
            od (numpy.ndarray): The OD array to crop

        Returns:
            tuple: (cropped_od, x_slice, y_slice) where slices indicate the cropping ranges
        """
        if self.viewer is None:
            return od, slice(None), slice(None)

        try:
            # --- Prefer drawn ROI rect over view range ---
            roi_rect = self.viewer.get_od_roi_rect()
            if roi_rect is not None:
                x_min = max(0, int(round(roi_rect[0])))
                y_min = max(0, int(round(roi_rect[1])))
                x_max = min(od.shape[1], int(round(roi_rect[2])))
                y_max = min(od.shape[0], int(round(roi_rect[3])))
                if x_max > x_min and y_max > y_min:
                    y_slice = slice(y_min, y_max)
                    x_slice = slice(x_min, x_max)
                    return od[y_slice, x_slice], x_slice, y_slice
                # drawn rect is degenerate — fall through to view range

            # Get the current view range from the viewer's OD plot
            x_range, y_range = self.viewer.get_od_view_range()

            # Convert view coordinates to array indices
            # Clamp to valid array bounds
            x_min = max(0, int(round(x_range[0])))
            x_max = min(od.shape[1], int(round(x_range[1])))
            y_min = max(0, int(round(y_range[0])))
            y_max = min(od.shape[0], int(round(y_range[1])))

            # Create slices for cropping
            y_slice = slice(y_min, y_max)
            x_slice = slice(x_min, x_max)

            # Crop the OD
            cropped_od = od[y_slice, x_slice]

            return cropped_od, x_slice, y_slice

        except Exception as e:
            # If anything goes wrong, return the original OD
            print(f"Warning: Could not crop OD to view range: {e}")
            return od, slice(None), slice(None)