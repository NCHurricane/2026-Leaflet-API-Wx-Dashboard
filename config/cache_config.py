"""Cache serving policy shared by the frames endpoints.

After a server restart (or whenever workers have not caught up yet), the
frames endpoints serve disk-cached frames that fall just outside the
requested lookback window as immediate scrubber fill-ins — provided they are
within the per-source grace windows below — and refresh in the background
instead of blocking the request on a synchronous render.

Windows are minutes of staleness beyond the requested lookback that are still
worth showing, keyed per data source because update cadence differs.
"""

OVERLAY_STALE_SERVE_WINDOW_MIN = {
    "radar_live": 15,
    "mrms": 20,
    "rtma_rapid_update": 30,
    "rtma_hourly": 90,
}

# Frames rendered synchronously inside a request when the cache is empty, so
# the first paint is not blank. The rest of the window fills in a background
# thread and the frontend's history polling picks the frames up as they land.
OVERLAY_EMPTY_CACHE_SYNC_FRAMES = 3
