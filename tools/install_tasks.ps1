<#
.SYNOPSIS
    Registers Windows Scheduled Tasks that keep the dashboard's data caches
    perpetually warm so the FastAPI server starts with hot data.

.DESCRIPTION
    Creates one task per data worker (alerts, SPC, surface, MRMS, RTMA hourly,
    RTMA rapid-update) plus a
    weekly NWS zone-geometry preseed task. All tasks:
      - Run as the current user, only when logged on.
      - Use the project's venv Python explicitly.
      - Set working directory to the project root.
      - Refuse to start a new instance if a previous run is still going.
      - Stop after 10 minutes if hung.
      - Log stdout/stderr to logs\scheduled\<task>.log (appended).

    The in-process APScheduler still runs as a fallback. Both schedulers use
    a shared sentinel-file freshness gate (see workers\_freshness.py), so
    whichever fires first refreshes the cache and the other exits immediately.

.PARAMETER PythonExe
    Optional override for the Python interpreter path. Defaults to the
    project venv: <repo>\.venv\Scripts\python.exe.

.EXAMPLE
    pwsh tools\install_tasks.ps1

.EXAMPLE
    pwsh tools\install_tasks.ps1 -PythonExe "C:\Python312\python.exe"
#>

[CmdletBinding()]
param(
    [string]$PythonExe
)

$ErrorActionPreference = 'Stop'

# Resolve repo root (parent of tools/)
$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $RepoRoot 'logs\scheduled'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

if (-not $PythonExe) {
    # Use pythonw.exe — no console window, ever. Required to avoid popups
    # over the dashboard during livestream.
    $PythonExe = Join-Path $RepoRoot '.venv\Scripts\pythonw.exe'
}
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "pythonw.exe not found: $PythonExe (the venv must include pythonw.exe to run silently)"
}

Write-Host "Repo root  : $RepoRoot"
Write-Host "Python exe : $PythonExe"
Write-Host "Log folder : $LogDir"
Write-Host ""

# Each task definition. Times use ISO 8601 / ScheduledTask cmdlet conventions.
$tasks = @(
    @{
        Name        = 'Wx-Dashboard-Alerts'
        Description = 'Refresh national NWS alerts cache (cache/alerts/).'
        Module      = 'workers.alerts_worker'
        Trigger     = 'minutes-1'
    },
    @{
        Name        = 'Wx-Dashboard-SPC'
        Description = 'Refresh SPC outlook cache (cache/spc/).'
        Module      = 'workers.spc_worker'
        Trigger     = 'minutes-30'
    },
    @{
        Name        = 'Wx-Dashboard-Surface'
        Description = 'Refresh METAR surface obs cache.'
        Module      = 'workers.surface_worker'
        Trigger     = 'minutes-30'
    },
    @{
        Name        = 'Wx-Dashboard-MRMS'
        Description = 'Refresh MRMS GRIB2 cache (cache/mrms/<active product>).'
        Module      = 'workers.mrms_worker'
        Trigger     = 'minutes-15'
    },
    @{
        Name        = 'Wx-Dashboard-RTMA'
        Description = 'Refresh RTMA Hourly city-point/overlay cache (cache/rtma/*).'
        Module      = 'workers.rtma_hourly_worker'
        Trigger     = 'hourly-at-5'
    },
    @{
        Name        = 'Wx-Dashboard-RTMA-RU'
        Description = 'Refresh RTMA Rapid Update city-point/overlay cache (cache/rtma/*).'
        Module      = 'workers.rtma_rapid_worker'
        Trigger     = 'minutes-15-at-20'
    },
    @{
        Name        = 'Wx-Dashboard-ZonePreseed'
        Description = 'Weekly preseed of NWS zone-geometry disk cache.'
        Script      = 'tools\preseed_zone_cache.py'
        Trigger     = 'weekly-sunday-0300'
    }
)

function New-IntervalTrigger {
    param(
        [Parameter(Mandatory)] [int]$Minutes,
        [int]$StartMinute = 0
    )
    # Repeat forever from a wall-clock anchored minute (e.g., :05, :20).
    $now = Get-Date
    $start = Get-Date -Year $now.Year -Month $now.Month -Day $now.Day `
        -Hour $now.Hour -Minute $StartMinute -Second 0
    while ($start -le $now) {
        $start = $start.AddMinutes($Minutes)
    }

    $trigger = New-ScheduledTaskTrigger -Once -At $start `
        -RepetitionInterval (New-TimeSpan -Minutes $Minutes) `
        -RepetitionDuration ([TimeSpan]::FromDays(3650))
    return ,$trigger
}

function New-WeeklyTrigger {
    param(
        [Parameter(Mandatory)] [string]$DayOfWeek,
        [Parameter(Mandatory)] [string]$AtTime
    )
    return New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $AtTime
}

foreach ($t in $tasks) {
    $name = $t.Name

    # Build the Python argument string. Each task launches pythonw.exe
    # directly (no PowerShell wrapper), so there is no console window. The
    # worker handles its own stdout/stderr redirection via --log-to-file,
    # writing to logs\scheduled\<name>.log.
    if ($t.Module) {
        $pyArgs = "-u -m $($t.Module) --log-to-file"
    }
    else {
        $scriptPath = Join-Path $RepoRoot $t.Script
        $pyArgs = "-u `"$scriptPath`" --log-to-file"
    }

    $action = New-ScheduledTaskAction `
        -Execute $PythonExe `
        -Argument $pyArgs `
        -WorkingDirectory $RepoRoot

    switch -Regex ($t.Trigger) {
        '^minutes-(\d+)$' {
            $trigger = New-IntervalTrigger -Minutes ([int]$Matches[1])
            break
        }
        '^minutes-(\d+)-at-(\d{1,2})$' {
            $trigger = New-IntervalTrigger -Minutes ([int]$Matches[1]) -StartMinute ([int]$Matches[2])
            break
        }
        '^hourly-at-(\d{1,2})$' {
            $trigger = New-IntervalTrigger -Minutes 60 -StartMinute ([int]$Matches[1])
            break
        }
        '^weekly-(\w+)-(\d{4})$' {
            $day = $Matches[1].Substring(0,1).ToUpper() + $Matches[1].Substring(1)
            $hh = $Matches[2].Substring(0,2)
            $mm = $Matches[2].Substring(2,2)
            $trigger = New-WeeklyTrigger -DayOfWeek $day -AtTime "$hh`:$mm"
            break
        }
        default {
            throw "Unknown trigger spec: $($t.Trigger)"
        }
    }

    $settings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
        -StartWhenAvailable `
        -DontStopOnIdleEnd `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries

    # Run as the current user, only when logged on (interactive token).
    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Limited

    Write-Host ("[+] Registering {0,-30} -> {1}" -f $name, $pyArgs)

    # Replace any prior version atomically.
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    }

    Register-ScheduledTask `
        -TaskName $name `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $t.Description | Out-Null
}

Write-Host ""
Write-Host "All tasks registered. View in Task Scheduler under 'Task Scheduler Library'."
Write-Host "Logs will appear in: $LogDir"
