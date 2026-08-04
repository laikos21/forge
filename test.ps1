<#
.SYNOPSIS
Runs the FORGE test suites.

.DESCRIPTION
Backend: pytest (unit, API integration and the end-to-end workflow smoke test).
Frontend: TypeScript type checking and Vitest.

Tests never touch your real data directory - the backend suite points
FORGE_DATA_DIR at a temporary folder for every test.

.PARAMETER Backend
Run only the backend suite.

.PARAMETER Frontend
Run only the frontend checks.

.PARAMETER Verbose2
Show individual test names instead of the compact summary.

.PARAMETER Filter
Pass a pytest -k expression, e.g. -Filter duplicate.

.EXAMPLE
.\test.ps1

.EXAMPLE
.\test.ps1 -Backend -Filter search
#>
[CmdletBinding()]
param(
    [switch]$Backend,
    [switch]$Frontend,
    [switch]$Verbose2,
    [string]$Filter
)

. "$PSScriptRoot\scripts\common.ps1"

Repair-PathVariable

$runBackend = $Backend -or (-not $Backend -and -not $Frontend)
$runFrontend = $Frontend -or (-not $Backend -and -not $Frontend)
$failures = @()

if ($runBackend) {
    Assert-Venv
    Write-Step 'Backend test suite (pytest)'
    $pytestArgs = @('-m', 'pytest')
    if ($Verbose2) { $pytestArgs += '-v' } else { $pytestArgs += '-q' }
    if ($Filter) { $pytestArgs += @('-k', $Filter) }
    Push-Location $script:BackendDir
    try {
        & $script:VenvPython @pytestArgs
        if ($LASTEXITCODE -ne 0) { $failures += 'backend (pytest)' } else { Write-Ok 'Backend tests passed' }
    } finally {
        Pop-Location
    }
}

if ($runFrontend) {
    Assert-NodeModules

    Write-Step 'Frontend type checking (tsc)'
    try {
        Invoke-FrontendBin 'tsc' @('--noEmit', '-p', 'tsconfig.app.json')
        Write-Ok 'No type errors'
    } catch {
        $failures += 'frontend (typecheck)'
        Write-Fail $_.Exception.Message
    }

    Write-Step 'Frontend test suite (vitest)'
    $vitestArgs = @('run')
    if (-not $Verbose2) { $vitestArgs += @('--reporter=dot') }
    try {
        Invoke-FrontendBin 'vitest' $vitestArgs
        Write-Ok 'Frontend tests passed'
    } catch {
        $failures += 'frontend (vitest)'
        Write-Fail $_.Exception.Message
    }
}

Write-Host ''
if ($failures.Count -gt 0) {
    Write-Fail ("Failed: " + ($failures -join ', '))
    exit 1
}
Write-Host 'All requested test suites passed.' -ForegroundColor Green
