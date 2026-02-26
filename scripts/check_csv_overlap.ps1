# Check how many of the 8630 sets with exit dates are also in our retired+Keepa set
$csv = Import-Csv 'C:\Users\Chris Hadley\Downloads\Brickset-allSets (3).csv'

$withExit = $csv | Where-Object { $_.ExitDate -ne '' }

# Build set_number format (Number-Variant)
$exitDates = @{}
foreach ($row in $withExit) {
    $setNum = "$($row.Number)-$($row.Variant)"
    $exitDates[$setNum] = $row.ExitDate
}

Write-Output "Sets with exit dates in CSV: $($exitDates.Count)"

# Check date format
Write-Output "`nDate format samples:"
$withExit | Select-Object -First 5 | ForEach-Object {
    Write-Output "  $($_.Number)-$($_.Variant): ExitDate='$($_.ExitDate)' LaunchDate='$($_.LaunchDate)'"
}

# Count by availability
Write-Output "`nAvailability distribution of sets WITH exit dates:"
$withExit | Group-Object Availability | Sort-Object Count -Descending | Format-Table Name, Count -AutoSize
