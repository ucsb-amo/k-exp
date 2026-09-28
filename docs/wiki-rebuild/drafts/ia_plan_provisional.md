# Provisional IA plan (editor-in-chief, before reports). To be rewritten as wiki_ia_plan.md after Phase 2.

## Home (one screen)
One paragraph: the K machine, ARTIQ, three packages, two readers.
Five doors: Error-Message-Index · Troubleshooting · Demons · Words-You'll-See · Where-Does-X-Live
Three paths (5–8 pages each), ordered along the concept map:
A. Run the machine today: Operator-Cheat-Sheet → Starting-Up-the-Machine → Running-a-Standard-Experiment → Watching-a-Run-(LiveOD) → Controlling-Devices-Between-Runs → Finding-and-Viewing-Data → Recovering-From-Common-Problems
B. Write my first experiment: Words-You'll-See#code → Where-the-Code-Lives → Anatomy-of-an-Experiment → Parameters-and-Units → Scanning-Parameters → Devices-in-an-Experiment → Cameras-and-Imaging-in-an-Experiment → Saving-Extra-Data-(DataVault) → From-Run-ID-to-Plot
C. Maintain or extend the code: Package-Layering → Experiment-Lifecycle-Internals → Device-Layer-and-Adding-Hardware → Hardware-Drivers → Monitor-Internals → LiveOD-Internals → Data-File-Format → Calibrations → Tests-Profiling-and-Environment

## Sidebar (8 groups, doors pinned on top)
0 Lookup: the five doors + Operator cheat sheet
1 Start here: PC setup, Starting up, Running a standard experiment, Words You'll See
2 Running the machine: LiveOD, Device control (Monitor), Data browser/finding data, Recovering, Experiments catalog
3 Writing experiments: Anatomy, Parameters & units, Scanning, Devices in an experiment, Cameras & imaging, DataVault, Analysis worked example
4 Devices & control (reference): Device frames & config reference, Adding hardware, Composite devices, Drivers (AWG, SLM, coils, Raman, Rydberg, relay...), FFU
5 Cameras & imaging (reference): LiveOD internals, camera settings & overrides, SLM spot finder, Camera viewer
6 Data & analysis (reference): Data file format & run IDs, atomdata/fitting/plotting/slice, Climate, Units
7 Maintaining: Package layering & code map, lifecycle internals, Monitor internals, network & firewall, environment/venv, tests & profiling, Archaeology

## Merges/splits (provisional; reasons after audit)
- Standard-terminology + Unit-conventions(glossary parts) → Words-You'll-See (stub redirects)
- _Commonly-used-kexp-objects + Base-experiment-parent-class + Quick-Start → Anatomy-of-an-Experiment (tutorial) + Experiment-Lifecycle (explanation/reference)
- Device-Frames + _DDS-Objects + Device-configuration-reference → Device-Frames-and-Channel-Reference
- Saving-and-loading-data + Changing-data-directory + DataVault(file parts) → Data-Files-and-Run-IDs; DataVault stays (how-to)
- Monitor page (1021) → Controlling-Devices-Between-Runs (how-to) + Monitor-Internals (reference) + Composite-Tab (reference); troubleshooting rows → Troubleshooting
- LiveOD (525) → Watching-a-Run-(LiveOD) (how-to) + LiveOD-Internals (reference: protocol, run integrity, camera host)
- Scan-loop (657) → Scanning-Parameters (how-to) + Scanner-Internals (reference)
- Network-and-Firewall-Setup + Networking-intro: keep both (setup how-to; explanation), rename intro → Networking-for-Beginners
- Fast-DDS-freuqency-updates → Fast-DDS-Frequency-Updates-(FFU) with stub
- Numerology → Parameters-and-Units (with the Unit conventions reference)
- Placeholder-objects → Internals section of Devices-in-an-Experiment / Composite devices
- Repositories-and-design-philosophy → Package-Layering (k-amo/k-jam parts kept)
- Miscellaneous-Archaeology: keep; receives obsolete material
- Climate: keep, link from Data & analysis
