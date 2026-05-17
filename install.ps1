# SERENA bootstrap — Windows (PowerShell 5+).
# Idempotent: safe to re-run. Installs Ollama, pulls model, creates venv,
# installs deps, then launches the web server on http://localhost:7860.
# Run from an elevated PowerShell:  powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SerenaDir = Join-Path $ScriptDir "serena"
$VenvDir   = Join-Path $SerenaDir ".venv"
$ModelTag  = if ($env:SERENA_MODEL) { $env:SERENA_MODEL } else { "gemma4:e2b" }

function Log  ($m) { Write-Host "[serena] $m" -ForegroundColor Cyan }
function Warn ($m) { Write-Host "[warn]   $m" -ForegroundColor Yellow }
function Die  ($m) { Write-Host "[fail]   $m" -ForegroundColor Red; exit 1 }

# ─── 1. Ollama install ───────────────────────────────────────────
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Log "Ollama not found. Installing via winget…"
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Die "winget not available. Install Ollama manually from https://ollama.com/download/windows then re-run."
    }
    winget install --id Ollama.Ollama --silent --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
} else {
    Log "Ollama present."
}

# ─── 2. Ollama daemon ────────────────────────────────────────────
function Test-Ollama {
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri "http://localhost:11434/api/tags" | Out-Null; return $true }
    catch { return $false }
}
if (-not (Test-Ollama)) {
    Log "Starting Ollama daemon…"
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    $ok = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Ollama) { $ok = $true; break }
    }
    if (-not $ok) { Die "Ollama daemon did not start." }
}
Log "Ollama daemon reachable."

# ─── 3. Pull model ───────────────────────────────────────────────
$installed = (& ollama list) | Select-Object -Skip 1 | ForEach-Object { ($_ -split '\s+')[0] }
if ($installed -contains $ModelTag) {
    Log "Model $ModelTag already pulled."
} else {
    Log "Pulling $ModelTag (~2GB, one-time)…"
    & ollama pull $ModelTag
}

# ─── 4. Python interpreter ───────────────────────────────────────
$Py = $null
foreach ($v in @("3.12", "3.11", "3.10")) {
    $cand = & py "-$v" -c "import sys;print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $cand) { $Py = "py -$v"; break }
}
if (-not $Py) {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $minor = & python -c "import sys;print(sys.version_info.minor)"
        if ([int]$minor -ge 10 -and [int]$minor -le 12) { $Py = "python" }
    }
}
if (-not $Py) { Die "Python 3.10–3.12 required. Install from https://www.python.org/downloads/." }
Log "Using $Py."

# ─── 5. venv + deps ──────────────────────────────────────────────
if (-not (Test-Path $VenvDir)) {
    Log "Creating venv at $VenvDir…"
    & cmd /c "$Py -m venv `"$VenvDir`""
}
$VenvPy = Join-Path $VenvDir "Scripts\python.exe"
& $VenvPy -m pip install --quiet --upgrade pip
Log "Installing requirements…"
& $VenvPy -m pip install --quiet -r (Join-Path $SerenaDir "requirements.txt")

# ─── 6. Launch ───────────────────────────────────────────────────
Log "Launching SERENA on http://localhost:7860"
Set-Location (Join-Path $SerenaDir "web")
& $VenvPy "run.py"
