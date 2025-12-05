Param(
  [Parameter(Mandatory=$true)][string]$AudioPath,
  [Parameter(Mandatory=$true)][string]$LyricsPath,
  [string]$BackendUrl = 'http://127.0.0.1:5000',
  [string]$Font = 'Arial',
  [int]$FontSize = 70,
  [string]$BgColor = '#000000'
)

Write-Host "Starting Croonify backend..."
$env:CROONIFY_BACKEND_PORT = [Uri]$BackendUrl | % Port
if (-not $env:CROONIFY_BACKEND_PORT) { $env:CROONIFY_BACKEND_PORT = 5000 }

$backend = Start-Process -PassThru -FilePath python -ArgumentList '-m','backend.app' -WorkingDirectory (Split-Path $PSScriptRoot -Parent)
Start-Sleep -Seconds 2

Write-Host "Waiting for backend ($BackendUrl) to be ready..."
for ($i=0; $i -lt 30; $i++) {
  try {
    Invoke-RestMethod -Method Options -Uri "$BackendUrl/generate" -TimeoutSec 5 | Out-Null
    break
  } catch {
    Start-Sleep -Seconds 1
  }
}

Write-Host "Running pipeline..."
& "$PSScriptRoot/run_pipeline.ps1" -AudioPath $AudioPath -LyricsPath $LyricsPath -BackendUrl $BackendUrl -Font $Font -FontSize $FontSize -BgColor $BgColor

Write-Host "Stopping backend..."
try { $backend | Stop-Process -Force } catch {}