# Satellite v2 Phase 3 results

Phase 3 reduces source parsing cost without changing calibrated pixels:

- FCI multi-channel products open each body chunk once and extract all required
  channels while preserving per-channel native grid state.
- AHI reads/decompresses/calibrates segments with a four-thread internal pool
  and retains only decimated calibrated strips, rather than all full segment
  buffers through the stitching phase.

Raw benchmark files remain under ignored `cache/satellite/.bench/`; this
directory contains only compact committed evidence.

