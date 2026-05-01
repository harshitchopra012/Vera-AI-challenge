$ErrorActionPreference = "Stop"

$Python = "C:\Users\harsh\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$HealthUrl = "http://127.0.0.1:8080/v1/healthz"

if (-not (Test-Path $Python)) {
    Write-Error "Bundled Python was not found at $Python. Open Codex once more or install Python from python.org."
}

function Test-BotHealth {
    try {
        $response = Invoke-RestMethod -Uri $HealthUrl -Method GET -TimeoutSec 2
        return $response.status -eq "ok"
    } catch {
        return $false
    }
}

if (-not (Test-BotHealth)) {
    Write-Host "Starting Vera bot on http://127.0.0.1:8080 ..."
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
        Write-Error "Bot server did not start. Try running .\run_bot.ps1 first."
    }
}

$Npx = "C:\Program Files\nodejs\npx.cmd"
if (-not (Test-Path $Npx)) {
    Write-Error "npx was not found. Install Node.js or use ngrok/cloudflared manually."
}

Write-Host ""
Write-Host "Opening a public tunnel to http://127.0.0.1:8080"
Write-Host "If localtunnel prints a password/IP warning, follow its instruction in the browser."
Write-Host "Submit the printed https://... URL as your base URL, without /v1/healthz."
Write-Host "Keep this PowerShell window open while the judge tests your bot."
Write-Host ""

& $Npx --yes localtunnel --port 8080
