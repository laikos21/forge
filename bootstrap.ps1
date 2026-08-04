<#
.SYNOPSIS
Prepares FORGE for use on this machine.

.DESCRIPTION
Verifies the required tooling, creates the Python virtual environment, installs
backend and frontend dependencies, generates the sample documents, applies the
database migrations and (unless told otherwise) loads the demonstration data.

Safe to re-run: every step is idempotent.

.PARAMETER SkipDemo
Do not load the demonstration data.

.PARAMETER Clean
Delete the virtual environment and node_modules before installing.

.EXAMPLE
.\bootstrap.ps1

.EXAMPLE
.\bootstrap.ps1 -SkipDemo
#>
[CmdletBinding()]
param(
    [switch]$SkipDemo,
    [switch]$Clean
)

. "$PSScriptRoot\scripts\common.ps1"

Write-Host 'FORGE bootstrap' -ForegroundColor White
Write-Host '===============' -ForegroundColor White

Repair-PathVariable

# --- 1. tooling -------------------------------------------------------------

Write-Step 'Checking required tooling'

$python = Find-Python
if (-not $python) {
    Write-Fail 'Python 3.11 or newer was not found.'
    Write-Host '       Install it from https://www.python.org/downloads/windows/ (tick "Add python.exe to PATH")'
    Write-Host '       or run: winget install Python.Python.3.13'
    exit 1
}
$pythonVersion = (& $python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
Write-Ok "Python $pythonVersion at $python"

$node = Get-CommandPath 'node'
if (-not $node) {
    Write-Fail 'Node.js was not found.'
    Write-Host '       Install it from https://nodejs.org/ (LTS) or run: winget install OpenJS.NodeJS.LTS'
    exit 1
}
$nodeVersion = (& $node --version).Trim()
$nodeMajor = [int]($nodeVersion.TrimStart('v').Split('.')[0])
if ($nodeMajor -lt 20) {
    Write-Fail "Node.js $nodeVersion is too old. FORGE needs 20 or newer."
    exit 1
}
Write-Ok "Node.js $nodeVersion at $node"

if (-not (Get-CommandPath 'npm.cmd') -and -not (Get-CommandPath 'npm')) {
    Write-Fail 'npm was not found even though Node.js is installed.'
    exit 1
}
Write-Ok 'npm available'

# SQLite ships inside Python; FTS5 is what FORGE actually depends on.
$fts = & $python -c "import sqlite3;c=sqlite3.connect(':memory:');c.execute('CREATE VIRTUAL TABLE t USING fts5(a)');print('ok')" 2>$null
if ($fts -ne 'ok') {
    Write-Fail 'This Python build has no SQLite FTS5 support, which FORGE requires for search.'
    Write-Host '       Install the official python.org build for Windows.'
    exit 1
}
Write-Ok 'SQLite FTS5 available'

# --- 2. python environment --------------------------------------------------

if ($Clean) {
    Write-Step 'Removing existing environments'
    if (Test-Path $script:VenvDir) { Remove-Item -Recurse -Force $script:VenvDir }
    $nodeModules = Join-Path $script:FrontendDir 'node_modules'
    if (Test-Path $nodeModules) { Remove-Item -Recurse -Force $nodeModules }
    Write-Ok 'Cleaned'
}

Write-Step 'Creating the Python virtual environment'
if (-not (Test-Path $script:VenvPython)) {
    & $python -m venv $script:VenvDir
    if ($LASTEXITCODE -ne 0) { Write-Fail 'Could not create the virtual environment.'; exit 1 }
    Write-Ok "Created $script:VenvDir"
} else {
    Write-Ok 'Already present'
}

Write-Step 'Installing backend dependencies'
& $script:VenvPython -m pip install --upgrade pip --quiet
& $script:VenvPython -m pip install -e "$script:BackendDir[dev]" --quiet
if ($LASTEXITCODE -ne 0) { Write-Fail 'Backend dependency installation failed.'; exit 1 }
Write-Ok 'FastAPI, SQLAlchemy, Alembic, pypdf, Pillow, pytest installed'

$ocr = & $script:VenvPython -c "import shutil;print('yes' if shutil.which('tesseract') else 'no')"
if ($ocr.Trim() -eq 'yes') {
    Write-Ok 'Tesseract found: OCR for screenshots can be enabled in Settings'
} else {
    Write-Warn2 'Tesseract not found. OCR stays optional and disabled; everything else works.'
    Write-Host '       To enable it later: winget install UB-Mannheim.TesseractOCR' -ForegroundColor DarkGray
    Write-Host "       then: $script:VenvPython -m pip install pytesseract" -ForegroundColor DarkGray
}

# --- 3. frontend ------------------------------------------------------------

Write-Step 'Installing frontend dependencies'
if (Test-Path (Join-Path $script:FrontendDir 'package-lock.json')) {
    Invoke-Npm @('ci', '--no-audit', '--no-fund')
} else {
    Invoke-Npm @('install', '--no-audit', '--no-fund')
}
Write-Ok 'React, Vite, TypeScript, Vitest installed'

# --- 4. data ----------------------------------------------------------------

Write-Step 'Generating the sample documents'
$samplePdf = Join-Path $script:ForgeRoot 'samples\helios-q3-fy2026-review.pdf'
if (-not (Test-Path $samplePdf)) {
    Invoke-Python @((Join-Path $script:ForgeRoot 'scripts\make_samples.py')) $script:ForgeRoot
    Write-Ok 'Samples written to samples\'
} else {
    Write-Ok 'Samples already present'
}

Write-Step 'Applying database migrations'
Invoke-Python @((Join-Path $script:ForgeRoot 'scripts\manage.py'), 'migrate') $script:ForgeRoot
Write-Ok 'Database is at the current schema revision'

if (-not $SkipDemo) {
    Write-Step 'Loading demonstration data'
    Invoke-Python @((Join-Path $script:ForgeRoot 'scripts\manage.py'), 'seed') $script:ForgeRoot
    Write-Ok 'Demonstration content loaded (clearly labelled, removable from Settings)'
}

# --- done -------------------------------------------------------------------

Write-Host ''
Write-Host 'Bootstrap complete.' -ForegroundColor Green
Write-Host ''
Write-Host '  Start FORGE:      ' -NoNewline; Write-Host '.\run.ps1' -ForegroundColor White
Write-Host '  Run the tests:    ' -NoNewline; Write-Host '.\test.ps1' -ForegroundColor White
Write-Host '  Production build: ' -NoNewline; Write-Host '.\build.ps1' -ForegroundColor White
Write-Host ''
Write-Host '  Data lives in:    ' -NoNewline; Write-Host (Join-Path $script:ForgeRoot 'data') -ForegroundColor White
Write-Host '  Nothing leaves this machine: no account, no API key, no network calls.' -ForegroundColor DarkGray
