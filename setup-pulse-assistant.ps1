$ErrorActionPreference = "Stop"
$Repo = $PSScriptRoot
$ToolDir = Join-Path $Repo ".pulse-tools"
& npm install --prefix $ToolDir @openai/codex@0.155.1 --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw "Codex installation failed; install Node.js LTS first." }
$Entry = Join-Path $ToolDir "node_modules/@openai/codex/bin/codex.js"
& node $Entry login status
if ($LASTEXITCODE -ne 0) { & node $Entry login }
if ($LASTEXITCODE -ne 0) { throw "Codex sign-in failed." }
Write-Host "Assistant ready. Open Pulse on localhost and pair your device."
