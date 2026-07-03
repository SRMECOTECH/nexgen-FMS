# =====================================================================
# nextGen-FMS — first-time venv setup
# Run from the project root:
#     .\scripts\setup-venv.ps1
# =====================================================================

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "==> Creating .venv with Python 3.13" -ForegroundColor Cyan
if (-not (Test-Path .venv)) {
    python -m venv .venv
} else {
    Write-Host "    .venv already exists — reusing"
}

Write-Host "==> Activating .venv" -ForegroundColor Cyan
. .\.venv\Scripts\Activate.ps1

Write-Host "==> Upgrading pip" -ForegroundColor Cyan
python -m pip install --upgrade pip

Write-Host "==> Installing backend deps" -ForegroundColor Cyan
pip install -r backend\requirements.txt

Write-Host "==> Installing ml_service deps" -ForegroundColor Cyan
pip install -r ml_service\requirements.txt

if (-not (Test-Path .env)) {
    Write-Host "==> No .env found. Create one at the repo root (it is the single source of config)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done. To use the venv in a new terminal:" -ForegroundColor Green
Write-Host "    .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "Then start the backend (port comes from .env: FMS_BACKEND_PORT=9001):" -ForegroundColor Green
Write-Host "    uvicorn backend.app.main:app --reload --port `$env:FMS_BACKEND_PORT --reload-dir backend --reload-dir lakehouse" -ForegroundColor Yellow
Write-Host ""
Write-Host "Frontend (port comes from .env: FMS_FRONTEND_PORT=6173):" -ForegroundColor Green
Write-Host "    Set-Location frontend; npm run dev" -ForegroundColor Yellow
