<#
.SYNOPSIS
    Preview or manage optional dashboard cache-warmer tasks.

.DESCRIPTION
    The dashboard requires no Windows scheduled tasks. Application requests,
    refresh coordination, current-season Tropical refresh, and cache cleanup
    are owned by the running FastAPI process.

    With no mutation switches this script only lists existing Wx-Dashboard-*
    tasks and previews the bounded optional-warmer profiles. Optional warmers
    call the running localhost API; they never launch legacy direct-writing
    workers.

.PARAMETER Profile
    Optional warmer profiles to preview or register. Defaults to core and
    surface; rtma and mrms must be selected explicitly.

.PARAMETER InstallOptionalWarmers
    Register the selected optional-warmer profiles. New tasks are disabled
    unless EnableOptionalWarmers is also supplied.

.PARAMETER EnableOptionalWarmers
    Enable newly registered optional-warmer tasks.

.PARAMETER UnregisterLegacyTasks
    Explicitly unregister known legacy direct-writer tasks after listing them.
    This is an operator-authorized migration action and is never implied by
    preview or installation.

.EXAMPLE
    pwsh -File tools\install_tasks.ps1

.EXAMPLE
    pwsh -File tools\install_tasks.ps1 -InstallOptionalWarmers

.EXAMPLE
    pwsh -File tools\install_tasks.ps1 -InstallOptionalWarmers -EnableOptionalWarmers

.EXAMPLE
    pwsh -File tools\install_tasks.ps1 -Profile rtma,mrms -InstallOptionalWarmers
#>

[CmdletBinding()]
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [ValidateSet('core', 'surface', 'rtma', 'mrms')]
    [string[]]$Profile = @('core', 'surface'),
    [string]$ApiBaseUrl = 'http://127.0.0.1:8000',
    [switch]$InstallOptionalWarmers,
    [switch]$EnableOptionalWarmers,
    [switch]$UnregisterLegacyTasks
)

$ErrorActionPreference = 'Stop'
$TaskPrefix = 'Wx-Dashboard-'
$Pythonw = Join-Path $ProjectRoot '.venv\Scripts\pythonw.exe'
$LegacyTaskNames = @(
    'Wx-Dashboard-Alerts',
    'Wx-Dashboard-MRMS',
    'Wx-Dashboard-Radar-Live',
    'Wx-Dashboard-RTMA',
    'Wx-Dashboard-RTMA-RU',
    'Wx-Dashboard-Satellite_v2_meteosat_prefetch',
    'Wx-Dashboard-Satellite_v2_rapid',
    'Wx-Dashboard-SPC',
    'Wx-Dashboard-Surface',
    'Wx-Dashboard-Tropical',
    'Wx-Dashboard-Tropical-Archive',
    'Wx-Dashboard-Water-Riv-Gauges',
    'Wx-Dashboard-WPC'
)
$ProfileIntervals = @{
    core = 5
    surface = 30
    rtma = 15
    mrms = 5
}

if ($EnableOptionalWarmers -and -not $InstallOptionalWarmers) {
    throw '-EnableOptionalWarmers requires -InstallOptionalWarmers.'
}

Write-Host 'Dashboard task mode: optional warmers only; no task is required.'
Write-Host "Project root       : $ProjectRoot"
Write-Host "Application API    : $ApiBaseUrl"
Write-Host ''
Write-Host 'Existing Wx-Dashboard-* tasks:'
$ExistingTasks = @(Get-ScheduledTask -TaskName "$TaskPrefix*" -ErrorAction SilentlyContinue)
if ($ExistingTasks.Count -eq 0) {
    Write-Host '  (none)'
} else {
    $ExistingTasks |
        Select-Object TaskName, State, TaskPath |
        Sort-Object TaskName |
        Format-Table -AutoSize
}

Write-Host 'Optional-warmer preview:'
foreach ($profileName in $Profile) {
    $taskName = "$TaskPrefix" + 'Optional-Warmer-' + (
        (Get-Culture).TextInfo.ToTitleCase($profileName)
    )
    $enabled = if ($EnableOptionalWarmers) { 'enabled' } else { 'disabled' }
    Write-Host (
        '  {0,-45} every {1,3} min [{2}] -> API profile {3}' -f
        $taskName, $ProfileIntervals[$profileName], $enabled, $profileName
    )
}

if (-not $InstallOptionalWarmers -and -not $UnregisterLegacyTasks) {
    Write-Host ''
    Write-Host 'Preview only. No scheduled tasks were changed.'
    exit 0
}

if ($InstallOptionalWarmers) {
    if (-not (Test-Path $Pythonw)) {
        throw "pythonw.exe not found at '$Pythonw'. Create the venv first or pass -ProjectRoot."
    }
    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive `
        -RunLevel Limited
    $baseStart = (Get-Date).Date

    foreach ($profileName in $Profile) {
        $taskName = "$TaskPrefix" + 'Optional-Warmer-' + (
            (Get-Culture).TextInfo.ToTitleCase($profileName)
        )
        $arguments = (
            '-u -m workers.optional_warmer --profile {0} --base-url "{1}" --log-to-file' -f
            $profileName, $ApiBaseUrl
        )
        $action = New-ScheduledTaskAction `
            -Execute $Pythonw `
            -Argument $arguments `
            -WorkingDirectory $ProjectRoot
        $trigger = New-ScheduledTaskTrigger `
            -Once `
            -At $baseStart `
            -RepetitionInterval (New-TimeSpan -Minutes $ProfileIntervals[$profileName]) `
            -RepetitionDuration (New-TimeSpan -Days 3650)
        $settings = New-ScheduledTaskSettingsSet `
            -MultipleInstances IgnoreNew `
            -StartWhenAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
        $settings.Enabled = [bool]$EnableOptionalWarmers

        Register-ScheduledTask `
            -TaskName $taskName `
            -Action $action `
            -Trigger $trigger `
            -Principal $principal `
            -Settings $settings `
            -Force | Out-Null
        Write-Host "Registered optional warmer: $taskName"
    }
}

if ($UnregisterLegacyTasks) {
    Write-Host ''
    Write-Host 'Removing explicitly authorized legacy direct-writer tasks:'
    foreach ($taskName in $LegacyTaskNames) {
        if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
            Write-Host "  Removed $taskName"
        }
    }
}
