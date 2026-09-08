[CmdletBinding()]
param(
    [string]$WrongAccountProfile = "ezimarts",
    [string]$WrongAccountId = "449442411456"
)

$ErrorActionPreference = "Stop"
$ProjectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResolvedProject = (Resolve-Path -LiteralPath $ProjectPath).Path
$StatePath = Join-Path $ResolvedProject "terraform.tfstate"
$BackupDirectory = Join-Path $ResolvedProject "state-backups"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupPath = Join-Path $BackupDirectory "terraform.tfstate.before-4incorp-move-$Timestamp.json"
$DestroyPlan = Join-Path $ResolvedProject "destroy-4incorp-from-449442411456.tfplan"
$ExpectedBuckets = @("4incorp.com-web", "4incorp.com-documents")

Remove-Item Env:TF_CLI_ARGS -ErrorAction SilentlyContinue
Remove-Item Env:TF_CLI_ARGS_plan -ErrorAction SilentlyContinue
Remove-Item Env:TF_CLI_ARGS_apply -ErrorAction SilentlyContinue

if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
    throw "Terraform state was not found at $StatePath"
}

Write-Host "Signing in to the account that accidentally contains the 4incorp stack..."
aws sso login --profile $WrongAccountProfile
if ($LASTEXITCODE -ne 0) { throw "AWS SSO login failed." }

$ActualAccount = aws sts get-caller-identity --profile $WrongAccountProfile --query Account --output text
if ($LASTEXITCODE -ne 0 -or $ActualAccount -ne $WrongAccountId) {
    throw "Safety check failed. Expected account $WrongAccountId but received $ActualAccount."
}

$env:AWS_PROFILE = $WrongAccountProfile
New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
Copy-Item -LiteralPath $StatePath -Destination $BackupPath
if (-not (Test-Path -LiteralPath $BackupPath -PathType Leaf)) {
    throw "State backup could not be verified. Cleanup stopped."
}
Write-Host "State backup created: $BackupPath"

$StateResources = @(terraform "-chdir=$ResolvedProject" state list)
if ($LASTEXITCODE -ne 0 -or $StateResources.Count -eq 0) {
    throw "Terraform state is empty or unreadable. Cleanup stopped."
}
$Unexpected = @($StateResources | Where-Object {
    $_ -notmatch '^(data\.(archive_file|aws_route53_zone)\.fourincorp|aws_[^.]+\.fourincorp)' -and
    $_ -notin @(
        'aws_cognito_user_group.admin',
        'aws_cognito_user_group.customer',
        'aws_cognito_user_group.staff'
    )
})
if ($Unexpected.Count -gt 0) {
    Write-Host "Unexpected state entries were found:"
    $Unexpected | ForEach-Object { Write-Host "  $_" }
    throw "Cleanup stopped because the state is not exclusively the 4incorp stack."
}

terraform "-chdir=$ResolvedProject" plan -destroy "-out=$DestroyPlan"
if ($LASTEXITCODE -ne 0) { throw "Terraform could not produce the destroy plan." }

Write-Host "Review the destroy plan above carefully."
$Confirmation = Read-Host "Type DELETE-4INCORP-FROM-449442411456 to continue"
if ($Confirmation -cne "DELETE-4INCORP-FROM-449442411456") {
    throw "Confirmation did not match. Nothing was deleted."
}

foreach ($Bucket in $ExpectedBuckets) {
    $Location = aws s3api get-bucket-location --bucket $Bucket --profile $WrongAccountProfile --query LocationConstraint --output text 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Emptying confirmed 4incorp bucket s3://$Bucket in account $WrongAccountId..."
        aws s3 rm "s3://$Bucket" --recursive --profile $WrongAccountProfile
        if ($LASTEXITCODE -ne 0) { throw "Could not empty s3://$Bucket. Cleanup stopped." }
    } else {
        Write-Host "Bucket $Bucket is absent or inaccessible; Terraform will handle its recorded state."
    }
}

terraform "-chdir=$ResolvedProject" apply $DestroyPlan
if ($LASTEXITCODE -ne 0) {
    throw "Terraform destroy did not finish. Preserve the state and inspect the error before continuing."
}

Write-Host "The accidental 4incorp stack was removed from account $WrongAccountId."
Write-Host "Backup retained at: $BackupPath"
Write-Host "Next run: .\deploy.ps1"
