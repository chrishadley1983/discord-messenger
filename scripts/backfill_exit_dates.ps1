# Backfill exit_date and launch_date from Brickset CSV export into Supabase
# Generates SQL UPDATE statements and runs them via Supabase REST API

$csv = Import-Csv 'C:\Users\Chris Hadley\Downloads\Brickset-allSets (3).csv'

# Build updates array
$updates = @()
foreach ($row in $csv) {
    $setNum = "$($row.Number)-$($row.Variant)"

    $exitDate = $null
    $launchDate = $null

    if ($row.ExitDate -ne '') {
        try {
            $parsed = [DateTime]::ParseExact($row.ExitDate.Trim(), 'dd/MM/yyyy HH:mm:ss', [System.Globalization.CultureInfo]::InvariantCulture)
            $exitDate = $parsed.ToString('yyyy-MM-dd')
        } catch {
            # Try alternate format
            try {
                $parsed = [DateTime]::Parse($row.ExitDate.Trim())
                $exitDate = $parsed.ToString('yyyy-MM-dd')
            } catch {}
        }
    }

    if ($row.LaunchDate -ne '') {
        try {
            $parsed = [DateTime]::ParseExact($row.LaunchDate.Trim(), 'dd/MM/yyyy HH:mm:ss', [System.Globalization.CultureInfo]::InvariantCulture)
            $launchDate = $parsed.ToString('yyyy-MM-dd')
        } catch {
            try {
                $parsed = [DateTime]::Parse($row.LaunchDate.Trim())
                $launchDate = $parsed.ToString('yyyy-MM-dd')
            } catch {}
        }
    }

    if ($exitDate -or $launchDate) {
        $updates += [PSCustomObject]@{
            SetNumber = $setNum
            ExitDate = $exitDate
            LaunchDate = $launchDate
        }
    }
}

Write-Output "Total updates to apply: $($updates.Count)"
Write-Output "  With exit_date: $(($updates | Where-Object { $_.ExitDate }).Count)"
Write-Output "  With launch_date: $(($updates | Where-Object { $_.LaunchDate }).Count)"

# Build SQL file with batched UPDATE statements
$sqlFile = 'C:\Users\Chris Hadley\Discord-Messenger\scripts\backfill_exit_dates.sql'
$sql = @()

# Use a CTE with VALUES for efficient bulk update
# Process in batches of 500 to keep SQL manageable
$batchSize = 500
$batchNum = 0

for ($i = 0; $i -lt $updates.Count; $i += $batchSize) {
    $batchNum++
    $batch = $updates[$i..([Math]::Min($i + $batchSize - 1, $updates.Count - 1))]

    $values = @()
    foreach ($u in $batch) {
        $exitVal = if ($u.ExitDate) { "'$($u.ExitDate)'::date" } else { "NULL" }
        $launchVal = if ($u.LaunchDate) { "'$($u.LaunchDate)'::date" } else { "NULL" }
        $escapedSetNum = $u.SetNumber -replace "'", "''"
        $values += "('$escapedSetNum', $exitVal, $launchVal)"
    }

    $valuesList = $values -join ",`n  "

    $sql += @"
-- Batch $batchNum ($($batch.Count) rows)
UPDATE brickset_sets AS bs
SET
  exit_date = COALESCE(v.exit_date, bs.exit_date),
  launch_date = COALESCE(v.launch_date, bs.launch_date)
FROM (VALUES
  $valuesList
) AS v(set_number, exit_date, launch_date)
WHERE bs.set_number = v.set_number;

"@
}

$sql -join "`n" | Set-Content -Path $sqlFile -Encoding UTF8
Write-Output "`nSQL file written to: $sqlFile"
Write-Output "Batches: $batchNum"
