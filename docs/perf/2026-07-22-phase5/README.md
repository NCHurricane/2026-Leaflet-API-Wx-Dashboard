# Satellite v2 Phase 5 results

Phase 5 reuses one `ProcessPoolExecutor` across an entire rapid-worker run and
skips the trailing catalog rebuild when a job rendered no tiles and had no
errors. Other callers retain the original owned-pool behavior by default.

Raw probe and golden files remain under ignored `cache/satellite/.bench/`; this
directory contains only compact committed evidence.
