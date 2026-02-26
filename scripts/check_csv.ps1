$csv = Import-Csv 'C:\Users\Chris Hadley\Downloads\Brickset-allSets (3).csv'
$total = $csv.Count
$hasExit = ($csv | Where-Object { $_.ExitDate -ne '' }).Count
$hasLaunch = ($csv | Where-Object { $_.LaunchDate -ne '' }).Count
Write-Output "Total rows: $total"
Write-Output "Has ExitDate: $hasExit"
Write-Output "Has LaunchDate: $hasLaunch"

Write-Output "`nSample rows with ExitDate:"
$csv | Where-Object { $_.ExitDate -ne '' } | Select-Object -First 10 | Format-Table Number, Variant, SetName, Availability, ExitDate, LaunchDate -AutoSize
