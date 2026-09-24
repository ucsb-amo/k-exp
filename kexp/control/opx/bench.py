"""OPXBench -- drive the OPX interactively (Jupyter) with kexp defaults.

Stands in for a prepared experiment: real kexp ExptParams, the real dds
frame defaults (so the OPX config is exactly what a run would compile), an
xvar interface for scans -- but no ARTIQ, no liveOD, no run id, nothing
saved. Meant for iterating on sequences in kexp/experiments/opx_sequences/
from a notebook:

    import numpy as np
    from kexp.control.opx import OPXBench
    from kexp.experiments.opx_sequences.rabi import rabi_raman_pulse

    bench = OPXBench()
    bench.xvar('t_raman_pulse', np.linspace(0., 30.e-6, 15))
    job = bench.simulate(rabi_raman_pulse, shots=2)   # pulse viewer opens

    print(bench.qua_source)                # the full (real) program text
    samples = job.get_simulated_samples()  # dig into the traces yourself

Every simulate() call starts fresh (new manager, new DataVault), so it can
be re-run cell-by-cell while editing a sequence. Xvar values run in the
order given -- no shuffle, no repeats -- so shot k of the simulation is
values[k], deterministically.

kexp-specific (imports the lab config); the machinery it drives is the
same manager/builder an experiment uses.
"""

import numpy as np
from types import SimpleNamespace
from typing import TYPE_CHECKING, Optional

from waxa.base.xvar import xvar as _xvar
from waxx.config.data_vault import DataVault

from kexp.control.opx.manager import OPXManager

if TYPE_CHECKING:
    # static-analysis only: keeps qm (and the heavier kexp config modules)
    # out of the import chain while giving completion on the annotations
    from qm.jobs.simulated_job import SimulatedJob
    from kexp.config.expt_params import ExptParams
    from kexp.config.dds_id import dds_frame


class OPXBench:

    def __init__(self, expt_params=None):
        from kexp.config.expt_params import ExptParams
        from kexp.config.dds_id import dds_frame

        self.params: 'ExptParams' = (expt_params if expt_params is not None
                                     else ExptParams())
        self.p: 'ExptParams' = self.params
        self.dds: 'dds_frame' = dds_frame(expt_params=self.params)

        self.scan_xvars = []
        self.xvardims = []
        self.run_info = SimpleNamespace(save_data=False)

        self.data = DataVault(expt=self)
        self._extra_file_texts = {}
        self.opx: OPXManager = self._fresh_manager()

    def _fresh_manager(self) -> OPXManager:
        from kexp.control.opx.opx_config import make_opx_manager
        opx = make_opx_manager(self)
        opx._exit_after_simulate = False   # a notebook cell must survive
        return opx

    def compute_new_derived(self):
        pass

    def xvar(self, key, values):
        """Declare a scanned parameter, exactly as in an experiment's
        prepare() -- except values run in the order given (no shuffle, no
        repeats). Re-declaring a key replaces its values."""
        values = np.atleast_1d(np.asarray(values, dtype=float))
        self.scan_xvars = [xv for xv in self.scan_xvars if xv.key != key]
        self.scan_xvars.append(_xvar(key, values,
                                     position=len(self.scan_xvars)))
        for i, xv in enumerate(self.scan_xvars):
            xv.position = i
        vars(self.params)[key] = values[0]
        self.xvardims = [len(xv.values) for xv in self.scan_xvars]

    def simulate(self, sequence, duration=200.e-6, shots=1, viewer=True,
                 web_plot=None) -> 'Optional[SimulatedJob]':
        """Build the program for `sequence` and run the QOP simulator
        (needs the OPX reachable on the lab network). Returns the
        simulation job.

        shots: how many scheduled shots to simulate (0 = the whole scan);
        duration: simulated OPX timeline (SI seconds).

        viewer=True (default): open the interactive pulse viewer on the
        result -- a separate window; re-running simulate() updates it in
        place. The QM waveform report (browser plot) is then suppressed:
        web_plot=True forces it as well, web_plot=False skips it, None
        (default) means "only when the viewer is off".
        """
        # fresh state so this can be called repeatedly while iterating
        self.data = DataVault(expt=self)
        self._extra_file_texts = {}
        self.opx = self._fresh_manager()

        self.opx.use(sequence, simulate=True, simulate_duration=duration,
                     simulate_shots=shots, simulate_web_plot=web_plot,
                     simulate_viewer=viewer)
        self.opx.on_finish_prepare()
        return self.opx.sim_job

    def view(self, inline=False):
        """Re-open the pulse viewer on the last simulate() (after closing
        the window, or with viewer=False). inline=True builds it in this
        process, which needs a running Qt event loop (``%gui qt``)."""
        return self.opx.open_viewer(inline=inline)

    @property
    def viewer_bundle(self):
        """The seqview bundle of the last simulate() (None before one)."""
        return self.opx.viewer_bundle

    @property
    def qua_source(self) -> str:
        """The generated (real, triggered) QUA program text from the last
        simulate() -- what a run would save as provenance."""
        return self._extra_file_texts.get('opx_qua_program', '')
