# 4incorp Backend Stack

This stack adds a production-shaped AWS backend for the attached `4incorp.com`
frontend without changing the existing EZiMarts marketplace resources.

## What Terraform Creates

- Private S3 bucket for frontend files.
- CloudFront distribution for the frontend.
- Private S3 bucket for application documents.
- DynamoDB tables for users, applications, documents, payments, messages, and OTP records.
- Python Lambda API for auth, applications, document uploads, messages, and manual payment records.
- API Gateway HTTP API with CORS.
- IAM role and least-scoped policies for the Lambda.

## Important Variables

Set production values in `terraform.tfvars`:

```hcl
fourincorp_app_secret             = "use-a-long-random-secret-here"
fourincorp_admin_email            = "admin@4incorp.com"
fourincorp_staff_emails           = ["staff1@4incorp.com", "staff2@4incorp.com"]
fourincorp_acm_certificate_arn    = "arn:aws:acm:us-east-1:ACCOUNT:certificate/..."
fourincorp_frontend_bucket_name   = "4incorp.com"
fourincorp_documents_bucket_name  = "4incorp-application-documents"
```

If you do not set `fourincorp_acm_certificate_arn`, CloudFront still deploys,
but only with its default `*.cloudfront.net` domain.

## Deploy

```powershell
terraform init
terraform plan
terraform apply
```

After apply, use:

```powershell
terraform output fourincorp_api_url
terraform output fourincorp_frontend_cloudfront_url
terraform output fourincorp_frontend_bucket_name
```

Upload the attached HTML as `index.html` to the frontend bucket and invalidate
CloudFront.

## API Routes

Base URL comes from `terraform output fourincorp_api_url`.

```text
POST  /auth/register
POST  /auth/login
POST  /applications
GET   /applications
GET   /applications/{reference}
PATCH /applications/{reference}
POST  /applications/{reference}/documents
POST  /applications/{reference}/messages
POST  /applications/{reference}/payments
```

Protected routes use:

```text
Authorization: Bearer <token>
```

## Frontend Wiring

Replace the frontend's `localStorage` demo submit/login/register handlers with
calls to this API.

Example application submit:

```js
const FOURINCORP_API_BASE_URL = "https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod";

async function fourincorpRequest(path, options = {}) {
  const token = localStorage.getItem("4incorpToken");
  const response = await fetch(FOURINCORP_API_BASE_URL + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || "Request failed");
  return data;
}

async function submitFormationApplication(form) {
  const payload = Object.fromEntries(new FormData(form).entries());
  const result = await fourincorpRequest("/applications", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return result.reference;
}
```

## Notes

- The Lambda stores secure password hashes, not plaintext passwords.
- The first registered `fourincorp_admin_email` receives the `admin` role.
- Emails listed in `fourincorp_staff_emails` receive the `staff` role.
- Guest applications can be submitted without a token.
- File upload uses presigned S3 posts so documents do not pass through Lambda.
