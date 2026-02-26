# Read the SQL file and split into individual batch statements
$sqlContent = Get-Content -Path 'C:\Users\Chris Hadley\Discord-Messenger\scripts\backfill_exit_dates.sql' -Raw

# Split on the batch comment markers
$batches = $sqlContent -split '(?=-- Batch \d+)' | Where-Object { $_.Trim() -ne '' }

Write-Output "Found $($batches.Count) batches to execute"

# Output each batch to a separate file for execution
for ($i = 0; $i -lt $batches.Count; $i++) {
    $batchFile = "C:\Users\Chris Hadley\Discord-Messenger\scripts\batch_$($i + 1).sql"
    $batches[$i].Trim() | Set-Content -Path $batchFile -Encoding UTF8
    Write-Output "Wrote batch $($i + 1) to $batchFile"
}
