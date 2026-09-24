"""kexp.control.opx -- Quantum Machines OPX+ program builder.

Layout mirrors the eventual waxx/kexp split (same playbook as liveOD):

    generic (no kexp config, qm imported lazily inside functions):
        manager.py, builder.py, context.py, params_bridge.py, sequence.py,
        channels.py, units.py
    kexp-specific (ports, element names, ExptParams/dds wiring):
        opx_config.py

Importing this package (or kexp itself) never imports qm-qua: the modules
only touch qm inside method bodies. Analysis machines and loky workers need
no qm install.

Usage in an experiment:

    from kexp.experiments.opx_sequences.rabi import rabi_raman_pulse

    def prepare(self):
        Base.__init__(self, ...)
        self.xvar('t_raman_pulse', np.linspace(0., 30.e-6, 15))
        self.opx.use(rabi_raman_pulse)     # before finish_prepare
        self.finish_prepare(shuffle=True)
"""

# Plain imports on purpose: none of these modules import qm at module level
# (qm only loads inside method bodies), so this stays qm-free AND static
# analysis (Pylance/jedi) sees every name for highlighting and completion.
from kexp.control.opx.manager import OPXManager
from kexp.control.opx.builder import OPXProgramBuilder
from kexp.control.opx.context import OPXShotContext
from kexp.control.opx.sequence import OPXSequence, opx_sequence, get_sequence
from kexp.control.opx.channels import ChannelMap, ChannelSpec
from kexp.control.opx.params_bridge import (build_shot_tables, ShotTables,
                                            ParamRef)
from kexp.control.opx.opx_config import (make_opx_manager, build_opx_config,
                                         kexp_channel_map, KexpShotContext)
from kexp.control.opx.bench import OPXBench

__all__ = [
    'OPXManager', 'OPXProgramBuilder', 'OPXShotContext',
    'OPXSequence', 'opx_sequence', 'get_sequence',
    'ChannelMap', 'ChannelSpec',
    'build_shot_tables', 'ShotTables', 'ParamRef',
    'make_opx_manager', 'build_opx_config', 'kexp_channel_map',
    'KexpShotContext',
    'OPXBench',
]
