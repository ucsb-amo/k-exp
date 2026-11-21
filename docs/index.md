# kexp

Control and experiment code for the Weld Lab potassium machine, built on ARTIQ.

kexp is the machine-specific layer of a small stack of packages:

| Package | Role | Documentation |
|---|---|---|
| `kexp` | The K machine: device configuration, sequences, experiments, calibrations | this site |
| `waxx` | ARTIQ control and scan framework, liveOD, the run queue | [wax](https://ucsb-amo.github.io/wax/) |
| `waxa` | Analysis: loading runs, fitting, plotting | [wax](https://ucsb-amo.github.io/wax/) |

`kexp` imports `waxx`, and `waxx` imports `waxa`, never the other way round.

## Guides

The how-to and reference pages currently live in the
[k-exp wiki](https://github.com/ucsb-amo/k-exp/wiki).

## Contents

```{toctree}
:maxdepth: 2

API reference <api/kexp/index>
Module index <modindex>
General index <genindex>
building-the-docs
```
