$ErrorActionPreference = "Stop"

$Python = "C:\Users\harsh\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$BotUrl = "http://127.0.0.1:8080/v1/healthz"

if (-not (Test-Path $Python)) {
    Write-Error "Bundled Python was not found at $Python. Open Codex once more or install Python from python.org."
}

function Test-BotHealth {
    try {
        $response = Invoke-RestMethod -Uri $BotUrl -Method GET -TimeoutSec 2
        return $response.status -eq "ok"
    } catch {
        return $false
    }
}

if (-not (Test-BotHealth)) {
    Write-Host "Bot server is not running. Starting it on http://127.0.0.1:8080 ..."
    Start-Process -FilePath $Python -ArgumentList "`"$PSScriptRoot\bot.py`"" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden | Out-Null

    $ready = $false
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-BotHealth) {
            $ready = $true
            break
        }
    }

    if (-not $ready) {
        Write-Error "Bot server did not start. Try running .\run_bot.ps1 in a separate PowerShell window."
    }
}

& $Python "$PSScriptRoot\test_api_flow.py"
