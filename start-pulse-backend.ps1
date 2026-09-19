param(
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 8505,
    [switch]$Setup
)
$ErrorActionPreference = "Stop"
$Repo = $PSScriptRoot
$Api = Join-Path $Repo "options-seller"
$Venv = Join-Path $Api "api/.venv-pulse"
$Python = Join-Path $Venv "Scripts/python.exe"
if ($Setup -or -not (Test-Path $Python)) {
    if (-not (Test-Path $Python)) {
        if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv $Venv }
        else { & python -m venv $Venv }
        if ($LASTEXITCODE -ne 0) { throw "Python 3.11 or newer is required." }
    }
    & $Python -m pip install -r (Join-Path $Api "api/requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
    & npm --prefix (Join-Path $Repo "mobile-app") ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed. Install Node.js LTS." }
    & npm --prefix (Join-Path $Repo "mobile-app") run build
    if ($LASTEXITCODE -ne 0) { throw "Web build failed." }
}
$env:PYTHONPATH = Join-Path $Api "src"
# Do not seed or overwrite the Windows server's actual paper portfolio.
Write-Host "Pulse: http://${ListenHost}:${Port}/pulse/"
Push-Location $Api
try { & $Python -m uvicorn api.main:app --host $ListenHost --port $Port --loop asyncio }
finally { Pop-Location }
exit $LASTEXITCODE
