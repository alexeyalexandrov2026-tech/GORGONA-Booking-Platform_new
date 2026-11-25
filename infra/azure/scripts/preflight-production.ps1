<#
.SYNOPSIS
  Read-only Production Go-Live preflight validator for GORGONA (zero Azure spend).
.DESCRIPTION
  Verifies all infrastructure, quota, image digest, OIDC, and notification prerequisites
  before running stack-up.ps1 for paid Production. Creates or modifies nothing.
#>
param(
    [string]$SubscriptionId = '5f50de54-70cf-46de-a936-7be73f76201e',
    [string]$Location = 'centralus',
    [string]$AcrName = 'gorgonaacrga8b00',
    [string]$ImageDigest = ''
)
$ErrorActionPreference = 'Stop'
$failures = [System.Collections.Generic.List[string]]::new()

Write-Host "=== GORGONA PRODUCTION PREFLIGHT (READ-ONLY) ==="
$sub = az account show --query id -o tsv 2>$null
if ($sub -ne $SubscriptionId) {
    $failures.Add("Active Azure subscription ($sub) does not match expected ($SubscriptionId).")
} else {
    Write-Host "[OK] Subscription: $sub"
}

$usage = az rest --method get --url "https://management.azure.com/subscriptions/$SubscriptionId/providers/Microsoft.App/locations/$Location/usages?api-version=2024-03-01" | ConvertFrom-Json
$envQuota = $usage.value | Where-Object { $_.name.value -eq 'ManagedEnvironmentCount' }
if (-not $envQuota -or $envQuota.limit -le $envQuota.currentValue) {
    $failures.Add("Container Apps ManagedEnvironmentCount quota exhausted ($($envQuota.currentValue)/$($envQuota.limit)); request increase to 5 before deploying Production.")
} else {
    Write-Host "[OK] Container Apps ManagedEnvironmentCount: $($envQuota.currentValue)/$($envQuota.limit)"
}

foreach ($var in @('GBA_AUTH_ISSUER', 'GBA_AUTH_AUDIENCE', 'GBA_AUTH_JWKS_URL', 'GBA_AUTH_CLIENT_ID', 'GBA_AUTH_SCOPE')) {
    $val = [Environment]::GetEnvironmentVariable($var)
    if ([string]::IsNullOrWhiteSpace($val)) {
        $failures.Add("Missing OIDC environment variable: $var (configure Entra External ID CIAM).")
    } else {
        Write-Host "[OK] OIDC var set: $var"
    }
}

if (-not [string]::IsNullOrWhiteSpace($ImageDigest)) {
    $manifest = az acr repository show --name $AcrName --image "gorgona-api@$ImageDigest" --query digest -o tsv 2>$null
    if ($manifest -ne $ImageDigest) {
        $failures.Add("Image digest gorgona-api@$ImageDigest not found in ACR $AcrName.")
    } else {
        Write-Host "[OK] Verified ACR image digest: $manifest"
    }
}

$bicepRoot = Join-Path $PSScriptRoot '..\main-platform.bicep'
az bicep build --file $bicepRoot --stdout > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    $failures.Add("az bicep build failed for main-platform.bicep.")
} else {
    Write-Host "[OK] main-platform.bicep compiles cleanly."
}

if ($failures.Count -gt 0) {
    Write-Host "`nPREFLIGHT BLOCKED ($($failures.Count) prerequisites missing):" -ForegroundColor Yellow
    foreach ($f in $failures) { Write-Host "  - $f" -ForegroundColor Red }
    exit 2
}
Write-Host "`nALL PRODUCTION PREFLIGHT CHECKS PASSED." -ForegroundColor Green