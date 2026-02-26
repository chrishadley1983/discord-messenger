# Delete .pyc cache for hadley_api
$pycache = "C:\Users\Chris Hadley\discord-messenger\hadley_api\__pycache__"
if (Test-Path $pycache) {
    Remove-Item -Recurse -Force $pycache
    Write-Output "Deleted $pycache"
}

# Restart via NSSM
nssm restart HadleyAPI
Start-Sleep -Seconds 4

# Test
try {
    $r = Invoke-RestMethod -Uri 'http://localhost:8100/' -TimeoutSec 5
    Write-Output "API Status: $($r.status)"
} catch {
    Write-Output "API not responding yet"
}
