$sqlContent = Get-Content -Path 'C:\Users\Chris Hadley\Discord-Messenger\scripts\backfill_exit_dates.sql' -Raw
$batches = $sqlContent -split '(?=-- Batch \d+)' | Where-Object { $_.Trim() -ne '' }
Write-Output "Total batches: $($batches.Count)"
$outDir = 'C:\Users\Chris Hadley\Discord-Messenger\scripts\sql_batches'
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }
for ($i = 0; $i -lt $batches.Count; $i++) {
    $batchFile = Join-Path $outDir "batch_$($i + 1).sql"
    $batches[$i].Trim() | Set-Content -Path $batchFile -Encoding UTF8 -NoNewline
    $size = (Get-Item $batchFile).Length
    Write-Output "Batch $($i + 1): $size bytes"
}
