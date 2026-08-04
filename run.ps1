<#
.SYNOPSIS
Starts FORGE.

.DESCRIPTION
By default runs the API (uvicorn, with reload) and the Vite dev server together
and opens the browser. With -Prod it builds the frontend and serves everything
from the API process on a single port.

Press Ctrl+C to stop; both processes are shut down together.

.PARAMETER Prod
Build the frontend and serve it from FastAPI on one port.

.PARAMETER Port
API port (default 8000).

.PARAMETER FrontendPort
Vite dev server port (default 5173). Ignored with -Prod.

.PARAMETER NoBrowser
Do not open a browser window.

.EXAMPLE
.\run.ps1

.EXAMPLE
.\run.ps1 -Prod -Port 8080
#>
[CmdletBinding()]
param(
    [switch]$Prod,
    [int]$Port = 8000,
    [int]$FrontendPort = 5173,
    [switch]$NoBrowser
)

. "$PSScriptRoot\scripts\common.ps1"

Repair-PathVariable
Assert-Venv

$processes = @()

function Stop-Children {
    foreach ($process in $script:processes) {
        if ($process -and -not $process.HasExited) {
            try { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
}

try {
    if ($Prod) {
        Assert-NodeModules
        Write-Step 'Building the frontend'
        Invoke-FrontendBin 'vite' @('build')
        Write-Ok 'frontend\dist is up to date'

        Write-Step "Starting FORGE on http://127.0.0.1:$Port"
        Write-Host '   The API serves the built interface from the same origin.' -ForegroundColor DarkGray
        Write-Host '   Press Ctrl+C to stop.' -ForegroundColor DarkGray
        if (-not $NoBrowser) {
            Start-Job -ScriptBlock {
                param($url)
                Start-Sleep -Seconds 3
                Start-Process $url
            } -ArgumentList "http://127.0.0.1:$Port" | Out-Null
        }
        Push-Location $script:BackendDir
        try {
            & $script:VenvPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port
        } finally {
            Pop-Location
        }
        exit 0
    }

    Assert-NodeModules

    Write-Step "Starting the API on http://127.0.0.1:$Port"
    $api = Start-Process -FilePath $script:VenvPython `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$Port", '--reload') `
        -WorkingDirectory $script:BackendDir -NoNewWindow -PassThru
    $processes += $api

    Start-Sleep -Milliseconds 1500
    if ($api.HasExited) {
        Write-Fail "The API failed to start (exit code $($api.ExitCode))."
        exit 1
    }
    Write-Ok "API running (pid $($api.Id)) - docs at http://127.0.0.1:$Port/api/docs"

    Write-Step "Starting the interface on http://127.0.0.1:$FrontendPort"
    $viteCmd = Join-Path $script:FrontendDir 'node_modules\.bin\vite.cmd'
    $env:FORGE_API_URL = "http://127.0.0.1:$Port"
    $web = Start-Process -FilePath $viteCmd `
        -ArgumentList @('--port', "$FrontendPort", '--strictPort') `
        -WorkingDirectory $script:FrontendDir -NoNewWindow -PassThru
    $processes += $web

    Start-Sleep -Seconds 2
    if ($web.HasExited) {
        Write-Fail "The dev server failed to start (exit code $($web.ExitCode))."
        Stop-Children
        exit 1
    }
    Write-Ok "Interface running (pid $($web.Id))"

    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$FrontendPort" }

    Write-Host ''
    Write-Host "  FORGE is running at http://127.0.0.1:$FrontendPort" -ForegroundColor Green
    Write-Host '  Press Ctrl+C to stop both processes.' -ForegroundColor DarkGray
    Write-Host ''

    while (-not $api.HasExited -and -not $web.HasExited) {
        Start-Sleep -Seconds 1
    }
    if ($api.HasExited) { Write-Warn2 "The API exited (code $($api.ExitCode))." }
    if ($web.HasExited) { Write-Warn2 "The dev server exited (code $($web.ExitCode))." }
} finally {
    Stop-Children
}
