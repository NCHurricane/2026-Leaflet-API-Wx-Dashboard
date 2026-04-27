# Session Summary — 2026-04-23

## Theme

Migrated background data fetching from in-process APScheduler to Windows
Task Scheduler ("OS-only" mode), eliminated console popups during livestream,
and tightened the alerts polling cadence to ~30s end-to-end.

---

## Key Decisions

1. **OS-only fetching is the default.** In-process APScheduler is now opt-in
   via `WX_INPROC_WORKERS=1` so OS tasks and in-process jobs do not race and
   spam "Cache fresh — skipping" lines.
2. **`pythonw.exe` instead of `powershell.exe + python.exe`** for all
   scheduled tasks — no console window, ever (livestream-safe).
3. **Workers self-redirect stdio** to `logs/scheduled/<name>.log` via
   `--log-to-file` so we don't need PowerShell wrappers for log capture.
4. **30s alerts cadence** is the practical floor (NWS api.weather.gov caches
   ~30s upstream). Achieved by running two staggered Task Scheduler entries
   1 minute apart, offset by 30s.

---

## Files Changed

### Backend / scheduler

- **`workers/_freshness.py`**
  - Added `redirect_stdio_to_log(name)` — replaces `sys.stdout` / `sys.stderr`
    with a line-buffered append-mode file handle at
    `logs/scheduled/<name>.log`.
  - Added `check_cache_freshness()` startup health check.
  - `_HEALTH_THRESHOLDS = {"alerts": 5*60, "spc": 60*60, "surface": 60*60}`,
    `_MRMS_THRESHOLD = 30*60`.
- **`workers/scheduler.py`**
  - In-process scheduler now gated:
    ```python
    _INPROC_ENABLED = os.environ.get("WX_INPROC_WORKERS", "").strip().lower() \
                      in ("1", "true", "yes", "on")
    ```
  - `start_scheduler()` returns early printing
    `[scheduler] In-process workers disabled (default)...` unless the env var
    is set.
  - `stop_scheduler()` guarded by `if _scheduler.running`.
- **`workers/alerts_worker.py`**
  - **`_FRESH_WINDOW_SEC` lowered to `20`** (from `45`) so the staggered
    `-B` task at +30s actually fetches instead of always seeing a fresh
    sentinel from `-A`.
- **`workers/{alerts,spc,surface,mrms}_worker.py`** and
  **`tools/preseed_zone_cache.py`**
  - All have `__main__` argparse blocks with `--force` (where applicable),
    `--product` (mrms), and `--log-to-file`.
  - When `--log-to-file` is set:
    `from workers._freshness import redirect_stdio_to_log; redirect_stdio_to_log("<name>")`.
- **`main.py`**
  - Step 10: cache freshness health check after `start_scheduler()`. Prints
    `[WARN]` lines per stale cache and emits either
    `[OK] All caches fresh (OS task healthy)` or
    `[WARN] N cache freshness issue(s)`.
  - Startup time dropped from ~100s to **0.03s** because workers no longer
    run in-process at boot.

### Task Scheduler

- **`tools/install_tasks.ps1`**
  - Default `$PythonExe` is now `<repo>\.venv\Scripts\pythonw.exe` (throws if
    missing).
  - Action:
    `New-ScheduledTaskAction -Execute $PythonExe -Argument "-u -m <module> --log-to-file" -WorkingDirectory $RepoRoot`
  - Five tasks installed:
    | Task | Trigger |
    | ---- | ------- |
    | `Wx-Dashboard-Alerts` | every 1 min (later replaced by `-A`/`-B` pair) |
    | `Wx-Dashboard-SPC` | every 30 min |
    | `Wx-Dashboard-Surface` | every 30 min |
    | `Wx-Dashboard-MRMS` | every 15 min |
    | `Wx-Dashboard-ZonePreseed` | weekly Sunday 03:00 |
  - All tasks: `LogonType Interactive`, `RunLevel Limited`, runs as
    `$env:USERNAME`, `MultipleInstances IgnoreNew`,
    `ExecutionTimeLimit 10 minutes`.

### Alerts staggered pair (manual install, not in `install_tasks.ps1` yet)

- Deleted `Wx-Dashboard-Alerts`.
- Registered `Wx-Dashboard-Alerts-A` (start :00) and
  `Wx-Dashboard-Alerts-B` (start :30), both repeating every 1 min →
  net 30s cadence.
- Snippet for re-registering both tasks with a clean minute-anchored offset
  is in this session's chat history.

### Frontend

- **`js/weather.js`** (around line 5400)
  - `ALERTS_AUTO_REFRESH_MS` raised from `15_000` to `30_000` to match the
    backend cadence (no more wasted requests against the upstream 30s cache).
  - Comment updated: "Auto-refresh alerts every 30s to match the OS-task
    backend cadence".

---

## Verification Recipes

```powershell
# Are both alerts tasks registered and on schedule?
Get-ScheduledTask Wx-Dashboard-Alerts-* |
    Get-ScheduledTaskInfo |
    Select-Object TaskName, LastRunTime, NextRunTime, LastTaskResult

# Live-tail the alerts log
Get-Content .\logs\scheduled\alerts.log -Wait -Tail 20

# Confirm cache file actually updates every ~30s
while ($true) { (Get-Item .\cache\alerts\national_full.geojson).LastWriteTime; Start-Sleep 10 }
```

Notes:

- `LastTaskResult = 267011` (0x41303) means "task has not yet run". Normal
  before first trigger.
- `LastRunTime = 11/30/1999 12:00:00 AM` is the placeholder for "never".
- `LastTaskResult = 0` after a successful run.
- Healthy log entry looks like:
  `[alerts_worker] Complete in 19.65s ... Features: 400 total`
- "Cache fresh — skipping run" every other tick = `_FRESH_WINDOW_SEC` is
  still too high relative to the cadence; lower it.

---

## Operational Notes for Future Sessions

- **Do not re-enable in-process workers** unless explicitly debugging. The
  OS tasks are the source of truth.
- **NWS upstream caches `api.weather.gov` alerts ~30s.** Polling faster than
  30s wastes calls and gives no fresher data.
- **Task Scheduler's hard floor is 1-minute repetition.** Sub-minute cadences
  require either staggered duplicate tasks (current approach for alerts) or
  a long-running loop-in-worker mode.
- **`pythonw.exe` is mandatory** for any scheduled task that runs while a
  user is logged on and presenting/livestreaming. `python.exe` will flash a
  console window each tick.
- **The freshness gate is shared** between in-process and OS schedulers via
  sentinel files at `cache/.workers/<name>.last_run`. If you change cadence,
  also re-tune `_FRESH_WINDOW_SEC` in the relevant worker.
