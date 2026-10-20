"""Gap-aware replay: FeedbackReplay that takes each shot's inter-pulse gaps from data.dT_mu.

Runs taken with FeedbackExptAlt (expts/base_expt_feedback_alt.py) record the gap actually used
after every pulse. The stock FeedbackReplayCore reconstructs gaps as 'constant base + drawn pulse
time', validated only at the nominal pulse, so it would replay such runs on the wrong timeline
without noticing. This subclass prefers the recorded container and falls back to the stock
reconstruction for runs without it (then it is the stock replay, bit for bit).
"""
import numpy as np

from kexp.analysis import FeedbackReplay


class FeedbackReplayGaps(FeedbackReplay):

    def _compute_dT_rr_mu(self, t_raman_pulse_rr):
        ad = getattr(self, "ad", None)
        data = getattr(ad, "data", None)
        if data is not None and "dT_mu" in list(getattr(data, "keys", [])):
            rec = np.asarray(getattr(data, "dT_mu"), dtype=float)
            shape = np.asarray(t_raman_pulse_rr).shape
            rec = rec.reshape(-1, rec.shape[-1])
            if rec.shape == shape and np.all(np.isfinite(rec)) and np.all(rec > 0):
                self.dT_source = "data.dT_mu"
                return np.rint(rec).astype(np.int64)
        self.dT_source = "reconstructed"
        return super()._compute_dT_rr_mu(t_raman_pulse_rr)
