<#
.SYNOPSIS
Produces the production build.

.DESCRIPTION
Type-checks and builds the frontend into frontend\dist, byte-compiles the
backend, applies pending migrations and prints a summary. After this,
.\run.ps1 -Prod serves the whole application from a single port.

.PARAMETER SkipTests
Do not run the test suites first.

.PARAMETER SkipMigrate
Do not apply database migrations.

.EXAMPLE
.\build.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipMigrate
)

. "$PSScriptRoot\scripts\common.ps1"

Repair-PathVariable
Assert-Venv
Assert-NodeModules

$started = Get-Date

if (-not $SkipTests) {
    Write-Step 'Running the test suites'
    & (Join-Path $script:ForgeRoot 'test.ps1')
    if ($LASTEXITCODE -ne 0) { Write-Fail 'Tests failed; build stopped.'; exit 1 }
}

Write-Step 'Byte-compiling the backend'
Invoke-Python @('-m', 'compileall', '-q', 'app')
Write-Ok 'No syntax errors'

if (-not $SkipMigrate) {
    Write-Step 'Applying database migrations'
    Invoke-Python @((Join-Path $script:ForgeRoot 'scripts\manage.py'), 'migrate') $script:ForgeRoot
    Write-Ok 'Schema up to date'
}

Write-Step 'Type-checking the frontend'
Invoke-FrontendBin 'tsc' @('--noEmit', '-p', 'tsconfig.app.json')
Write-Ok 'No type errors'

Write-Step 'Building the frontend'
$dist = Join-Path $script:FrontendDir 'dist'
if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }
Invoke-FrontendBin 'vite' @('build')

if (-not (Test-Path (Join-Path $dist 'index.html'))) {
    Write-Fail 'The build did not produce frontend\dist\index.html.'
    exit 1
}

$assets = Get-ChildItem $dist -Recurse -File
$totalKb = [math]::Round(($assets | Measure-Object -Property Length -Sum).Sum / 1KB, 1)
Write-Ok "$($assets.Count) files, $totalKb KB in frontend\dist"

Write-Host ''
Write-Host "Build complete in $([math]::Round(((Get-Date) - $started).TotalSeconds, 1))s." -ForegroundColor Green
Write-Host '  Serve it with: ' -NoNewline; Write-Host '.\run.ps1 -Prod' -ForegroundColor White
