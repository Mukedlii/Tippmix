#!/usr/bin/env pwsh
# Set ODDS_API_KEY GitHub Secret

$GITHUB_TOKEN = $env:GITHUB_TOKEN
if (-not $GITHUB_TOKEN) {
    throw "GITHUB_TOKEN environment variable is required."
}

$repo = "Mukedlii/Tippmix"
$secretName = "ODDS_API_KEY"
$secretValue = $env:ODDS_API_KEY
if (-not $secretValue) {
    throw "ODDS_API_KEY environment variable is required."
}

Write-Host "Setting GitHub Secret: $secretName"

# Get public key for encryption
$keyUrl = "https://api.github.com/repos/$repo/actions/secrets/public-key"
$headers = @{
    "Authorization" = "Bearer $GITHUB_TOKEN"
    "Accept" = "application/vnd.github+json"
}

try {
    $keyResponse = Invoke-RestMethod -Uri $keyUrl -Headers $headers
    $publicKey = $keyResponse.key
    $keyId = $keyResponse.key_id
    
    Write-Host "Got public key: $keyId"
    
    # Encrypt secret (requires libsodium or similar - complex in PowerShell)
    # Easiest way: use gh CLI or GitHub UI
    
    Write-Host ""
    Write-Host "⚠️  PowerShell encryption is complex. Use one of these instead:"
    Write-Host ""
    Write-Host "1. GitHub UI:"
    Write-Host "   https://github.com/$repo/settings/secrets/actions"
    Write-Host "   New secret -> Name: $secretName -> Value: $secretValue"
    Write-Host ""
    Write-Host "2. GitHub CLI (if installed):"
    Write-Host "   gh secret set $secretName --body `"$secretValue`""
    
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}
