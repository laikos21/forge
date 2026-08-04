# Shared helpers for the FORGE PowerShell scripts.
# Dot-source this file: . "$PSScriptRoot\scripts\common.ps1"

$ErrorActionPreference = 'Stop'

$script:ForgeRoot = Split-Path -Parent $PSScriptRoot
$script:BackendDir = Join-Path $script:ForgeRoot 'backend'
$script:FrontendDir = Join-Path $script:ForgeRoot 'frontend'
$script:VenvDir = Join-Path $script:BackendDir '.venv'
$script:VenvPython = Join-Path $script:VenvDir 'Scripts\python.exe'

function Write-Step([string]$Message) { Write-Host "`n>> $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host "   OK  $Message" -ForegroundColor Green }
function Write-Warn2([string]$Message) { Write-Host "   !   $Message" -ForegroundColor Yellow }
function Write-Fail([string]$Message) { Write-Host "   X   $Message" -ForegroundColor Red }

<#
.SYNOPSIS
Removes stray quotes and blank entries from PATH for this process only.

.DESCRIPTION
A single unbalanced double quote anywhere in PATH makes cmd.exe stop resolving
every entry after it, which breaks npm's child processes with a confusing
"'node' is not recognized" error. This repairs the copy of PATH inside the
current process; the machine and user environment variables are left untouched.
#>
function Repair-PathVariable {
    $entries = $env:PATH -split ';' |
        ForEach-Object { $_.Trim().Trim('"') } |
        Where-Object { $_ -ne '' }
    $repaired = ($entries -join ';')
    if ($repaired -ne $env:PATH) {
        $env:PATH = $repaired
        Write-Warn2 'PATH contained stray quotes or empty entries; cleaned for this session only.'
    }
}

function Get-CommandPath([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) { return $null }
    if ($command.Source) { return $command.Source }
    return $command.Path
}

function Test-PythonVersion([string]$Exe, [int]$MinMajor = 3, [int]$MinMinor = 11) {
    try {
        $raw = & $Exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    } catch { return $false }
    if (-not $raw) { return $false }
    $parts = $raw.Trim().Split('.')
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    return ($major -gt $MinMajor) -or (($major -eq $MinMajor) -and ($minor -ge $MinMinor))
}

function Find-Python {
    foreach ($candidate in @('py -3.13', 'py -3.12', 'py -3.11', 'python', 'python3')) {
        $parts = $candidate.Split(' ')
        $exe = Get-CommandPath $parts[0]
        if (-not $exe) { continue }
        if ($parts.Count -gt 1) {
            try { $resolved = (& $exe $parts[1] -c "import sys; print(sys.executable)" 2>$null) } catch { continue }
            if ($resolved -and (Test-PythonVersion $resolved)) { return $resolved.Trim() }
        } elseif (Test-PythonVersion $exe) {
            return $exe
        }
    }
    return $null
}

function Assert-Venv {
    if (-not (Test-Path $script:VenvPython)) {
        throw "The Python environment is missing. Run .\bootstrap.ps1 first."
    }
}

function Assert-NodeModules {
    if (-not (Test-Path (Join-Path $script:FrontendDir 'node_modules'))) {
        throw "Frontend dependencies are missing. Run .\bootstrap.ps1 first."
    }
}

<#
.SYNOPSIS
Runs a native command, judging success by its exit code alone.

.DESCRIPTION
Windows PowerShell turns anything a native program writes to stderr into an
error record, and with $ErrorActionPreference = 'Stop' that aborts the script -
even when the program only logged an informational line (alembic and npm both
do). Inside this helper the preference is relaxed and the exit code is the
only thing that decides success.
#>
function Invoke-Native([string]$Executable, [string[]]$Arguments, [string]$WorkingDirectory) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    Push-Location $WorkingDirectory
    try {
        & $Executable @Arguments
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) {
        throw "$(Split-Path -Leaf $Executable) $($Arguments -join ' ') failed with exit code $code."
    }
}

function Invoke-Npm([string[]]$Arguments, [string]$WorkingDirectory = $script:FrontendDir) {
    Repair-PathVariable
    $npm = Get-CommandPath 'npm.cmd'
    if (-not $npm) { $npm = Get-CommandPath 'npm' }
    if (-not $npm) { throw 'npm was not found on PATH. Install Node.js 20 or newer.' }
    Invoke-Native $npm $Arguments $WorkingDirectory
}

<# Run a locally installed frontend binary (vite, vitest, tsc) directly.
   Faster and quieter than going through `npm run`, and it avoids npm's
   script-approval prompts. #>
function Invoke-FrontendBin([string]$Name, [string[]]$Arguments) {
    Repair-PathVariable
    $binary = Join-Path $script:FrontendDir "node_modules\.bin\$Name.cmd"
    if (-not (Test-Path $binary)) { throw "$Name is not installed. Run .\bootstrap.ps1 first." }
    Invoke-Native $binary $Arguments $script:FrontendDir
}

function Invoke-Python([string[]]$Arguments, [string]$WorkingDirectory = $script:BackendDir) {
    Assert-Venv
    Invoke-Native $script:VenvPython $Arguments $WorkingDirectory
}
