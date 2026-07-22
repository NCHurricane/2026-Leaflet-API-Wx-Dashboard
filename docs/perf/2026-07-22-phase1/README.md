# Satellite v2 Phase 1 results

Phase 1 fixes the NetCDF dataset LRU, replaces full PNG decoding on normal
cache hits with a size/signature check, and avoids lon/lat mesh allocation for
composites that do not consume geographic geometry.

- The four affected GOES cold-parse rows passed the Phase 0 golden comparison
  after the isolated LRU change.
- The final warm-parse matrix passed all 81 byte-exact golden comparisons.
- The final hit matrix contains five samples for each of the nine pinned rows.
- Raw run files remain under ignored `cache/satellite/.bench/`; this directory
  keeps only the compact committed results and reproducibility manifest.

