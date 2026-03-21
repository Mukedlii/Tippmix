# Disable old GitHub workflows by renaming them
# Keep only: ai_tipster_system.yml

$workflowDir = ".github/workflows"
$keep = @("ai_tipster_system.yml", "update-dashboard-data.yml")

$workflows = Get-ChildItem $workflowDir -Filter "*.yml"

Write-Host "`n🔧 Disabling old workflows...`n" -ForegroundColor Cyan

foreach ($file in $workflows) {
    if ($keep -contains $file.Name) {
        Write-Host "✅ Keep: $($file.Name)" -ForegroundColor Green
    } else {
        $newName = "$($file.BaseName).disabled.yml"
        $newPath = Join-Path $workflowDir $newName
        
        Write-Host "🔴 Disable: $($file.Name) -> $newName" -ForegroundColor Yellow
        
        Rename-Item $file.FullName $newPath -Force
    }
}

Write-Host "`n✅ Done! Active workflows: ai_tipster_system.yml + update-dashboard-data.yml`n" -ForegroundColor Green
