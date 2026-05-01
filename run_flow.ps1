$ErrorActionPreference = "Stop"

$Python = "C:\Users\harsh\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Bundled Python was not found at $Python. Open Codex once more or install Python from python.org."
}

& $Python "$PSScriptRoot\demo_flow.py"
