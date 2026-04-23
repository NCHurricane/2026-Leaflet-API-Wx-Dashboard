<#
.SYNOPSIS
    Registers Windows Scheduled Tasks that keep the dashboard's data caches
    perpetually warm so the FastAPI server starts with hot data.

.DESCRIPTION
    Creates one task per data worker (alerts, SPC, surface, MRMS) plus a
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
    $PythonExe = Join-Path $RepoRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python executable not found: $PythonExe"
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
        Name        = 'Wx-Dashboard-ZonePreseed'
        Description = 'Weekly preseed of NWS zone-geometry disk cache.'
        Script      = 'tools\preseed_zone_cache.py'
        Trigger     = 'weekly-sunday-0300'
    }
)

function New-IntervalTrigger {
    param(
        [Parameter(Mandatory)] [int]$Minutes
    )
    # Repeat the trigger forever, starting now. Daily-at-startup so reboots
    # also kick off the cycle without waiting for the next interval.
    $start = (Get-Date).AddMinutes(1)
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
    $logFile = Join-Path $LogDir "$name.log"

    if ($t.Module) {
        $argLine = "-m $($t.Module)"
    }
    else {
        $argLine = "`"$(Join-Path $RepoRoot $t.Script)`""
    }

    # PowerShell wrapper: cd to repo, append timestamped header, run python.
    # Append both stdout and stderr to the per-task log.
    $cmdLine = "& `"$PythonExe`" $argLine *>> `"$logFile`""
    $wrapper = "Set-Location -LiteralPath `"$RepoRoot`"; " +
               "Add-Content -Path `"$logFile`" -Value (`"`n=== `" + (Get-Date -Format 's') + `" $name ===`"); " +
               "$cmdLine"

    $action = New-ScheduledTaskAction `
        -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"$wrapper`"" `
        -WorkingDirectory $RepoRoot

    switch -Regex ($t.Trigger) {
        '^minutes-(\d+)$' {
            $trigger = New-IntervalTrigger -Minutes ([int]$Matches[1])
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

    Write-Host ("[+] Registering {0,-30} -> {1}" -f $name, $argLine)

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
