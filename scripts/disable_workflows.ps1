$keep = @("ai_tipster_system.yml", "update-dashboard-data.yml")
$dir = ".github/workflows"

Get-ChildItem $dir -Filter "*.yml" | ForEach-Object {
    if ($keep -contains $_.Name) {
        Write-Host "Keep: $($_.Name)" -ForegroundColor Green
    } else {
        $newName = "$($_.BaseName).disabled.yml"
        Rename-Item $_.FullName (Join-Path $dir $newName) -Force
        Write-Host "Disabled: $($_.Name)" -ForegroundColor Yellow
    }
}

Write-Host "`nDone!" -ForegroundColor Cyan
