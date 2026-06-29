# noWand installer for Windows (PowerShell)
# Mirrors install.sh: finds Python, checks tkinter, creates a venv, installs
# dependencies, verifies SVG rendering, and optionally launches the app.
#
# Run it from this folder:
#     powershell -ExecutionPolicy Bypass -File install.ps1
# (the -ExecutionPolicy Bypass avoids Windows' default script-blocking)

$ErrorActionPreference = "Stop"
$MinMajor = 3
$MinMinor = 12

function Info($m)    { Write-Host "[noWand] $m" -ForegroundColor Cyan }
function Good($m)    { Write-Host "[noWand] $m" -ForegroundColor Green }
function Warn($m)    { Write-Host "[noWand] WARNING: $m" -ForegroundColor Yellow }
function Die($m)     { Write-Host "[noWand] ERROR: $m" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "+==============================+"
Write-Host "|      noWand  -  installer    |"
Write-Host "+==============================+"
Write-Host ""

# --- 1. Find a suitable Python -------------------------------------------------
Info "Looking for Python $MinMajor.$MinMinor or newer..."

$python = $null
# The 'py' launcher is the most reliable way to find Python on Windows.
$candidates = @(
    @("py", @("-3.14")), @("py", @("-3.13")), @("py", @("-3.12")),
    @("py", @("-3")), @("python", @()), @("python3", @())
)
foreach ($c in $candidates) {
    $exe = $c[0]; $pre = $c[1]
    if (Get-Command $exe -ErrorAction SilentlyContinue) {
        try {
            $ver = & $exe @pre -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($ver -match '^(\d+)\.(\d+)$') {
                $maj = [int]$Matches[1]; $min = [int]$Matches[2]
                if ($maj -eq $MinMajor -and $min -ge $MinMinor) {
                    $python = @($exe) + $pre
                    Good "Found: $exe $pre ($ver)"
                    break
                }
            }
        } catch { }
    }
}

if (-not $python) {
    Die "Python $MinMajor.$MinMinor+ not found.`n" +
        "  Install it from https://www.python.org/downloads/windows/`n" +
        "  During install, tick 'Add python.exe to PATH' and keep 'tcl/tk and IDLE' checked."
}

# Helper to invoke the chosen interpreter
function Py { & $python[0] @($python[1..($python.Length-1)] + $args) }

# --- 2. Check tkinter ----------------------------------------------------------
Info "Checking tkinter..."
try { Py -c "import tkinter" 2>$null | Out-Null; Good "tkinter OK" }
catch {
    Die "tkinter is not available.`n" +
        "  Reinstall Python from python.org and keep the 'tcl/tk and IDLE' option checked."
}

# --- 3. Create / reuse virtual environment ------------------------------------
$venv = Join-Path $PSScriptRoot ".venv"
if (Test-Path $venv) {
    Info "Virtual environment already exists - reusing it."
} else {
    Info "Creating virtual environment in .venv ..."
    Py -m venv $venv
    Good "Virtual environment created."
}

$venvPy = Join-Path $venv "Scripts\python.exe"

# --- 4. Install dependencies ---------------------------------------------------
Info "Installing dependencies from requirements.txt ..."
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
Good "All packages installed."

# --- 5. Verify cairosvg can actually render -----------------------------------
Info "Verifying SVG rendering..."
$svgTest = @'
import cairosvg
svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="5" fill="red"/></svg>'
cairosvg.svg2png(bytestring=svg, output_width=10, output_height=10)
print("ok")
'@
$cairoOk = $false
try { & $venvPy -c $svgTest 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { $cairoOk = $true } } catch { }

if ($cairoOk) {
    Good "SVG rendering works - icons will display correctly."
} else {
    Write-Host ""
    Warn "cairosvg is installed but could not render a test SVG."
    Write-Host "  On Windows, cairosvg needs the Cairo graphics library (libcairo-2.dll),"
    Write-Host "  which is bundled with the GTK3 runtime. Install it, then re-run this script:"
    Write-Host ""
    Write-Host "    https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases"
    Write-Host ""
    Write-Host "  (Download the latest 'gtk3-runtime ... -ts-win64.exe', run it, then reopen PowerShell.)"
    Write-Host "  The app still runs without it - device icons just fall back to text labels."
    Write-Host ""
}

# --- 6. Offer to launch --------------------------------------------------------
Write-Host ""
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  To run noWand at any time:"
Write-Host "    .venv\Scripts\python app.py"
Write-Host ""
$answer = Read-Host "Launch noWand now? [Y/n]"
if ([string]::IsNullOrWhiteSpace($answer) -or $answer -match '^[Yy]') {
    Info "Starting noWand..."
    & $venvPy (Join-Path $PSScriptRoot "app.py")
}
