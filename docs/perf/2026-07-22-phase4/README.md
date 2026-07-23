# Satellite v2 Phase 4 results

Phase 4 adds a shared, byte-budgeted `SourceRaster` LRU beneath the existing
renderer cache. The default budget is 4096 MB and can be overridden with
`WX_SATELLITE_V2_SOURCE_RASTER_CACHE_MB`; zero disables it.

Source eviction removes renderer entries that retain the evicted raster, so
inactive renderer references cannot bypass byte accounting. Raw benchmark files
remain under ignored `cache/satellite/.bench/`; this directory contains only
compact committed evidence.
