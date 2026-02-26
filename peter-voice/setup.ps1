# Peter Voice Desktop Client - Setup Script
# Run once: powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = "Stop"
$voiceDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "=== Peter Voice Setup ===" -ForegroundColor Cyan
Write-Host ""

# -----------------------------------------------------------------------
# 1. Python 3.13
# -----------------------------------------------------------------------
$python = $null

# Try py launcher first (most reliable on Windows)
try {
    $ver = & py -3.13 --version 2>&1
    if ($ver -match "3\.13") {
        $python = "py -3.13"
        Write-Host "[OK] $ver (via py launcher)" -ForegroundColor Green
    }
} catch {}

# Try direct python command
if (-not $python) {
    foreach ($candidate in @("python3.13", "python")) {
        try {
            $ver = & $candidate --version 2>&1
            if ($ver -match "3\.13") {
                $python = $candidate
                Write-Host "[OK] $ver" -ForegroundColor Green
                break
            }
        } catch {}
    }
}

# Try common install paths
if (-not $python) {
    $paths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "C:\Python313\python.exe",
        "C:\Program Files\Python313\python.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) {
            $ver = & $p --version 2>&1
            if ($ver -match "3\.13") {
                $python = $p
                Write-Host "[OK] $ver (at $p)" -ForegroundColor Green
                break
            }
        }
    }
}

if (-not $python) {
    Write-Host "Python 3.13 not found. Installing via winget..." -ForegroundColor Yellow
    winget install Python.Python.3.13 --accept-package-agreements --accept-source-agreements
    Write-Host "Please restart this script after Python installs." -ForegroundColor Red
    exit 1
}

# -----------------------------------------------------------------------
# 2. Virtual environment
# -----------------------------------------------------------------------
$venvPath = Join-Path $voiceDir ".venv"
$pythonVenv = Join-Path $venvPath "Scripts\python.exe"
$pip = Join-Path $venvPath "Scripts\pip.exe"

if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    if ($python -eq "py -3.13") {
        & py -3.13 -m venv $venvPath
    } else {
        & $python -m venv $venvPath
    }
}
Write-Host "[OK] venv at $venvPath" -ForegroundColor Green

# -----------------------------------------------------------------------
# 3. Dependencies
# -----------------------------------------------------------------------
Write-Host "Installing Python dependencies (this may take a few minutes)..." -ForegroundColor Yellow
& $pip install --upgrade pip -q
& $pip install -r (Join-Path $voiceDir "requirements.txt")
Write-Host "[OK] Dependencies installed" -ForegroundColor Green

# -----------------------------------------------------------------------
# 4. espeak-ng (required by Kokoro for phonemisation)
# -----------------------------------------------------------------------
$espeak = Get-Command espeak-ng -ErrorAction SilentlyContinue
if (-not $espeak) {
    # Also check Program Files
    $espeakPath = "C:\Program Files\eSpeak NG\espeak-ng.exe"
    if (Test-Path $espeakPath) {
        Write-Host "[OK] espeak-ng found at $espeakPath" -ForegroundColor Green
    } else {
        Write-Host "Installing espeak-ng..." -ForegroundColor Yellow
        winget install espeak-ng --accept-package-agreements --accept-source-agreements
    }
} else {
    Write-Host "[OK] espeak-ng found" -ForegroundColor Green
}

# -----------------------------------------------------------------------
# 5. Kokoro ONNX models
# -----------------------------------------------------------------------
$modelsDir = Join-Path $voiceDir "models"
$modelFile = Join-Path $modelsDir "kokoro-v1.0.onnx"
$voicesFile = Join-Path $modelsDir "voices-v1.0.bin"

if (-not (Test-Path $modelsDir)) {
    New-Item -ItemType Directory -Path $modelsDir | Out-Null
}

if (-not (Test-Path $modelFile) -or -not (Test-Path $voicesFile)) {
    Write-Host "Downloading Kokoro ONNX models (~450MB)..." -ForegroundColor Yellow
    $modelUrl = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
    $voicesUrl = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

    Write-Host "  Downloading kokoro-v1.0.onnx..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $modelUrl -OutFile $modelFile -UseBasicParsing
    Write-Host "  Downloading voices-v1.0.bin..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $voicesUrl -OutFile $voicesFile -UseBasicParsing
    Write-Host "[OK] Models downloaded" -ForegroundColor Green
} else {
    Write-Host "[OK] Models already present" -ForegroundColor Green
}

# -----------------------------------------------------------------------
# 6. Verify imports
# -----------------------------------------------------------------------
Write-Host "Verifying imports..." -ForegroundColor Yellow
& $pythonVenv -c "import kokoro_onnx; import moonshine_onnx; import sounddevice; import pystray; import pynput; import aiohttp; import torch; print('All imports OK')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Import verification FAILED. Check errors above." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] All imports verified" -ForegroundColor Green

# -----------------------------------------------------------------------
# 7. Windows startup shortcut (optional)
# -----------------------------------------------------------------------
$startupDir = [System.IO.Path]::Combine($env:APPDATA, "Microsoft\Windows\Start Menu\Programs\Startup")
$shortcutPath = Join-Path $startupDir "Peter Voice.lnk"

if (-not (Test-Path $shortcutPath)) {
    $response = Read-Host "Add to Windows startup? (y/n)"
    if ($response -eq "y") {
        $WScriptShell = New-Object -ComObject WScript.Shell
        $shortcut = $WScriptShell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $pythonVenv
        $shortcut.Arguments = "`"$(Join-Path $voiceDir 'peter_voice.pyw')`""
        $shortcut.WorkingDirectory = $voiceDir
        $shortcut.WindowStyle = 7  # Minimized
        $shortcut.Description = "Peter Voice Desktop Client"
        $shortcut.Save()
        Write-Host "[OK] Startup shortcut created" -ForegroundColor Green
    }
} else {
    Write-Host "[OK] Startup shortcut already exists" -ForegroundColor Green
}

# -----------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------
Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "To run manually:" -ForegroundColor Cyan
Write-Host "  $pythonVenv `"$(Join-Path $voiceDir 'peter_voice.pyw')`"" -ForegroundColor White
Write-Host ""
Write-Host "Hotkeys:" -ForegroundColor Cyan
Write-Host "  Ctrl+Space         Push-to-talk" -ForegroundColor White
Write-Host "  Ctrl+Shift+Space   Toggle PTT / Wake Word mode" -ForegroundColor White
Write-Host ""
