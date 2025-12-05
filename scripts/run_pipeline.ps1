Param(
  [Parameter(Mandatory=$true)][string]$AudioPath,
  [Parameter(Mandatory=$true)][string]$LyricsPath,
  [string]$BackendUrl = 'http://127.0.0.1:5000',
  [string]$Font = 'Arial',
  [int]$FontSize = 70,
  [string]$BgColor = '#000000'
)

if (!(Test-Path $AudioPath)) { Write-Error "Audio not found: $AudioPath"; exit 1 }
if (!(Test-Path $LyricsPath)) { Write-Error "Lyrics not found: $LyricsPath"; exit 1 }

$payload = @{
  audio_path = (Resolve-Path $AudioPath).Path
  lyrics_path = (Resolve-Path $LyricsPath).Path
  font = $Font
  fontsize = $FontSize
  bg_color = $BgColor
  separation_engine = 'auto'
  sync_refine = $false
} | ConvertTo-Json

Write-Host "POST $BackendUrl/generate"
$resp = Invoke-RestMethod -Method Post -Uri "$BackendUrl/generate" -ContentType 'application/json' -Body $payload -TimeoutSec 120
if (!$resp.job_id) { Write-Error "No job_id returned"; exit 1 }
$job = $resp.job_id
Write-Host "Job ID: $job"

$start = Get-Date
while ($true) {
  try {
    $s = Invoke-RestMethod -Method Get -Uri "$BackendUrl/status/$job" -TimeoutSec 60
    $stage = $s.stage
    $progress = $s.progress
    $status = $s.status
    if ($stage) { Write-Host "Stage: $stage" }
    Write-Host "Progress: $progress% Status: $status"
    if ($status -eq 'done') {
      $url = $s.output_url
      if ($url -and ($url -notmatch '^https?://')) { $url = "$BackendUrl$url" }
      Write-Host "OUTPUT_URL: $url"
      break
    }
    if ($status -eq 'error') {
      Write-Error ($s.error)
      exit 1
    }
  } catch {
    Write-Warning "Status poll failed: $($_.Exception.Message)"
  }
  Start-Sleep -Seconds 3
}