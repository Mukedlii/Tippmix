# Tippmix Task Scheduler Auto-Setup
# Run this script ONCE when you're home (Right-click → Run with PowerShell)

Write-Host "🚀 Tippmix Task Scheduler Setup" -ForegroundColor Cyan
Write-Host "=" * 60
Write-Host ""

# Check admin rights
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "❌ This script needs ADMIN rights!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Right-click this file → 'Run with PowerShell as Administrator'" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}

Write-Host "✅ Admin rights confirmed" -ForegroundColor Green
Write-Host ""

# Task details
$taskName = "Tippmix Daily Reddit Alert"
$taskPath = "\"
$scriptPath = "C:\Users\Muki\clawd\Tippmix\run_daily_reddit_alert.bat"
$workingDir = "C:\Users\Muki\clawd\Tippmix"

# Check if script exists
if (-not (Test-Path $scriptPath)) {
    Write-Host "❌ Script not found: $scriptPath" -ForegroundColor Red
    Write-Host ""
    Write-Host "Make sure you're in the correct directory!" -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "✅ Script found: $scriptPath" -ForegroundColor Green
Write-Host ""

# Delete existing task if exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "⚠️  Existing task found, removing..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "✅ Old task removed" -ForegroundColor Green
    Write-Host ""
}

# Create task action
$action = New-ScheduledTaskAction `
    -Execute $scriptPath `
    -WorkingDirectory $workingDir

# Create task trigger (daily at 15:00)
$trigger = New-ScheduledTaskTrigger -Daily -At "15:00"

# Create task principal (run as current user, highest privileges)
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest

# Create task settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

# Register the task
Write-Host "📝 Creating scheduled task..." -ForegroundColor Cyan

try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -TaskPath $taskPath `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "Sends Reddit TOP PICKS to Telegram VIP daily at 15:00 CET" | Out-Null
    
    Write-Host "✅ Task created successfully!" -ForegroundColor Green
    Write-Host ""
    
    # Test run
    Write-Host "🧪 Do you want to TEST RUN now? (y/n): " -ForegroundColor Yellow -NoNewline
    $testRun = Read-Host
    
    if ($testRun -eq 'y' -or $testRun -eq 'Y') {
        Write-Host ""
        Write-Host "▶️  Running test..." -ForegroundColor Cyan
        Start-ScheduledTask -TaskName $taskName
        Write-Host "✅ Test started! Check Telegram VIP in 1-2 minutes!" -ForegroundColor Green
    }
    
    Write-Host ""
    Write-Host "=" * 60
    Write-Host "🎉 SETUP COMPLETE!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Task name: $taskName" -ForegroundColor White
    Write-Host "Schedule: Daily at 15:00 (3 PM)" -ForegroundColor White
    Write-Host "Next run: Tomorrow 15:00" -ForegroundColor White
    Write-Host ""
    Write-Host "To check status: Open Task Scheduler (taskschd.msc)" -ForegroundColor Cyan
    Write-Host ""
    
} catch {
    Write-Host "❌ Error creating task: $_" -ForegroundColor Red
    Write-Host ""
}

pause
