# Emilie installer for Windows (PowerShell 5.1+ or 7).
#   powershell -ExecutionPolicy Bypass -File install.ps1
# Creates %LOCALAPPDATA%\Emilie\venv, installs Emilie into it, and puts `emilie` on your PATH.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$home_dir = Join-Path $env:LOCALAPPDATA "Emilie"
$venv = Join-Path $home_dir "venv"
$bin = Join-Path $home_dir "bin"
$src = Join-Path $home_dir "src"

function Find-Python {
    foreach ($c in @(@("py", "-3"), @("python"), @("python3"))) {
        try {
            $v = & $c[0] @($c[1..($c.Length - 1)]) -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and [version]$v -ge [version]"3.10") { return ,$c }
        } catch { }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host "Python 3.10+ not found. Install it first:  winget install Python.Python.3.12" -ForegroundColor Red
    exit 1
}
Write-Host "Using Python: $($py -join ' ')"

New-Item -ItemType Directory -Force -Path $home_dir, $bin | Out-Null
& $py[0] @($py[1..($py.Length - 1)]) -m venv $venv
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --upgrade pip | Out-Null
# keep a private copy of the sources, so deleting the cloned folder later does not break Emilie
if ((Resolve-Path $root).Path -ne (Resolve-Path $src -ErrorAction SilentlyContinue).Path) {
    if (Test-Path $src) { Remove-Item -Recurse -Force $src }
    New-Item -ItemType Directory -Force -Path $src | Out-Null
    Get-ChildItem -Force $root | Where-Object { $_.Name -notin @(".git", ".venv", "__pycache__", ".env") } |
        Copy-Item -Recurse -Force -Destination $src
}
& $vpy -m pip install --upgrade -e $src
if ($LASTEXITCODE -ne 0) { Write-Host "pip install failed" -ForegroundColor Red; exit 1 }

# launcher: emilie.cmd -> venv\Scripts\emilie.exe
Set-Content -Path (Join-Path $bin "emilie.cmd") -Encoding ASCII -Value "@echo off`r`n`"$venv\Scripts\emilie.exe`" %*"

$user_path = [Environment]::GetEnvironmentVariable("Path", "User")
if (($user_path -split ";") -notcontains $bin) {
    [Environment]::SetEnvironmentVariable("Path", ($user_path.TrimEnd(";") + ";" + $bin), "User")
    Write-Host "Added $bin to your PATH (open a NEW terminal for it to take effect)."
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "Optional: camera and microphone need ffmpeg:  winget install Gyan.FFmpeg" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Done. Open a new Windows Terminal and run:  emilie" -ForegroundColor Green
Write-Host "First run asks for an API key (or run: emilie --setup)."
