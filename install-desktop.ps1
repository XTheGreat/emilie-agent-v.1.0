# Emilie desktop app installer for Windows (PowerShell 5.1+ or 7).
#   powershell -ExecutionPolicy Bypass -File install-desktop.ps1
# Installs the window's packages (Electron, React UI) in .\desktop, builds the UI, and adds "Emilie" shortcuts to the
# Start menu and the desktop. The agent itself is the same Python Emilie as the CLI (install.ps1 sets it up).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$desk = Join-Path $root "desktop"

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# 1. Python side: Emilie's own environment (install.ps1 creates it the first time)
$venvPy = Join-Path $env:LOCALAPPDATA "Emilie\venv\Scripts\python.exe"
if (-not (Test-Path $venvPy) -and -not (Test-Path (Join-Path $root ".venv\Scripts\python.exe"))) {
    Step "Emilie (Python) is not installed yet: running install.ps1 first"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $root "install.ps1")
    if ($LASTEXITCODE -ne 0) { Write-Host "install.ps1 failed" -ForegroundColor Red; exit 1 }
}

# 2. Node.js runs the window (Electron)
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js is needed for the desktop window. Install it, open a NEW terminal and run this again:" -ForegroundColor Yellow
    Write-Host "    winget install OpenJS.NodeJS.LTS"
    exit 1
}
Write-Host "Node.js $(node --version)"

Push-Location $desk
try {
    Step "Installing the desktop packages (first time takes a few minutes)"
    if (Test-Path "package-lock.json") { npm ci --no-audit --no-fund --loglevel=error } else { npm install --no-audit --no-fund --loglevel=error }
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }

    Step "Downloading the Electron runtime"
    node node_modules/electron/install.js
    if (-not (Test-Path "node_modules\electron\dist\electron.exe")) { throw "Electron did not download (check your internet connection)" }

    Step "Building the interface"
    npm run build --silent
    if ($LASTEXITCODE -ne 0) { throw "the UI build failed" }
} finally {
    Pop-Location
}

# 3. Shortcuts with Emilie's icon
Step "Creating shortcuts"
$exe = Join-Path $desk "node_modules\electron\dist\electron.exe"
$icon = Join-Path $desk "build\icon.ico"
$shell = New-Object -ComObject WScript.Shell
$places = @([Environment]::GetFolderPath("Desktop"), (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"))
foreach ($dir in $places) {
    $lnk = $shell.CreateShortcut((Join-Path $dir "Emilie.lnk"))
    $lnk.TargetPath = $exe
    $lnk.Arguments = "`"$desk`""
    $lnk.WorkingDirectory = $desk
    $lnk.IconLocation = "$icon,0"
    $lnk.Description = "Emilie - coding agent"
    $lnk.Save()
    Write-Host "  $dir\Emilie.lnk"
}

# 4. Tell `emilie app` where the window lives
$data = Join-Path $env:USERPROFILE ".emilie\desktop"
New-Item -ItemType Directory -Force -Path $data | Out-Null
@{ desktop = $desk } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $data "app.json")

Write-Host ""
Write-Host "Done. Open Emilie from the Start menu or the desktop shortcut (or run: emilie app)." -ForegroundColor Green
