#!/usr/bin/env pwsh
# Trigger GitHub Actions workflow manually

$GITHUB_TOKEN = $env:GITHUB_TOKEN
if (-not $GITHUB_TOKEN) {
    Write-Host "GitHub Personal Access Token not found in environment."
    Write-Host ""
    Write-Host "Options:"
    Write-Host "1) Set GITHUB_TOKEN environment variable"
    Write-Host "2) Or enter token now (it won't be saved):"
    Write-Host ""
    $GITHUB_TOKEN = Read-Host "GitHub Token (ghp_...)" -AsSecureString
    $GITHUB_TOKEN = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($GITHUB_TOKEN)
    )
}

$repo = "Mukedlii/Tippmix"
$workflow = "tippmix_morning_full.yml"
$branch = "main"

$url = "https://api.github.com/repos/$repo/actions/workflows/$workflow/dispatches"

Write-Host "Triggering workflow: $workflow on $branch..."

$headers = @{
    "Authorization" = "Bearer $GITHUB_TOKEN"
    "Accept" = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}

$body = @{
    ref = $branch
} | ConvertTo-Json

try {
    $response = Invoke-WebRequest -Uri $url -Method POST -Headers $headers -Body $body -ContentType "application/json"
    
    if ($response.StatusCode -eq 204) {
        Write-Host "✓ Workflow triggered successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Check status: https://github.com/$repo/actions"
    } else {
        Write-Host "Unexpected response: $($response.StatusCode)" -ForegroundColor Yellow
        Write-Host $response.Content
    }
} catch {
    Write-Host "Error triggering workflow:" -ForegroundColor Red
    Write-Host $_.Exception.Message
    Write-Host ""
    Write-Host "Make sure your GitHub token has 'workflow' scope."
    Write-Host "Create token: https://github.com/settings/tokens/new?scopes=workflow"
}
