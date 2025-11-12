Param(
    [int]$FrontendPort = 5500,
    [int]$BackendPort = 5000
)

$ErrorActionPreference = 'Continue'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Wait-ForPort($Port, $Host='127.0.0.1', $TimeoutSec=30) {
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSec) {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $client.Connect($Host, $Port)
            $client.Close()
            return $true
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    return $false
}

$backend = Start-Process -FilePath "python" -ArgumentList "app.py" -WorkingDirectory (Join-Path $Root 'backend') -PassThru -WindowStyle Hidden
$frontend = Start-Process -FilePath "python" -ArgumentList "-m http.server $FrontendPort --directory frontend" -WorkingDirectory $Root -PassThru -WindowStyle Hidden

Wait-ForPort -Port $BackendPort | Out-Null
Start-Process "http://localhost:$FrontendPort/"
Write-Host "Frontend: http://localhost:$FrontendPort/"
Write-Host "Backend: http://localhost:$BackendPort/"

Read-Host "Press Enter to stop services"

try { Stop-Process -Id $backend.Id -Force } catch {}
try { Stop-Process -Id $frontend.Id -Force } catch {}

Write-Host "Services stopped."