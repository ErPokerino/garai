# Avvio di GarAI: installa le dipendenze al primo avvio, compila il frontend se serve e apre il browser.
#   .\avvia.ps1            avvio normale (http://127.0.0.1:8765)
#   .\avvia.ps1 -Rebuild   ricompila il frontend
param([switch]$Rebuild, [int]$Port = 8765)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -c "import fastapi, google.genai" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installazione dipendenze Python..."
    python -m pip install -r requirements.txt
}

if ($Rebuild -or -not (Test-Path "web\dist\index.html")) {
    Write-Host "Compilazione del frontend..."
    Push-Location web
    if (-not (Test-Path "node_modules")) { npm install --no-audit --no-fund }
    npm run build
    Pop-Location
}

python -m app --port $Port
