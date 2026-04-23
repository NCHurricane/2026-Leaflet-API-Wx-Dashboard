<#
.SYNOPSIS
    Removes the Wx-Dashboard scheduled tasks created by install_tasks.ps1.

.DESCRIPTION
    Unregisters every scheduled task whose name begins with "Wx-Dashboard-".
    Leaves logs/scheduled/ in place so historical output is preserved.

.EXAMPLE
    pwsh tools\uninstall_tasks.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$tasks = Get-ScheduledTask -TaskName 'Wx-Dashboard-*' -ErrorAction SilentlyContinue
if (-not $tasks) {
    Write-Host "No Wx-Dashboard-* tasks are currently registered. Nothing to do."
    return
}

foreach ($task in $tasks) {
    Write-Host ("[-] Removing {0}" -f $task.TaskName)
    Unregister-ScheduledTask -TaskName $task.TaskName -Confirm:$false
}

Write-Host ""
Write-Host "Done. Logs preserved under logs\scheduled\."
