[CmdletBinding()]
param(
    [string]$Profile = "4incorp",
    [string]$ExpectedAccount = "424123860784"
)

$ErrorActionPreference = "Stop"
$ProjectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectPath
$PlanPath = Join-Path $ProjectPath "4incorp.tfplan"
$StatePath = Join-Path $ProjectPath "terraform.tfstate"

# Prevent user-level Terraform argument overrides from injecting an additional
# working-directory argument into plan/apply.
Remove-Item Env:TF_CLI_ARGS -ErrorAction SilentlyContinue
Remove-Item Env:TF_CLI_ARGS_plan -ErrorAction SilentlyContinue
Remove-Item Env:TF_CLI_ARGS_apply -ErrorAction SilentlyContinue

if ((Test-Path -LiteralPath $StatePath -PathType Leaf) -and
    (Select-String -LiteralPath $StatePath -SimpleMatch '449442411456' -Quiet)) {
    throw "Terraform state still references account 449442411456. Run .\cleanup-wrong-account.ps1 successfully before deployment."
}

Write-Host "Signing in to AWS IAM Identity Center profile '$Profile'..."
aws sso login --profile $Profile
if ($LASTEXITCODE -ne 0) { throw "AWS SSO login failed." }

$ActualAccount = aws sts get-caller-identity --profile $Profile --query Account --output text
if ($LASTEXITCODE -ne 0 -or $ActualAccount -ne $ExpectedAccount) {
    throw "Safety check failed. Expected AWS account $ExpectedAccount but received $ActualAccount."
}

$env:AWS_PROFILE = $Profile
terraform "-chdir=$ProjectPath" init
if ($LASTEXITCODE -ne 0) { throw "terraform init failed." }

terraform "-chdir=$ProjectPath" validate
if ($LASTEXITCODE -ne 0) { throw "terraform validate failed." }

terraform "-chdir=$ProjectPath" plan "-out=$PlanPath"
if ($LASTEXITCODE -ne 0) { throw "terraform plan failed." }

Write-Host "Review the plan above. Terraform will ask for final approval before creating resources."
terraform "-chdir=$ProjectPath" apply $PlanPath
if ($LASTEXITCODE -ne 0) { throw "terraform apply failed." }

$FrontendBucket = terraform output -raw fourincorp_frontend_bucket_name
$DistributionId = terraform output -raw fourincorp_cloudfront_distribution_id
$ApiUrl = (terraform output -raw fourincorp_api_url).TrimEnd('/')
$UserPoolId = terraform output -raw fourincorp_cognito_user_pool_id
$ClientId = terraform output -raw fourincorp_cognito_client_id

$RuntimeConfig = @"
window.FOURINCORP_CONFIG = {
  apiBaseUrl: "$ApiUrl",
  cognitoUserPoolId: "$UserPoolId",
  cognitoClientId: "$ClientId"
};
"@
Set-Content -LiteralPath (Join-Path $ProjectPath "config.js") -Value $RuntimeConfig -Encoding utf8

aws s3 cp .\4incorpindex.html "s3://$FrontendBucket/index.html" `
    --profile $Profile `
    --content-type "text/html; charset=utf-8" `
    --cache-control "no-cache"
if ($LASTEXITCODE -ne 0) { throw "Frontend upload failed." }

aws s3 cp .\config.js "s3://$FrontendBucket/config.js" `
    --profile $Profile `
    --content-type "application/javascript; charset=utf-8" `
    --cache-control "no-cache"
if ($LASTEXITCODE -ne 0) { throw "Runtime configuration upload failed." }

aws s3 cp .\production-api.js "s3://$FrontendBucket/production-api.js" `
    --profile $Profile `
    --content-type "application/javascript; charset=utf-8" `
    --cache-control "no-cache"
if ($LASTEXITCODE -ne 0) { throw "Frontend API adapter upload failed." }

aws cloudfront create-invalidation `
    --profile $Profile `
    --distribution-id $DistributionId `
    --paths "/*" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "CloudFront invalidation failed." }

Write-Host "Deployment submitted successfully."
Write-Host "Website: $(terraform output -raw fourincorp_domain)"
Write-Host "API: $(terraform output -raw fourincorp_api_url)"
Write-Host "Client records bucket: $(terraform output -raw fourincorp_client_records_bucket_name)"
Write-Host "Stripe webhook: $(terraform output -raw fourincorp_stripe_webhook_url)"
Write-Host "Next: create the webhook in Stripe, then store StripeSecretKey and StripeWebhookSecret in the emitted Secrets Manager secret."
