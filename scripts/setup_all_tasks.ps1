# Tippmix - Task Scheduler Setup Script
# Creates all 5 daily scheduled tasks for automated operation

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  TIPPMIX - TASK SCHEDULER SETUP" -ForegroundColor Cyan
Write-Host "============================================================`n" -ForegroundColor Cyan

# Check admin rights
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "ERROR: Admin rights szükséges!" -ForegroundColor Red
    Write-Host "Jobb klikk → Run as Administrator`n" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Get script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir

Write-Host "Project directory: $projectDir`n" -ForegroundColor Green

# Task definitions
$tasks = @(
    @{
        Name = "Tippmix Aggregator"
        Script = "aggregate_tipsters.py"
        Time = "01:00"
        Description = "Phase 2 - Collect tips from Reddit, Telegram, Nemzeti Sport"
    },
    @{
        Name = "Tippmix Results"
        Script = "fetch_results.py"
        Time = "03:00"
        Description = "Phase 3 - Fetch completed match results from TheOddsAPI"
    },
    @{
        Name = "Tippmix Settler"
        Script = "settle_tips.py"
        Time = "03:15"
        Description = "Phase 3 - Auto-settle tips and update tipster stats"
    },
    @{
        Name = "Tippmix AI Analysis"
        Script = "ai_consensus.py"
        Time = "14:00"
        Description = "Phase 4 - AI consensus analysis and TOP 6 selection"
    },
    @{
        Name = "Tippmix TOP6 Alert"
        Script = "send_top6_alert.py"
        Time = "15:00"
        Description = "Phase 5 - Send daily TOP 6 alert to Telegram VIP"
    }
)

# Create tasks
$created = 0
$failed = 0

foreach ($task in $tasks) {
    Write-Host "Creating task: $($task.Name)..." -ForegroundColor Yellow
    Write-Host "  Script: $($task.Script)" -ForegroundColor Gray
    Write-Host "  Time: $($task.Time)" -ForegroundColor Gray
    
    $scriptPath = Join-Path $scriptDir $task.Script
    $action = "python `"$scriptPath`""
    
    # Create task using schtasks
    $result = schtasks /create /tn $task.Name /tr $action /sc daily /st $task.Time /f 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✅ Created successfully`n" -ForegroundColor Green
        $created++
    } else {
        Write-Host "  ❌ Failed: $result`n" -ForegroundColor Red
        $failed++
    }
}

# Summary
Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  SETUP COMPLETE" -ForegroundColor Cyan
Write-Host "============================================================`n" -ForegroundColor Cyan

Write-Host "✅ Created: $created tasks" -ForegroundColor Green
if ($failed -gt 0) {
    Write-Host "❌ Failed: $failed tasks`n" -ForegroundColor Red
} else {
    Write-Host ""
}

# Show schedule
Write-Host "📅 DAILY SCHEDULE:" -ForegroundColor Cyan
Write-Host "  01:00 - Aggregator (Reddit/Telegram/Nemzeti Sport)" -ForegroundColor Gray
Write-Host "  03:00 - Results (TheOddsAPI)" -ForegroundColor Gray
Write-Host "  03:15 - Settler (auto-settlement)" -ForegroundColor Gray
Write-Host "  14:00 - AI Analysis (OpenAI GPT-4o-mini)" -ForegroundColor Gray
Write-Host "  15:00 - TOP6 Alert (Telegram VIP)" -ForegroundColor Gray
Write-Host ""

# Next steps
Write-Host "🎯 NEXT STEPS:" -ForegroundColor Cyan
Write-Host "  1. OpenAI API key: Set OPENAI_API_KEY environment variable" -ForegroundColor Yellow
Write-Host "     (Get from: https://platform.openai.com/api-keys)" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Test run (optional):" -ForegroundColor Yellow
Write-Host "     cd `"$projectDir`"" -ForegroundColor Gray
Write-Host "     python scripts\aggregate_tipsters.py" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. View tasks:" -ForegroundColor Yellow
Write-Host "     taskschd.msc (Task Scheduler GUI)" -ForegroundColor Gray
Write-Host "     schtasks /query | findstr Tippmix" -ForegroundColor Gray
Write-Host ""

# Bootstrap info
Write-Host "⏳ BOOTSTRAP PERIOD (3-4 weeks):" -ForegroundColor Cyan
Write-Host "  - Week 1: Data collection starts" -ForegroundColor Gray
Write-Host "  - Week 2: Tips settle, stats emerge" -ForegroundColor Gray
Write-Host "  - Week 3: Qualified tipsters detected" -ForegroundColor Gray
Write-Host "  - Week 4: Full system operational! 🚀" -ForegroundColor Gray
Write-Host ""

Write-Host "🏆 ALL 5 PHASES AUTOMATED! SYSTEM READY!" -ForegroundColor Green
Write-Host "============================================================`n" -ForegroundColor Cyan

Read-Host "Press Enter to exit"
