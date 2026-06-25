# Launch the standalone radar palette preview app on http://127.0.0.1:8050
# Run from anywhere: powershell -ExecutionPolicy Bypass -File pal_preview\run.ps1
$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
Push-Location $PSScriptRoot
try {
    & $python -m uvicorn app:app --host 127.0.0.1 --port 8050 --reload
}
finally {
    Pop-Location
}
