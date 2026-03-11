nssm restart HadleyAPI
Start-Sleep -Seconds 3
$response = Invoke-WebRequest -Uri "http://localhost:8100/voice/voices" -UseBasicParsing -ErrorAction SilentlyContinue
if ($response.StatusCode -eq 200) {
    Write-Output "Voice routes loaded: $($response.Content)"
} else {
    Write-Output "Voice routes NOT loaded (status: $($response.StatusCode))"
}
